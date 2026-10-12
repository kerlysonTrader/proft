"""Scanner multi-mercado do MT5 (ouro/prata, forex, índices, energia) — SOMENTE LEITURA.

Mesmas regras do cripto e do backtest por mercado (bot.tools.run_backtest --market mt5):
- score 0–100 nas velas 4H/1D (força relativa contra a referência do grupo; sem referência = neutra);
- perfil intraday: gatilho 15m, contexto 1H, faixa de stop do grupo (markets.mt5.stop_pct_range);
- COMPRA e VENDA: a venda roda as mesmas regras no gráfico invertido (signals/direction.py).

Para cada ativo/direção na Watchlist A/B mostra os planos (zona, gatilho, stop, alvos) e a
estatística do backtest daquele mercado/direção. Na Watchlist A, se um setup disparou na última
vela de 15m e passou nos filtros, vira ALERTA. Nunca envia ordens: o usuário decide e executa.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from bot.ai.gemini_analyst import Analysis, GeminiAnalyst, analyze_many, now_brt
from bot.data.market_data import klines_to_frame
from bot.logging_setup import get_logger
from bot.markets.mt5_source import Mt5Reader
from bot.markets.stats import SetupStats, stats_lines
from bot.scanner.features import Features, compute_features, is_num
from bot.scanner.regime import Regime, RegimeState, breadth_pct, evaluate_regime
from bot.scanner.scoring import ScoreResult, classify, score_features
from bot.signals.base import Signal
from bot.signals.direction import invert_frame, to_short
from bot.signals.engine import evaluate_setups
from bot.signals.filters import SignalContext, check_filters
from bot.signals.plans import entry_plans, plan_dict, plan_lines, signal_dict
from bot.signals.structure import StructureParams, structure_reading

log = get_logger("markets.mt5_scanner")

TRIGGER, CONTEXT = "15", "60"
STATUS_BY_LIST = {"A": "watch", "B": "watch_b", "-": "ignored"}
LABEL_BY_LIST = {"A": "Watchlist A", "B": "Watchlist B", "-": "Descartada"}
GROUP_LABEL = {"metais": "metais", "forex": "forex", "indices": "índices", "energia": "energia"}
STALE_MS = 45 * 60_000   # última vela de 15m mais velha que isso = mercado fechado (sem alertas)


def side_word(direction: int) -> str:
    return "compra" if direction > 0 else "venda"


def group_config(config: Any, group: str) -> Any:
    """Config do grupo: intraday 15m/1H e a faixa de stop do grupo."""
    setups = config.setups.model_copy(update={"trigger_interval": TRIGGER, "context_interval": CONTEXT})
    rng = config.markets.mt5.stop_pct_range.get(group)
    if rng:
        setups = setups.model_copy(update={"common": setups.common.model_copy(
            update={"min_stop_pct": rng[0], "max_stop_pct": rng[1]})})
    return config.model_copy(update={"setups": setups})


@dataclass
class Mt5Row:
    symbol: str
    group: str
    direction: int
    price: float
    change_24h_pct: float
    spread_pct: float
    features: Features
    score: ScoreResult
    watchlist: str
    regime: str
    market_open: bool = True
    plans: list[str] = field(default_factory=list)
    plan_data: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[Signal] = field(default_factory=list)                     # dispararam e passaram nos filtros
    blocked: list[tuple[Signal, list[str]]] = field(default_factory=list)  # dispararam mas foram barrados
    gemini: Analysis | None = None
    structure: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.symbol.removesuffix('.s')} · {side_word(self.direction)}"

    @property
    def status(self) -> str:
        return STATUS_BY_LIST[self.watchlist]


@dataclass
class Mt5Scan:
    run_at_ms: int
    duration_ms: int
    rows: list[Mt5Row]
    regimes: dict[str, Regime] = field(default_factory=dict)   # "metais · compra" -> regime
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def alerts(self) -> list[tuple[Mt5Row, Signal]]:
        return [(r, s) for r in self.rows for s in r.alerts]


class Mt5Scanner:
    def __init__(self, reader: Mt5Reader, config: Any, groups: list[str] | None = None,
                 stats: dict[tuple[str, int], dict[str, SetupStats]] | None = None,
                 state_dir: str | Path | None = None, now_ms: Callable[[], int] | None = None,
                 analyst: GeminiAnalyst | None = None) -> None:
        self.analyst = analyst
        self.reader, self.cfg = reader, config
        mcfg = config.markets.mt5
        self.groups = groups or list(mcfg.groups)
        self.directions = [1 if d == "long" else -1 for d in mcfg.directions]
        self.stats = stats or {}
        self.state_dir = Path(state_dir) if state_dir else None
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))

    def _frames(self, symbol: str) -> dict[str, pd.DataFrame]:
        sc, bt, rc = self.cfg.score, self.cfg.backtest.candles, self.cfg.regime
        counts = {"D": max(sc.candles.d1, rc.daily_ema * 3, bt.d1_btc), "240": max(sc.candles.h4, bt.h4),
                  "60": max(sc.candles.h1, bt.h1, 500), TRIGGER: max(bt.h1, 500)}
        return {iv: klines_to_frame(self.reader.rates(symbol, iv, n)) for iv, n in counts.items()}

    def run(self) -> Mt5Scan:
        started = time.monotonic()
        now = self._now_ms()
        rows: list[Mt5Row] = []
        regimes: dict[str, Regime] = {}
        errors: dict[str, str] = {}
        for group in self.groups:
            data: dict[str, dict[str, pd.DataFrame]] = {}
            spreads: dict[str, float] = {}
            for symbol in self.cfg.markets.mt5.groups[group]:
                try:
                    data[symbol] = self._frames(symbol)
                    meta = self.reader.meta(symbol)
                    close = float(data[symbol][TRIGGER]["close"].iloc[-1])
                    spreads[symbol] = meta.spread_pct(close) if meta else float("nan")
                except Exception as exc:  # um ativo com erro não derruba a varredura
                    errors[symbol] = f"{type(exc).__name__}: {exc}"
                    log.warning("falha ao ler o MT5", extra={"symbol": symbol, "data": {"error": str(exc)}})
            params = StructureParams.from_config(self.cfg.setups.estrutura, self.cfg.indicators.atr_period)
            readings = {s: structure_reading(d[TRIGGER], d[CONTEXT], params) for s, d in data.items()}
            for direction in self.directions:
                regime, group_rows = self._scan_group(group, direction, data, spreads, now)
                for r in group_rows:
                    r.structure = readings.get(r.symbol, [])
                regimes[f"{GROUP_LABEL.get(group, group)} · {side_word(direction)}"] = regime
                rows.extend(group_rows)
        wanted = self.cfg.gemini.analyze_watchlists
        analyze_many(self.analyst, [(r, f"mt5:{r.symbol}:{side_word(r.direction)}", "mt5", mt5_context(r, now))
                                    for r in rows if r.market_open and (r.watchlist in wanted or r.alerts)])
        rows.sort(key=lambda r: (-len(r.alerts), "AB-".index(r.watchlist), -r.score.total))
        scan = Mt5Scan(now, int((time.monotonic() - started) * 1000), rows, regimes, errors)
        log.info("varredura MT5 concluída", extra={"data": {
            "linhas": len(rows), "watchlist_a": sum(r.watchlist == "A" for r in rows),
            "alertas": len(scan.alerts), "erros": len(errors), "duracao_s": round(scan.duration_ms / 1000, 1)}})
        return scan

    def _scan_group(self, group: str, direction: int, data: dict[str, dict[str, pd.DataFrame]],
                    spreads: dict[str, float], now: int) -> tuple[Regime, list[Mt5Row]]:
        cfg, sc = group_config(self.cfg, group), self.cfg.score
        short = direction < 0
        frames = {s: {iv: invert_frame(df) if short else df for iv, df in d.items()} for s, d in data.items()}
        bench = cfg.markets.mt5.benchmarks.get(group)
        bench_d1 = frames[bench]["D"] if bench in frames else klines_to_frame([])

        feats: dict[str, Features] = {}
        for symbol, d in frames.items():
            f = compute_features(symbol, d["D"], d["240"], d["60"], bench_d1, None, cfg.indicators, sc)
            if f.daily_candles >= cfg.universe.min_daily_candles or symbol == bench:
                feats[symbol] = f

        above = [f.close_4h > f.ema50_4h for f in feats.values() if is_num(f.close_4h) and is_num(f.ema50_4h)]
        if bench in frames:
            state_path = self.state_dir / f"{group}_{side_word(direction)}.json" if self.state_dir else None
            state = RegimeState.load(state_path) if state_path else RegimeState()
            b = frames[bench]
            regime = evaluate_regime(b["D"], b["240"], b["60"], breadth_pct(above), state, now, cfg.regime)
            if state_path:
                state.save(state_path)
        else:
            regime = Regime("risk_on", None, None, breadth_pct(above), None, False, None,
                            ["Grupo sem ativo de referência: sem filtro de regime"])

        what = f"{GROUP_LABEL.get(group, group)} · {side_word(direction)}"
        footer = stats_lines(self.stats.get((group, direction), {}), what)
        rows = []
        for symbol, f in feats.items():
            real = data[symbol][TRIGGER]
            last_end = int(real["start_ms"].iloc[-1]) + 15 * 60_000
            h1_real = data[symbol]["60"]["close"]
            change = ((float(h1_real.iloc[-1]) / float(h1_real.iloc[-25]) - 1) * 100 if len(h1_real) > 25
                      else float("nan"))
            score = score_features(f, sc)
            row = Mt5Row(symbol, group, direction, float(real["close"].iloc[-1]), change,
                         spreads.get(symbol, float("nan")), f, score, classify(score.total, sc, regime.regime),
                         regime.regime, market_open=now - last_end <= STALE_MS)
            d = frames[symbol]
            if row.watchlist in ("A", "B"):
                plans = entry_plans(d[TRIGGER], d[CONTEXT], score.components, now, cfg, direction)
                row.plans = plan_lines(plans, cfg.setups.common, cfg.exits, footer=footer, trigger_label="15m")
                row.plan_data = [plan_dict(p) for p in plans]
            if row.watchlist == "A" and row.market_open:
                self._signals(row, d, cfg, regime, now)
            rows.append(row)
        return regime, rows

    def _signals(self, row: Mt5Row, d: dict[str, pd.DataFrame], cfg: Any, regime: Regime, now: int) -> None:
        ctx = SignalContext(now, regime.allow_new_entries, regime.regime, {row.symbol: row.spread_pct})
        for raw in evaluate_setups(row.symbol, d[TRIGGER], d[CONTEXT], now, row.score.components, row.score.total,
                                   cfg):
            signal = to_short(raw, cfg.exits) if row.direction < 0 else raw
            problems = check_filters(signal, ctx, cfg.setups.common, cfg.universe.max_spread_pct)
            if problems:
                row.blocked.append((signal, problems))
            else:
                row.alerts.append(signal)


# ---------------------------------------------------------------------------- painel
NEUTRAL_PREFIXES = ("ATR ", "Bandas", "Volume", "Sem ")   # não dependem da direção
WORD_SWAPS = (("acima", "abaixo"), ("subindo", "caindo"), ("superior", "inferior"), ("crescendo", "caindo"),
              ("positivo", "negativo"), ("DI+ > DI−", "DI− > DI+"))


def real_price_reason(text: str, direction: int) -> str:
    """Motivo do score em termos do preço real. Na venda o score é medido no gráfico invertido:
    "Preço acima da EMA50 4H" lá significa "Preço abaixo da EMA50 4H" no gráfico de verdade."""
    text = text.replace("moeda/BTC", "ativo/referência").replace("do BTC", "da referência")
    if direction > 0 or text.startswith(NEUTRAL_PREFIXES):
        return text
    text = re.sub(r"RSI 4H (\d+) entre (\d+) e (\d+)",
                  lambda m: f"RSI 4H {100 - int(m[1])} entre {100 - int(m[3])} e {100 - int(m[2])}", text)
    text = re.sub(r"RSI 4H (\d+) sobrecomprado \(> (\d+)\)",
                  lambda m: f"RSI 4H {100 - int(m[1])} sobrevendido (< {100 - int(m[2])})", text)
    text = re.sub(r"(Retorno \d+d acima da referência \()([+−])",
                  lambda m: m[1] + ("−" if m[2] == "+" else "+"), text)
    text = re.sub(r"CMF 4H (-?[\d.]+) > (-?[\d.]+)",
                  lambda m: f"CMF 4H {-float(m[1]):.2f} < {-float(m[2]):g}", text)
    for i, (a, b) in enumerate(WORD_SWAPS):
        text = text.replace(a, f"\x00{i}a").replace(b, f"\x00{i}b")
    for i, (a, b) in enumerate(WORD_SWAPS):
        text = text.replace(f"\x00{i}a", b).replace(f"\x00{i}b", a)
    return text


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if is_num(value) else None


def alert_text(row: Mt5Row, s: Signal) -> str:
    from bot.signals.plans import _br, fmt_price

    name = {"pullback_tendencia": "Pullback", "rompimento_compressao": "Rompimento", "ote_fibo": "OTE"}[s.setup]
    return (f"🔔 ALERTA {s.side.upper()} {row.symbol.removesuffix('.s')} — {name} disparou no fechamento da vela 15m: "
            f"entrada {fmt_price(s.entry)}, stop {fmt_price(s.stop)} ({_br(s.stop_pct, '.2f')}%), "
            f"alvos {fmt_price(s.tp1)} / {fmt_price(s.tp2)} (R:R {_br(s.rr, '.1f')}). Você decide e executa.")


def mt5_payload(scan: Mt5Scan, sc: Any, max_results: int) -> dict[str, Any]:
    """Evento scanner_run com os ativos do MT5 (uma execução própria no painel)."""
    from bot.scanner.scanner import _iso

    notes = ["MT5 da corretora (somente leitura) — gatilho 15m, contexto 1H; compra e venda"]
    notes += [f"{k}: {r.regime}" for k, r in scan.regimes.items() if r.regime != "risk_on"]
    if scan.errors:
        notes.append(f"Erros de leitura: {', '.join(sorted(scan.errors))}")
    results = []
    for r in scan.rows[:max_results]:
        threshold = sc.watchlist_a_min if r.watchlist == "A" else sc.watchlist_b_min
        if r.watchlist == "A" and r.regime == "neutro":
            threshold += sc.neutral_regime_extra_min
        head = (f"{LABEL_BY_LIST[r.watchlist]} (score ≥ {threshold:g}) — {GROUP_LABEL.get(r.group, r.group)}, "
                f"{side_word(r.direction)}" if r.watchlist != "-" else f"Descartada (score < {sc.watchlist_b_min:g})")
        if not r.market_open:
            head += " — mercado fechado (sem alertas)"
        f, s = r.features, r.score
        flip = (lambda v: 100 - v) if r.direction < 0 else (lambda v: v)   # RSI mostrado no preço real
        blocked = [f"Setup {sig.setup} disparou mas foi barrado: {'; '.join(p)}" for sig, p in r.blocked]
        gem = r.gemini.panel_fields() if r.gemini else {}
        results.append({
            **gem,
            "symbol": r.label,
            "price": r.price,
            "change_24h_pct": _round(r.change_24h_pct, 2),
            "turnover_24h_usdt": 0,
            "score": round(s.total, 1),
            "score_trend": s.components["trend"],
            "score_relative_strength": s.components["relative_strength"],
            "score_volume": s.components["volume"],
            "score_squeeze": s.components["squeeze"],
            "score_derivatives": s.components["derivatives"],
            "score_momentum": s.components["momentum"],
            "penalties": s.penalties,
            "rsi_1h": _round(flip(f.rsi_1h), 1),
            "rsi_4h": _round(flip(f.rsi_4h), 1),
            "atr_pct": _round(f.atr_pct_4h, 2),
            "status": r.status,
            "plans": [*(signal_dict(a) for a in r.alerts), *r.plan_data],
            "reasons": [head, *(alert_text(r, a) for a in r.alerts), *([r.gemini.line()] if r.gemini else []),
                        *r.structure, *blocked, *r.plans,
                        *(real_price_reason(x, r.direction) for x in s.reasons),
                        *(f"Sem dado: {real_price_reason(m, r.direction)}" for m in s.missing[:3])],
        })
    return {
        "run": {
            "run_at": _iso(scan.run_at_ms),
            "regime": "MT5",
            "universe_size": len(scan.rows),
            "candidates": sum(r.watchlist == "A" for r in scan.rows),
            "duration_ms": scan.duration_ms,
            "notes": " | ".join(notes)[:2000],
        },
        "results": results,
    }


def alert_signal_payload(row: Mt5Row, s: Signal) -> dict[str, Any]:
    from bot.signals.engine import signal_payload

    vetoed = row.gemini is not None and row.gemini.verdict.veredito == "vetado"
    payload = signal_payload(s, status="vetado" if vetoed else "alerta")
    payload["symbol"] = row.label
    payload["reason"] = alert_text(row, s) + (f" | {row.gemini.line()}" if row.gemini else "")
    return payload


ASSET_NAMES = {
    "XAUUSD": "Ouro (XAU/USD)", "XAGUSD": "Prata (XAG/USD)", "XPTUSD": "Platina (XPT/USD)", "XCUUSD": "Cobre (XCU/USD)",
    "NAS100": "Nasdaq 100", "SP500": "S&P 500", "US30": "Dow Jones 30", "GER40": "DAX 40 (Alemanha)",
    "UK100": "FTSE 100 (Reino Unido)", "JPN225": "Nikkei 225 (Japão)", "XTIUSD": "Petróleo WTI",
    "XBRUSD": "Petróleo Brent", "XNGUSD": "Gás natural (Henry Hub)",
}


def mt5_context(r: Mt5Row, now_ms: int) -> dict[str, Any]:
    """Entrada do analista Gemini para um ativo do MT5 (intraday)."""
    base = r.symbol.removesuffix(".s")
    s = r.score
    return {
        "ativo": base, "nome": ASSET_NAMES.get(base, f"par de moedas {base[:3]}/{base[3:]}"),
        "grupo": GROUP_LABEL.get(r.group, r.group), "direcao": side_word(r.direction), "operacao": "intraday (15m/1H)",
        "agora": now_brt(now_ms), "lista": r.watchlist, "score": round(s.total, 1), "componentes": s.components,
        "preco": r.price, "variacao_24h_pct": _round(r.change_24h_pct, 2),
        "alertas": [alert_text(r, a) for a in r.alerts], "planos": [p for p in r.plans if p.startswith("Plano")][:2],
    }
