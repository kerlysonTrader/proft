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
from dataclasses import dataclass, field
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
                        **self.extra},
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
                             extra={"vela_15m_ms": main.candle_start_ms}))
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

    @classmethod
    def load(cls, path: str | Path) -> FeedState:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(list(raw.get("sent", [])), dict(raw.get("plans", {})))
        except (FileNotFoundError, ValueError):
            return cls()

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"sent": self.sent[-MAX_SENT:], "plans": self.plans}), encoding="utf-8")

    def new(self, events: list[FeedEvent]) -> list[FeedEvent]:
        seen = set(self.sent)
        return [e for e in events if e.event_id not in seen]


def send_events(events: list[FeedEvent], state: FeedState, dashboard: Any) -> tuple[int, int]:
    """Envia os eventos novos (status = tipo do evento). Devolve (enviados, falhas)."""
    ok = fail = 0
    for event in state.new(events):
        result = dashboard.send("signal", event.payload())
        if result.ok:
            state.sent.append(event.event_id)
            ok += 1
        else:
            fail += 1
    return ok, fail

