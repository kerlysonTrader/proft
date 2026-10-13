"""Varredura completa: universo -> velas (em paralelo) -> regime -> score -> Watchlist A/B.

Status enviados ao painel: A = "watch" (elegível para gatilho), B = "watch_b" (só monitorar),
descartada = "ignored". O primeiro motivo de cada linha diz a classificação em português.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from bot.ai.gemini_analyst import Analysis, GeminiAnalyst, analyze_many, now_brt
from bot.config import with_profile
from bot.data.market_data import MarketData
from bot.logging_setup import get_logger
from bot.markets.stats import SetupStats, stats_lines
from bot.scanner.features import Features, compute_features, is_num
from bot.scanner.regime import Regime, RegimeState, breadth_pct, evaluate_regime
from bot.scanner.scoring import ScoreResult, classify, score_features
from bot.scanner.universe import UniverseCoin, build_universe
from bot.signals.base import TF_LABEL
from bot.signals.feed import FeedEvent, FeedState, plan_events, structure_events
from bot.signals.plans import entry_plans, plan_dict, plan_lines
from bot.signals.structure import StructureParams, structure_bundle

log = get_logger("scanner")

STRUCTURE_CANDLES = 400   # velas de 15m para a leitura de estrutura (MME200 + pivôs)
STATUS_BY_LIST = {"A": "watch", "B": "watch_b", "-": "ignored"}
LABEL_BY_LIST = {"A": "Watchlist A", "B": "Watchlist B", "-": "Descartada"}


@dataclass
class CoinResult:
    coin: UniverseCoin
    features: Features
    score: ScoreResult
    watchlist: str = "-"
    note: str | None = None
    plans: list[str] = field(default_factory=list)
    plan_data: list[dict[str, Any]] = field(default_factory=list)
    gemini: Analysis | None = None
    structure: list[str] = field(default_factory=list)
    structure_data: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        return STATUS_BY_LIST[self.watchlist]


@dataclass
class ScanResult:
    run_at_ms: int
    duration_ms: int
    regime: Regime
    results: list[CoinResult]
    rejected: Counter = field(default_factory=Counter)
    errors: dict[str, str] = field(default_factory=dict)
    events: list[FeedEvent] = field(default_factory=list)   # feed da aba Sinais

    @property
    def universe_size(self) -> int:
        return len(self.results)

    @property
    def candidates(self) -> int:
        return sum(r.watchlist == "A" for r in self.results)


@dataclass
class _CoinData:
    d1: pd.DataFrame
    h4: pd.DataFrame
    h1: pd.DataFrame
    derivatives: Any
    m15: pd.DataFrame | None = None


class Scanner:
    def __init__(self, md: MarketData, registry: Any, config: Any, state: RegimeState,
                 now_ms: Callable[[], int] | None = None, analyst: GeminiAnalyst | None = None,
                 stats: dict[str, SetupStats] | None = None, feed_state: FeedState | None = None) -> None:
        self.stats = stats or {}
        self.feed_state = feed_state
        self.md, self.registry, self.cfg, self.state = md, registry, config, state
        self.analyst = analyst
        self._now_ms = now_ms or md.client.now_ms

    def _fetch(self, symbol: str, d1_limit: int) -> _CoinData:
        c = self.cfg.score.candles
        return _CoinData(
            d1=self.md.klines(symbol, "D", limit=d1_limit),
            h4=self.md.klines(symbol, "240", limit=c.h4),
            h1=self.md.klines(symbol, "60", limit=c.h1),
            derivatives=self.md.derivatives(symbol),
            m15=self.md.klines(symbol, "15", limit=STRUCTURE_CANDLES),
        )

    def run(self) -> ScanResult:
        cfg, sc = self.cfg, self.cfg.score
        started = time.monotonic()
        run_at = self._now_ms()
        btc = cfg.regime.btc_symbol

        universe = build_universe(self.md.spot_tickers(), self.registry, cfg.universe, cfg.bybit.quote,
                                  always=(btc,))
        self.md.has_perpetual(btc)  # aquece o cache dos tickers lineares antes do paralelo
        btc_d1_limit = min(1000, max(sc.candles.d1, cfg.regime.daily_ema * 3))  # aquecimento da EMA200 diária
        btc_data = self._fetch(btc, btc_d1_limit)

        coins = [c for c in universe.coins if c.symbol != btc]
        data: dict[str, _CoinData] = {btc: btc_data}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=sc.workers) as pool:
            futures = {c.symbol: pool.submit(self._fetch, c.symbol, sc.candles.d1) for c in coins}
            for symbol, future in futures.items():
                try:
                    data[symbol] = future.result()
                except Exception as exc:  # uma moeda com erro não derruba a varredura
                    errors[symbol] = f"{type(exc).__name__}: {exc}"
                    log.warning("falha ao buscar dados", extra={"symbol": symbol, "data": {"error": str(exc)}})

        rejected = Counter(universe.rejected)
        scored: list[tuple[UniverseCoin, Features]] = []
        for coin in universe.coins:
            if coin.symbol not in data:
                rejected["erro ao buscar dados"] += 1
                continue
            d = data[coin.symbol]
            f = compute_features(coin.symbol, d.d1, d.h4, d.h1, btc_data.d1, d.derivatives, cfg.indicators, sc)
            if f.daily_candles < cfg.universe.min_daily_candles and coin.symbol != btc:
                rejected["histórico curto (< velas diárias mínimas)"] += 1
                continue
            scored.append((coin, f))

        above = [f.close_4h > f.ema50_4h for _, f in scored if is_num(f.close_4h) and is_num(f.ema50_4h)]
        regime = evaluate_regime(btc_data.d1, btc_data.h4, btc_data.h1, breadth_pct(above), self.state,
                                 run_at, cfg.regime)

        results = []
        for coin, f in scored:
            score = score_features(f, sc)
            result = CoinResult(coin, f, score, classify(score.total, sc, regime.regime))
            results.append(result)
        self._check_depth([r for r in results if r.watchlist in ("A", "B")])
        for r in results:
            if r.watchlist in ("A", "B"):
                d = data[r.coin.symbol]
                plans = self._plans(d, r, run_at)
                r.plan_data = [plan_dict(p) for p in plans]
        params = StructureParams.from_config(cfg.setups.estrutura, cfg.indicators.atr_period)
        for r in results:
            d = data[r.coin.symbol]
            if d.m15 is not None:
                r.structure, r.structure_data = structure_bundle({"15m": d.m15, "1H": d.h1, "4H": d.h4}, params)
        analyze_many(self.analyst, [(r, f"cripto:{r.coin.symbol}", "cripto", crypto_context(r, regime, run_at))
                                    for r in results if r.watchlist in cfg.gemini.analyze_watchlists])
        results.sort(key=lambda r: r.score.total, reverse=True)

        duration = int((time.monotonic() - started) * 1000)
        scan = ScanResult(run_at, duration, regime, results, rejected, errors,
                          events=self._events(results, data, run_at))
        log.info("varredura concluída", extra={"data": {
            "regime": regime.regime, "universo": scan.universe_size, "watchlist_a": scan.candidates,
            "watchlist_b": sum(r.watchlist == "B" for r in results), "duracao_s": round(duration / 1000, 1),
            "erros": len(errors)}})
        return scan

    def _events(self, results: list[CoinResult], data: dict[str, _CoinData], now: int) -> list[FeedEvent]:
        """Feed da aba Sinais: gatilhos de estrutura (compra e venda, p/ perpétuo) e mudanças dos planos."""
        events: list[FeedEvent] = []
        for r in results:
            d = data.get(r.coin.symbol)
            if d is None or d.m15 is None:
                continue
            sym = r.coin.symbol
            events += structure_events("cripto", sym, sym, d.m15, d.h1, now, self.cfg,
                                       scores={1: r.score.total}, gemini={1: r.gemini})
            if self.feed_state is not None and r.plan_data:
                events += plan_events("cripto", sym, 1, r.plan_data, self.feed_state, now, r.score.total, r.gemini)
        return events

    def _plans(self, d: _CoinData, r: CoinResult, run_at: int) -> list:
        """Planos no perfil do scanner (day trade 15m/1H por padrão) com a estatística do backtest."""
        prof = self.cfg.markets.scanner_cripto
        pcfg = with_profile(self.cfg, prof.trigger_interval, prof.context_interval, prof.stop_pct_range)
        frames = {"15": d.m15, "60": d.h1, "240": d.h4}
        trig, ctx = frames[prof.trigger_interval], frames[prof.context_interval]
        if trig is None or ctx is None:
            r.plans = ["Plano: sem velas do tempo gráfico do gatilho nesta varredura"]
            return []
        plans = entry_plans(trig, ctx, r.score.components, run_at, pcfg)
        tf = TF_LABEL[prof.trigger_interval]
        r.plans = plan_lines(plans, pcfg.setups.common, pcfg.exits,
                             footer=stats_lines(self.stats, "cripto spot · compra"), trigger_label=tf)
        return plans

    def _check_depth(self, finalists: list[CoinResult]) -> None:
        """Profundidade do livro só para os finalistas (A/B). Falhou -> descartada."""
        u = self.cfg.universe
        for r in finalists:
            try:
                depth = self.md.orderbook(r.coin.symbol).bid_depth_quote(u.depth_window_pct)
            except Exception as exc:
                r.watchlist, r.note = "-", f"livro de ofertas indisponível ({type(exc).__name__})"
                continue
            if depth < u.min_bid_depth_2pct_usdt:
                r.watchlist = "-"
                r.note = (f"Profundidade de compra até −{u.depth_window_pct:g}%: {depth:,.0f} USDT "
                          f"(mínimo {u.min_bid_depth_2pct_usdt:,.0f})")


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if is_num(value) else None


def scanner_payload(scan: ScanResult, sc: Any, max_results: int) -> dict[str, Any]:
    """Payload do evento scanner_run (05_DASHBOARD_E_INTEGRACAO.md)."""
    notes = list(scan.regime.reasons)
    if scan.rejected:
        top = ", ".join(f"{reason}: {n}" for reason, n in scan.rejected.most_common(6))
        notes.append(f"Fora do universo — {top}")
    if scan.errors:
        notes.append(f"Erros de dados: {len(scan.errors)} moedas")

    results = []
    for r in scan.results[:max_results]:
        threshold = sc.watchlist_a_min if r.watchlist == "A" else sc.watchlist_b_min
        if r.watchlist == "A" and scan.regime.regime == "neutro":
            threshold += sc.neutral_regime_extra_min
        head = (f"{LABEL_BY_LIST[r.watchlist]} (score ≥ {threshold:g})" if r.watchlist != "-"
                else f"Descartada: {r.note}" if r.note else f"Descartada (score < {sc.watchlist_b_min:g})")
        f, s = r.features, r.score
        gem = r.gemini.panel_fields() if r.gemini else {}
        results.append({
            **gem,
            "symbol": r.coin.symbol,
            "price": r.coin.price,
            "change_24h_pct": _round(r.coin.change_24h_pct, 2),
            "turnover_24h_usdt": round(r.coin.turnover_24h_usdt),
            "score": round(s.total, 1),
            "score_trend": s.components["trend"],
            "score_relative_strength": s.components["relative_strength"],
            "score_volume": s.components["volume"],
            "score_squeeze": s.components["squeeze"],
            "score_derivatives": s.components["derivatives"],
            "score_momentum": s.components["momentum"],
            "penalties": s.penalties,
            "rsi_1h": _round(f.rsi_1h, 1),
            "rsi_4h": _round(f.rsi_4h, 1),
            "atr_pct": _round(f.atr_pct_4h, 2),
            "status": r.status,
            "plans": r.plan_data,
            "structure": r.structure_data,
            "reasons": [head, *r.structure, *r.plans, *s.reasons, *(f"Sem dado: {m}" for m in s.missing[:3])],
        })
    return {
        "run": {
            "run_at": _iso(scan.run_at_ms),
            "regime": scan.regime.regime,
            "universe_size": scan.universe_size,
            "candidates": scan.candidates,
            "duration_ms": scan.duration_ms,
            "notes": " | ".join(notes)[:2000],
        },
        "results": results,
    }


def crypto_context(r: CoinResult, regime: Regime, now_ms: int) -> dict[str, Any]:
    """Entrada do analista Gemini (seção 5): métricas do score, indicadores, preço e derivativos."""
    f, s, d = r.features, r.score, r.features.derivatives
    return {
        "simbolo": r.coin.symbol, "moeda": r.coin.symbol.removesuffix("USDT"), "direcao": "compra",
        "agora": now_brt(now_ms), "regime_btc": regime.regime, "lista": r.watchlist,
        "score": round(s.total, 1), "componentes": s.components, "penalidades": s.penalties,
        "preco": r.coin.price, "variacao_24h_pct": _round(r.coin.change_24h_pct, 2),
        "volume_24h_usdt": round(r.coin.turnover_24h_usdt),
        "rsi_1h": _round(f.rsi_1h, 1), "rsi_4h": _round(f.rsi_4h, 1),
        "atr_4h_pct": _round(f.atr_pct_4h, 2),
        "funding_pct": _round(d.funding_rate_pct, 4) if d else None,
        "open_interest_24h_pct": _round(d.oi_change_pct, 2) if d else None,
        "planos": r.plans[:2],
    }
