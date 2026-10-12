"""Analista Gemini (seção 5 do 03_ESTRATEGIA.md) — veto qualitativo, nunca define preço/stop/alvo.

- Vertex AI por REST (generateContent) com pesquisa no Google (grounding).
- Credencial: na VM, a conta de serviço (servidor de metadados); no PC, o gcloud já logado
  (`gcloud auth print-access-token`). Nenhuma chave passa pelo chat nem fica em arquivo.
- Saída JSON validada (pydantic). Falha (timeout, JSON inválido, erro de API, teto diário) =
  regra on_failure (cautela ou fail_closed = vetado).
- Cache por ativo (cache_hours), teto de chamadas por dia nesta máquina (max_calls_per_day) e
  auditoria de toda resposta em data/gemini/auditoria.jsonl.
- gemini.calls_enabled = false: nenhuma chamada real (não gera custo); o painel mostra "—".
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from bot.logging_setup import get_logger

log = get_logger("ai.gemini")

METADATA_TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"

SYSTEM_CRYPTO = """Você é um analista de risco de criptomoedas. Sua função é PROTEGER o capital:
identificar motivos para NÃO abrir a operação indicada agora. Você não define preço,
quantidade, stop ou alvo.

Você receberá um JSON com: símbolo, direção pretendida (compra ou venda), score técnico e seus
componentes, indicadores, variações de preço e, quando houver, open interest e funding.

Pesquise na web notícias e dados dos últimos 14 dias e dos próximos {lookahead} dias sobre o
projeto e verifique:
1. Hack, exploit, falha de rede ou de ponte.
2. Deslistagem, tag de monitoramento (ST) ou aviso da Bybit/grandes corretoras.
3. Desbloqueio de tokens (unlock) relevante (> 1% do supply circulante) nos próximos {lookahead} dias.
4. Processos, sanções ou problemas regulatórios.
5. Sinais de pump coordenado, venda de fundadores/fundos ou concentração anormal de carteiras.
6. Eventos positivos concretos (listagem, upgrade de rede, parceria relevante) — apenas como
   contexto, nunca como motivo para aumentar risco.
Numa VENDA, eventos positivos fortes contam como risco contra a operação.
"""

SYSTEM_MT5 = """Você é um analista de risco de mercados globais (metais, forex, índices de ações e
energia) para operações INTRADAY. Sua função é PROTEGER o capital: identificar motivos para NÃO
abrir a operação indicada agora. Você não define preço, quantidade, stop ou alvo.

Você receberá um JSON com: ativo, nome, direção pretendida (compra ou venda), score técnico e
seus componentes, preço, variação de 24 h e a data/hora atual (horário de Brasília).

Pesquise na web as notícias das últimas 48 horas e a agenda econômica das próximas 24 horas que
afetem o ativo e verifique:
1. Eventos de alto impacto nas próximas 24 h: decisão de juros, CPI/inflação, payroll (NFP), PIB,
   discursos de presidentes de bancos centrais, estoques de petróleo (EIA/API), reunião da OPEP+,
   resultados das maiores empresas do índice. Informe data e hora no horário de Brasília.
2. Notícia recente que contrarie a direção pretendida (intervenção cambial, choque geopolítico,
   mudança de política monetária, sanções, tarifa comercial).
3. Feriado ou baixa liquidez nas praças principais do ativo hoje.
4. Movimento extremo ou gap recente que indique volatilidade fora do normal.
"""

RULES = """
Regras:
- Evento grave confirmado por fonte confiável, ou evento de alto impacto nas próximas 2 horas → "vetado".
- Incerteza relevante, evento moderado ou evento de alto impacto nas próximas 24 h → "cautela".
- Nada relevante encontrado → "aprovado".
- Cite a fonte (URL) de cada evento. Não invente eventos nem datas; se não encontrar
  informação, diga que não encontrou.
- Responda SOMENTE com JSON válido, sem texto fora do JSON, neste formato:
{"veredito": "aprovado" | "cautela" | "vetado",
 "risco": "baixo" | "medio" | "alto",
 "eventos": [{"tipo": "%s", "data": "AAAA-MM-DD HH:MM ou null", "descricao": "...", "fonte": "url"}],
 "resumo": "até 400 caracteres, em português",
 "confianca": número entre 0 e 1}
"""
TYPES_CRYPTO = "hack|deslistagem|unlock|regulatorio|pump|positivo|outro"
TYPES_MT5 = "agenda|noticia|geopolitico|feriado|volatilidade|outro"

Kind = Literal["cripto", "mt5"]


def system_prompt(kind: Kind, lookahead_days: int = 14) -> str:
    if kind == "mt5":
        return SYSTEM_MT5 + RULES % TYPES_MT5
    return SYSTEM_CRYPTO.format(lookahead=lookahead_days) + RULES % TYPES_CRYPTO


class GeminiEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tipo: str = "outro"
    data: str | None = None
    descricao: str = ""
    fonte: str | None = None


class GeminiVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    veredito: Literal["aprovado", "cautela", "vetado"]
    risco: Literal["baixo", "medio", "alto"]
    eventos: list[GeminiEvent] = Field(default_factory=list)
    resumo: str = ""
    confianca: float = Field(default=0.0, ge=0, le=1)

    @field_validator("resumo")
    @classmethod
    def _cut(cls, value: str) -> str:
        return value.strip()[:400]

    @field_validator("veredito", "risco", mode="before")
    @classmethod
    def _lower(cls, value: Any) -> Any:
        return value.strip().lower().replace("é", "e") if isinstance(value, str) else value


@dataclass
class Analysis:
    verdict: GeminiVerdict
    ok: bool                       # False = fallback (on_failure)
    error: str | None = None
    cached: bool = False
    model: str = ""
    at_ms: int = 0
    sources: list[str] = field(default_factory=list)

    def panel_fields(self) -> dict[str, Any]:
        """Campos gemini_* do scanner_results no painel."""
        v = self.verdict
        summary = v.resumo if self.ok else f"Sem análise do Gemini ({self.error}) — tratado como {v.veredito}"
        return {"gemini_verdict": v.veredito, "gemini_risk": v.risco, "gemini_summary": summary,
                "gemini_events": [e.model_dump() for e in v.eventos]}

    def line(self) -> str:
        """Uma linha para os motivos/alertas."""
        v = self.verdict
        if not self.ok:
            return f"Gemini: sem análise ({self.error}) — tratado como {v.veredito}"
        return f"Gemini: {v.veredito} (risco {v.risco}) — {v.resumo}"


class GeminiError(Exception):
    pass


def parse_verdict(text: str) -> GeminiVerdict:
    """Extrai o JSON da resposta (aceita cercas ```json) e valida."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise GeminiError("resposta sem JSON")
    try:
        return GeminiVerdict.model_validate(json.loads(cleaned[start:end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiError(f"JSON inválido: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------- credencial
class AccessToken:
    """Token OAuth do Google: servidor de metadados (VM) ou gcloud do usuário (PC)."""

    def __init__(self, http: httpx.Client | None = None, runner: Callable[[list[str]], str] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._http = http or httpx.Client(timeout=5)
        self._runner = runner
        self._clock = clock
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token and self._clock() < self._expires - 120:
                return self._token
            token, ttl = self._from_metadata() or self._from_gcloud()
            self._token, self._expires = token, self._clock() + ttl
            return token

    def _from_metadata(self) -> tuple[str, float] | None:
        try:
            r = self._http.get(METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=2)
        except httpx.HTTPError:
            return None   # fora da VM
        if r.status_code != 200:
            return None
        data = r.json()
        return data["access_token"], float(data.get("expires_in", 3000))

    def _from_gcloud(self) -> tuple[str, float]:
        if self._runner is not None:
            out = self._runner(["auth", "print-access-token"])
        else:
            from bot.secrets import gcloud_executable

            exe = gcloud_executable() or shutil.which("gcloud")
            if not exe:
                raise GeminiError("sem credencial do Google (nem VM, nem gcloud)")
            proc = subprocess.run([exe, "auth", "print-access-token"], capture_output=True, text=True, timeout=60,
                                  check=False)
            if proc.returncode != 0:
                raise GeminiError("gcloud não devolveu token (faça gcloud auth login)")
            out = proc.stdout
        token = out.strip()
        if not token:
            raise GeminiError("token vazio")
        return token, 3000.0


# ---------------------------------------------------------------------------- analista
class GeminiAnalyst:
    def __init__(self, cfg: Any, data_dir: str | Path, http: httpx.Client | None = None,
                 token: AccessToken | None = None, clock: Callable[[], float] = time.time) -> None:
        self.cfg = cfg
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._http = http or httpx.Client(timeout=cfg.timeout_seconds)
        self._token = token or AccessToken()
        self._clock = clock
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ estado (cache e teto diário)
    @property
    def _cache_path(self) -> Path:
        return self.dir / "cache.json"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {"entries": {}, "calls": {}}

    def _save(self, state: dict[str, Any]) -> None:
        horizon = self._clock() - max(self.cfg.cache_hours, 24) * 3600
        state["entries"] = {k: v for k, v in state["entries"].items() if v["at"] >= horizon}
        state["calls"] = dict(sorted(state["calls"].items())[-7:])   # só os últimos dias
        self._cache_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def _today(self) -> str:
        return datetime.fromtimestamp(self._clock(), UTC).strftime("%Y-%m-%d")

    def calls_today(self) -> int:
        return int(self._load()["calls"].get(self._today(), 0))

    def _fallback(self, error: str) -> Analysis:
        verdict = "vetado" if self.cfg.on_failure == "fail_closed" else "cautela"
        return Analysis(GeminiVerdict(veredito=verdict, risco="medio"), ok=False, error=error,
                        model=self.cfg.model_screening, at_ms=int(self._clock() * 1000))

    # ------------------------------------------------------------------ análise
    def analyze(self, key: str, kind: Kind, context: dict[str, Any]) -> Analysis | None:
        """None = Gemini desligado (sem chamada, sem custo). Senão, análise (do cache, nova ou fallback)."""
        if not (self.cfg.enabled and self.cfg.calls_enabled):
            return None
        with self._lock:
            state = self._load()
            hit = state["entries"].get(key)
            if hit and self._clock() - hit["at"] < self.cfg.cache_hours * 3600:
                a = Analysis(GeminiVerdict.model_validate(hit["verdict"]), ok=True, cached=True, model=hit["model"],
                             at_ms=int(hit["at"] * 1000), sources=hit.get("sources", []))
                return a
            today = self._today()
            if state["calls"].get(today, 0) >= self.cfg.max_calls_per_day:
                return self._fallback(f"teto de {self.cfg.max_calls_per_day} análises/dia atingido")
            state["calls"][today] = state["calls"].get(today, 0) + 1
            self._save(state)
        try:
            verdict, sources, raw, usage = self._call(kind, context)
        except (GeminiError, httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            error = str(exc) if isinstance(exc, GeminiError) else type(exc).__name__
            log.warning("análise do Gemini falhou", extra={"data": {"key": key, "error": error}})
            self._audit({"key": key, "kind": kind, "context": context, "error": error})
            return self._fallback(error)
        now = self._clock()
        self._audit({"key": key, "kind": kind, "context": context, "verdict": verdict.model_dump(), "raw": raw,
                     "sources": sources, "usage": usage})
        with self._lock:
            state = self._load()
            state["entries"][key] = {"at": now, "model": self.cfg.model_screening, "verdict": verdict.model_dump(),
                                     "sources": sources}
            self._save(state)
        return Analysis(verdict, ok=True, model=self.cfg.model_screening, at_ms=int(now * 1000), sources=sources)

    def request_body(self, kind: Kind, context: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt(kind, self.cfg.unlock_lookahead_days)}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(context, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
        }
        if self.cfg.use_google_search_grounding:
            body["tools"] = [{"googleSearch": {}}]
        return body

    def endpoint(self) -> str:
        c = self.cfg
        host = "aiplatform.googleapis.com" if c.vertex_location == "global" else \
            f"{c.vertex_location}-aiplatform.googleapis.com"
        return (f"https://{host}/v1/projects/{c.vertex_project}/locations/{c.vertex_location}"
                f"/publishers/google/models/{c.model_screening}:generateContent")

    def _call(self, kind: Kind, context: dict[str, Any]) -> tuple[GeminiVerdict, list[str], str, dict]:
        headers = {"Authorization": f"Bearer {self._token.get()}", "Content-Type": "application/json"}
        r = self._http.post(self.endpoint(), headers=headers, json=self.request_body(kind, context),
                            timeout=self.cfg.timeout_seconds)
        if r.status_code != 200:
            raise GeminiError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        cand = data["candidates"][0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        grounding = cand.get("groundingMetadata", {}) or {}
        chunks = grounding.get("groundingChunks", []) or []
        sources = [c["web"]["uri"] for c in chunks if c.get("web", {}).get("uri")][:8]
        verdict = parse_verdict(text)
        for event in verdict.eventos:   # evento sem URL própria: usa a primeira fonte da pesquisa
            if not event.fonte and sources:
                event.fonte = sources[0]
        usage = dict(data.get("usageMetadata", {}))
        usage["pesquisas_google"] = len(grounding.get("webSearchQueries", []) or [])   # custo do grounding
        usage["grounding_campos"] = sorted(grounding)
        return verdict, sources, text, usage

    def _audit(self, record: dict[str, Any]) -> None:
        record = {"at": datetime.fromtimestamp(self._clock(), UTC).isoformat(timespec="seconds"),
                  "model": self.cfg.model_screening, **record}
        with (self.dir / "auditoria.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def analyze_many(analyst: GeminiAnalyst | None, jobs: list[tuple[Any, str, Kind, dict[str, Any]]],
                 workers: int = 4) -> None:
    """jobs = [(objeto, chave, tipo, contexto)]; grava o resultado em objeto.gemini (em paralelo)."""
    if analyst is None or not jobs:
        return
    from concurrent.futures import ThreadPoolExecutor

    jobs = sorted(jobs, key=lambda j: (getattr(j[0], "watchlist", "B"), -float(getattr(getattr(j[0], "score", None),
                                                                                       "total", 0) or 0)))
    with ThreadPoolExecutor(max_workers=workers) as pool:   # Watchlist A primeiro (teto diário)
        futures = [(obj, pool.submit(analyst.analyze, key, kind, ctx)) for obj, key, kind, ctx in jobs]
        for obj, future in futures:
            obj.gemini = future.result()


def now_brt(ms: int) -> str:
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(ms / 1000, ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M (Brasília)")
