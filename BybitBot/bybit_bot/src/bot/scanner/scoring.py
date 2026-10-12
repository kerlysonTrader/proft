"""Score de oportunidade 0–100 (seção 3 do 03_ESTRATEGIA.md).

Função pura: recebe as Features e o ScoreConfig; devolve pontos por componente,
penalidades e a lista de motivos legíveis ("EMA50 4H acima da EMA200 4H (+7)").
Condição com dado ausente (NaN) não pontua e vira motivo "sem dado".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bot.scanner.features import Features, is_num

COMPONENTS = ("trend", "relative_strength", "volume", "squeeze", "derivatives", "momentum")


@dataclass
class ScoreResult:
    symbol: str
    components: dict[str, float] = field(default_factory=lambda: dict.fromkeys(COMPONENTS, 0.0))
    penalties: float = 0.0
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def raw(self) -> float:
        return sum(self.components.values()) + self.penalties

    @property
    def total(self) -> float:
        return max(0.0, min(100.0, self.raw))


def _fmt(points: float) -> str:
    return f"{points:+g}".replace("-", "−")


def _nan(value: float | None) -> float:
    return float("nan") if value is None else float(value)


def _pct(value: float) -> str:
    return f"{value:+.1f}%".replace(".", ",").replace("-", "−")


class _Scorer:
    def __init__(self, f: Features, sc) -> None:
        self.f, self.sc, self.r = f, sc, ScoreResult(f.symbol)

    def award(self, component: str, ok: bool | None, points: float, text: str, needs: tuple = ()) -> None:
        if any(not is_num(v) for v in needs):
            self.r.missing.append(text)
            return
        if ok:
            self.r.components[component] += points
            self.r.reasons.append(f"{text} ({_fmt(points)})")

    def penalize(self, ok: bool | None, points: float, text: str, needs: tuple = ()) -> None:
        if any(not is_num(v) for v in needs) or not ok:
            return
        self.r.penalties += points
        self.r.reasons.append(f"{text} ({_fmt(points)})")


def score_features(f: Features, sc) -> ScoreResult:
    s = _Scorer(f, sc)
    p = sc.points

    # A. Tendência
    s.award("trend", f.close_4h > f.ema50_4h, p.trend.price_above_ema50_4h,
            "Preço acima da EMA50 4H", (f.close_4h, f.ema50_4h))
    s.award("trend", f.ema50_4h > f.ema200_4h, p.trend.ema50_above_ema200_4h,
            "EMA50 4H acima da EMA200 4H", (f.ema50_4h, f.ema200_4h))
    s.award("trend", f.close_1d > f.ema50_1d, p.trend.price_above_ema50_1d,
            "Preço acima da EMA50 diária", (f.close_1d, f.ema50_1d))
    s.award("trend", f.adx_4h > sc.adx_min and f.plus_di_4h > f.minus_di_4h, p.trend.adx_trend_4h,
            f"ADX 4H {f.adx_4h:.0f} > {sc.adx_min:g} com DI+ > DI−", (f.adx_4h, f.plus_di_4h, f.minus_di_4h))

    # B. Força relativa contra o BTC (ou o ativo de referência do mercado)
    if f.no_benchmark:
        s.r.components["relative_strength"] = sc.relative_strength_neutral_points
        neutral = _fmt(sc.relative_strength_neutral_points)
        s.r.reasons.append(f"Sem ativo de referência: força relativa neutra ({neutral})")
    else:
        _relative_strength(s, f, sc, p)
    _rest_of_score(s, f, sc, p)
    return s.r


def _relative_strength(s: _Scorer, f: Features, sc, p) -> None:
    s.award("relative_strength", f.ret_short - f.btc_ret_short > 0, p.relative_strength.ret_short_vs_btc,
            f"Retorno {sc.rs_short_days}d acima do BTC ({_pct((f.ret_short - f.btc_ret_short) * 100)})",
            (f.ret_short, f.btc_ret_short))
    s.award("relative_strength", f.ret_long - f.btc_ret_long > 0, p.relative_strength.ret_long_vs_btc,
            f"Retorno {sc.rs_long_days}d acima do BTC ({_pct((f.ret_long - f.btc_ret_long) * 100)})",
            (f.ret_long, f.btc_ret_long))
    s.award("relative_strength", f.ratio_btc > f.ratio_btc_ema, p.relative_strength.ratio_above_ema_1d,
            f"Razão moeda/BTC acima da EMA{sc.ratio_ema_period} diária", (f.ratio_btc, f.ratio_btc_ema))


def _rest_of_score(s: _Scorer, f: Features, sc, p) -> None:
    # C. Volume e acumulação
    low, high = sc.volume_ratio_band
    s.award("volume", low <= f.volume_ratio <= high, p.volume.volume_ratio_in_band,
            f"Volume 24h {f.volume_ratio:.1f}× a média (faixa {low:g}–{high:g}×)", (f.volume_ratio,))
    s.award("volume", f.obv_4h > f.obv_ema_4h and f.obv_4h > f.obv_past_4h, p.volume.obv_rising_4h,
            "OBV 4H acima da sua média e subindo", (f.obv_4h, f.obv_ema_4h, f.obv_past_4h))
    s.award("volume", f.cmf_4h > sc.cmf_min, p.volume.cmf_positive_4h,
            f"CMF 4H {f.cmf_4h:.2f} > {sc.cmf_min:g}", (f.cmf_4h,))

    # D. Compressão de volatilidade
    s.award("squeeze", f.bb_width_rank_4h <= sc.bb_width_percentile_max, p.squeeze.bb_width_low_4h,
            f"Bandas de Bollinger 4H comprimidas (percentil {f.bb_width_rank_4h:.0f})", (f.bb_width_rank_4h,))
    s.award("squeeze", f.range_position_4h >= sc.upper_range_fraction, p.squeeze.upper_third_range_4h,
            f"Preço no terço superior do range de {sc.range_lookback_4h} velas 4H", (f.range_position_4h,))
    s.award("squeeze", f.atr_4h < f.atr_avg_4h, p.squeeze.atr_contracting_4h,
            "ATR 4H abaixo da própria média (contração)", (f.atr_4h, f.atr_avg_4h))

    # E. Derivativos (perpétuo linear de mesmo nome)
    d = f.derivatives
    has_data = d is not None and any(is_num(v) for v in (d.oi_change_pct, d.funding_rate_pct, d.long_short_ratio))
    if not has_data:
        s.r.components["derivatives"] = sc.derivatives_neutral_points
        label = "Sem perpétuo listado" if d is None else "Dados de derivativos indisponíveis"
        s.r.reasons.append(f"{label}: pontuação neutra ({_fmt(sc.derivatives_neutral_points)})")
    else:
        oi, funding, ls = (_nan(d.oi_change_pct), _nan(d.funding_rate_pct), _nan(d.long_short_ratio))
        s.award("derivatives", oi > sc.oi_rise_min_pct and f.change_24h_pct < sc.oi_price_rise_max_pct,
                p.derivatives.oi_rising_price_flat,
                f"Open interest 24h {_pct(oi)} com preço {_pct(f.change_24h_pct)}", (oi, f.change_24h_pct))
        lo_f, hi_f = sc.funding_ok_range_pct
        s.award("derivatives", lo_f <= funding <= hi_f, p.derivatives.funding_ok,
                f"Funding {funding:.4f}% sem superaquecimento", (funding,))
        s.award("derivatives", ls <= sc.max_long_short_ratio, p.derivatives.long_short_ok,
                f"Razão long/short {ls:.2f} ≤ {sc.max_long_short_ratio:g}", (ls,))

    # F. Momentum
    r_lo, r_hi = sc.rsi_band_4h
    s.award("momentum", r_lo <= f.rsi_4h <= r_hi, p.momentum.rsi_in_band_4h,
            f"RSI 4H {f.rsi_4h:.0f} entre {r_lo:g} e {r_hi:g}", (f.rsi_4h,))
    s.award("momentum", f.macd_hist_4h > 0 and f.macd_hist_4h > f.macd_hist_prev_4h, p.momentum.macd_hist_rising_4h,
            "Histograma MACD 4H positivo e crescendo", (f.macd_hist_4h, f.macd_hist_prev_4h))

    # Penalidades
    pen = sc.penalties
    s.penalize(f.rsi_4h > sc.rsi_overbought_4h, pen.rsi_overbought_4h,
               f"RSI 4H {f.rsi_4h:.0f} sobrecomprado (> {sc.rsi_overbought_4h:g})", (f.rsi_4h,))
    stretch = (f.close_4h / f.ema20_4h - 1) * 100 if is_num(f.ema20_4h) and f.ema20_4h else float("nan")
    s.penalize(stretch > sc.max_dist_from_ema20_4h_pct, pen.stretched_from_ema20_4h,
               f"Preço {stretch:.1f}% acima da EMA20 4H (esticado)", (stretch,))
    s.penalize(f.volume_ratio > sc.pump_volume_ratio, pen.pump_volume,
               f"Volume 24h {f.volume_ratio:.1f}× a média (pump suspeito)", (f.volume_ratio,))
    if d is not None:
        funding = _nan(d.funding_rate_pct)
        s.penalize(funding > sc.funding_hot_pct, pen.funding_hot, f"Funding {funding:.4f}% superaquecido", (funding,))
    s.penalize(f.max_upper_wick_fraction_1d > sc.upper_wick_max_fraction, pen.upper_wick_rejection_1d,
               f"Pavio superior de {f.max_upper_wick_fraction_1d * 100:.0f}% do range numa das últimas "
               f"{sc.wick_lookback_days} velas diárias (rejeição)", (f.max_upper_wick_fraction_1d,))


def classify(total: float, sc, regime: str) -> str:
    """'A', 'B' ou '-' (descartada). Em regime neutro a Watchlist A exige score maior."""
    a_min = sc.watchlist_a_min + (sc.neutral_regime_extra_min if regime == "neutro" else 0)
    if total >= a_min:
        return "A"
    if total >= sc.watchlist_b_min:
        return "B"
    return "-"
