"""Feed de gatilhos da aba Sinais (apoio à decisão — o usuário decide e executa).

Três tipos de evento, gerados a cada varredura (cripto na VM e MT5 no PC):
- "gatilho": na vela de 15m que acabou de fechar aconteceu o que a leitura esperava A FAVOR do 1H
  (1H em alta pela Dow e acima da MME50 → CHoCH/BOS de alta, quebra da LTB, cunha de baixa rompida
  ou MME9 cruzando a MME21 para cima; espelhado para venda). Entrada, stop no último fundo/topo do
  15m e alvos em R vêm de signals/structure_setups.py — mesmo cálculo do backtest.
- "na_zona": o preço chegou na zona de um plano de entrada (antes estava fora dela).
- "invalidado": um plano passou a INVALIDADO (o preço passou do stop estimado).
Os gatilhos de estrutura NÃO mostraram vantagem no backtest intraday; o feed traz isso escrito.

Cada evento vai uma única vez (FeedState guarda os ids enviados e a situação anterior dos planos).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from bot.config import with_profile
from bot.signals.base import Signal
from bot.signals.direction import invert_frame, to_short
from bot.signals.plans import SETUP_NAMES
from bot.signals.structure_setups import STRUCTURE_SETUPS, structure_signals_live

FEED_NOTE = ("Leitura de estrutura sem vantagem medida no backtest intraday (12/10/2026): use como apoio, "
             "confirme no gráfico e decida você")
PRIORITY = ("cunha", "estrutura_choch", "lt_rompimento", "estrutura_bos", "medias_cruzamento")
TRIGGER_TEXT = {
    "estrutura_bos": ("BOS de alta: fechou acima do último topo do 15m",
                      "BOS de baixa: fechou abaixo do último fundo do 15m"),
    "estrutura_choch": ("CHoCH de alta: o recuo do 15m virou para alta",
                        "CHoCH de baixa: o repique do 15m virou para baixa"),
    "lt_rompimento": ("quebra da LTB do 15m", "quebra da LTA do 15m"),
    "cunha": ("rompimento de cunha de baixa (falling wedge) no 15m", "perda de cunha de alta (rising wedge) no 15m"),
    "medias_cruzamento": ("MME9 cruzou acima da MME21 no 15m (acima da MME200)",
                          "MME9 cruzou abaixo da MME21 no 15m (abaixo da MME200)"),
}
CONTEXT_TEXT = ("1H em alta (Dow) e acima da MME50", "1H em baixa (Dow) e abaixo da MME50")
KIND_LABEL = {"gatilho": "Gatilho atingido", "na_zona": "Preço na zona do plano", "invalidado": "Plano invalidado"}
SIDE_WORD = {1: "compra", -1: "venda"}
MAX_SENT = 3000
TRACK_HOURS = 12           # gatilho sem alvo nem stop em 12 h = "expirou" (pelo último preço)
M15_MS = 15 * 60_000


@dataclass
class FeedEvent:
    market: str                 # "cripto" | "mt5"
    asset: str                  # ex.: "BTCUSDT", "XAUUSD"
    direction: int              # 1 compra, −1 venda
    kind: str                   # gatilho | na_zona | invalidado
    setup: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    event_id: str
    description: str
    context: str = ""
    score: float | None = None
    gemini: Any = None          # Analysis | None
    extra: dict[str, Any] = field(default_factory=dict)
    source: str = ""            # símbolo de onde vêm as velas (ex.: XAUUSD.s) para o placar

    @property
    def side(self) -> str:
        return SIDE_WORD[self.direction]

    @property
    def label(self) -> str:
        return f"{self.asset} · {self.side}"

    def payload(self) -> dict[str, Any]:
        """Evento `signal` do painel (tabela signals), com os detalhes em `details`."""
        risk = (self.entry - self.stop) * self.direction
        rr = (self.tp2 - self.entry) * self.direction / risk if risk > 0 else None
        gem = None
        if self.gemini is not None:
            v = self.gemini.verdict
            gem = {"veredito": v.veredito, "risco": v.risco, "resumo": v.resumo if self.gemini.ok else None}
        text = f"{KIND_LABEL[self.kind]} ({self.side}): {self.description}"
        if self.context:
            text += f" | contexto: {self.context}"
        return {
            "symbol": self.label, "setup": self.setup, "entry": self.entry, "stop": self.stop, "tp1": self.tp1,
            "tp2": self.tp2, "rr": round(rr, 2) if rr else None,
            "score": round(self.score, 1) if self.score is not None else None,
            "status": self.kind, "reason": text, "order_link_id": self.event_id,
            "details": {"mercado": self.market, "ativo": self.asset, "lado": self.side, "evento": self.kind,
                        "titulo": KIND_LABEL[self.kind], "descricao": self.description, "contexto": self.context,
                        "setup_nome": SETUP_NAMES.get(self.setup, self.setup), "gemini": gem, "nota": FEED_NOTE,
                        **({"resultado": "aberto"} if self.kind == "gatilho" else {}), **self.extra},
        }


def feed_config(config: Any) -> Any:
    """Config do feed: day trade 15m/1H, todos os setups de estrutura, contexto Dow + MME50."""
    cfg = with_profile(config, "15", "60")
    st = cfg.setups.model_copy(update={
        "enabled": list(STRUCTURE_SETUPS),
        "estrutura": cfg.setups.estrutura.model_copy(update={"context": "dow_e_media"})})
    return cfg.model_copy(update={"setups": st})


def structure_events(market: str, asset: str, symbol: str, m15: pd.DataFrame, h1: pd.DataFrame, now_ms: int,
                     config: Any, directions: tuple[int, ...] = (1, -1),
                     scores: dict[int, float] | None = None, gemini: dict[int, Any] | None = None) -> list[FeedEvent]:
    """Gatilhos de estrutura na vela de 15m que acabou de fechar, compra e/ou venda (um por direção)."""
    cfg = feed_config(config)
    out = []
    for direction in directions:
        short = direction < 0
        trig, ctx = (invert_frame(m15), invert_frame(h1)) if short else (m15, h1)
        raw = structure_signals_live(symbol, trig, ctx, now_ms, 0.0, cfg)
        if not raw:
            continue
        raw.sort(key=lambda s: PRIORITY.index(s.setup))
        main: Signal = to_short(raw[0], cfg.exits) if short else raw[0]
        side_i = 1 if short else 0
        also = [TRIGGER_TEXT[s.setup][side_i].split(":")[0] for s in raw[1:]]
        description = TRIGGER_TEXT[main.setup][side_i] + (f" (também: {', '.join(also)})" if also else "")
        out.append(FeedEvent(market, asset, direction, "gatilho", main.setup, main.entry, main.stop, main.tp1,
                             main.tp2, main.order_link_id, description, CONTEXT_TEXT[side_i],
                             score=(scores or {}).get(direction), gemini=(gemini or {}).get(direction),
                             extra={"vela_15m_ms": main.candle_start_ms}, source=symbol))
    return out


def plan_events(market: str, asset: str, direction: int, plans: list[dict[str, Any]], state: FeedState,
                now_ms: int, score: float | None = None, gemini: Any = None) -> list[FeedEvent]:
    """Mudanças de situação dos planos: entrou na zona ou ficou invalidado (só a partir da 2ª varredura)."""
    stamp = now_ms - now_ms % (15 * 60_000)
    out = []
    for p in plans:
        if p.get("alerta"):
            continue
        key = f"{market}|{asset}|{p['setup']}|{p['lado']}"
        cur, prev = p.get("situacao") or "", state.plans.get(key)
        state.plans[key] = cur
        if prev is None or prev == cur or cur not in ("na_zona", "invalidado"):
            continue
        code = "z" if cur == "na_zona" else "x"
        event_id = f"{asset}-{code}{p['setup'][:3].lower()}{'s' if direction < 0 else ''}-{stamp // 60_000}"[:36]
        if cur == "na_zona":
            low, high = p["zona"] if p.get("zona") else (p["entrada"], p["entrada"])
            description = (f"{p['setup']}: o preço entrou na zona {_fmt(low)}–{_fmt(high)}; "
                           f"aguardar o gatilho: {p['gatilho']}")
        else:
            back = "voltar abaixo" if direction < 0 else "voltar acima"
            description = (f"{p['setup']}: o preço passou do stop estimado ({_fmt(p['stop'])}); só volta a valer se "
                           f"{back} de {_fmt(p.get('retomada') or p['entrada'])}")
        setup_key = next((k for k, v in SETUP_NAMES.items() if v == p["setup"]), p["setup"])
        out.append(FeedEvent(market, asset, direction, cur, setup_key, p["entrada"], p["stop"], p["tp1"], p["tp2"],
                             event_id, description, score=score, gemini=gemini))
    return out


def _fmt(value: float) -> str:
    return f"{value:.6g}".replace(".", ",")


@dataclass
class FeedState:
    sent: list[str] = field(default_factory=list)
    plans: dict[str, str] = field(default_factory=dict)
    tracking: dict[str, dict[str, Any]] = field(default_factory=dict)   # gatilhos em acompanhamento (placar)

    @classmethod
    def load(cls, path: str | Path) -> FeedState:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(list(raw.get("sent", [])), dict(raw.get("plans", {})), dict(raw.get("tracking", {})))
        except (FileNotFoundError, ValueError):
            return cls()

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {"sent": self.sent[-MAX_SENT:], "plans": self.plans, "tracking": self.tracking}
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    def new(self, events: list[FeedEvent]) -> list[FeedEvent]:
        seen = set(self.sent)
        return [e for e in events if e.event_id not in seen]


def send_events(events: list[FeedEvent], state: FeedState, dashboard: Any) -> tuple[int, int]:
    """Envia os eventos novos (status = tipo do evento). Devolve (enviados, falhas)."""
    ok = fail = 0
    for event in state.new(events):
        payload = event.payload()
        result = dashboard.send("signal", payload)
        if result.ok:
            state.sent.append(event.event_id)
            ok += 1
            if event.kind == "gatilho" and event.source:
                state.tracking[event.event_id] = {
                    "payload": payload, "fonte": event.source, "dir": event.direction, "entrada": event.entry,
                    "stop": event.stop, "tp1": event.tp1, "tp2": event.tp2,
                    "inicio_ms": int(event.extra.get("vela_15m_ms", 0)) + M15_MS}
        else:
            fail += 1
    return ok, fail



def resolve(track: dict[str, Any], candles: pd.DataFrame, now_ms: int, hours: float = TRACK_HOURS) -> dict | None:
    """Resultado do gatilho pelas velas de 15m depois do sinal (entrada no fechamento da vela do gatilho):
    alvo 1 ou stop, o que vier primeiro (os dois na mesma vela = stop, conservador); sem nenhum em
    `hours` horas = expirou pelo último fechamento. None = ainda em aberto."""
    d, entry, stop, tp1, tp2 = track["dir"], track["entrada"], track["stop"], track["tp1"], track["tp2"]
    risk = (entry - stop) * d
    if risk <= 0:
        return {"resultado": "invalido", "resultado_r": 0.0}
    after = candles[candles["start_ms"] >= track["inicio_ms"]]
    best = 0.0
    for row in after.itertuples(index=False):
        high, low = float(row.high), float(row.low)
        best = max(best, ((high - entry) if d > 0 else (entry - low)) / risk)
        end = int(row.start_ms) + M15_MS
        if (low <= stop) if d > 0 else (high >= stop):
            return _outcome("stop", -1.0, end, best)
        if (high >= tp1) if d > 0 else (low <= tp1):
            hit2 = (high >= tp2) if d > 0 else (low <= tp2)
            return _outcome("alvo", (tp1 - entry) * d / risk, end, best, alvo2=hit2)
    if len(after) and now_ms - track["inicio_ms"] >= hours * 3_600_000:
        last = float(after["close"].iat[-1])
        return _outcome("expirou", (last - entry) * d / risk, now_ms, best)
    return None


def _outcome(kind: str, r: float, end_ms: int, best: float, **extra: Any) -> dict[str, Any]:
    return {"resultado": kind, "resultado_r": round(r, 2), "max_favoravel_r": round(best, 2),
            "resolvido_em": datetime.fromtimestamp(end_ms / 1000, UTC).isoformat(timespec="minutes"), **extra}


def update_tracking(state: FeedState, candles_for: Callable[[str], pd.DataFrame | None], now_ms: int,
                    dashboard: Any) -> int:
    """Confere os gatilhos em acompanhamento e manda ao painel os que terminaram. Devolve quantos."""
    done = 0
    for event_id, track in list(state.tracking.items()):
        try:
            candles = candles_for(track["fonte"])
        except Exception:  # um ativo sem dados não derruba o placar
            candles = None
        if candles is None or candles.empty:
            if now_ms - track["inicio_ms"] > 3 * 86_400_000:
                del state.tracking[event_id]   # sem dados há 3 dias: desiste
            continue
        result = resolve(track, candles, now_ms)
        if result is None:
            continue
        payload = dict(track["payload"])
        payload["details"] = {**payload.get("details", {}), **result}
        if dashboard.send("signal", payload).ok:
            del state.tracking[event_id]
            done += 1
    return done
