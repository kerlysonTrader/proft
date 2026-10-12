"""Modelos pydantic do config.yaml.

Todo número da estratégia vem daqui. Campos desconhecidos são rejeitados
(extra="forbid") para que um erro de digitação no YAML não passe em silêncio.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def resolve_path(path: str | Path) -> Path:
    """Caminhos relativos do config são relativos à pasta bybit_bot."""
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path

Mode = Literal["paper", "demo", "live"]
SetupName = Literal["pullback_tendencia", "rompimento_compressao", "ote_fibo",
                    "estrutura_bos", "estrutura_choch", "lt_rompimento", "cunha", "medias_cruzamento"]
OnchainRule = Literal["S1", "F2", "F3", "R2", "R3"]


class ConfigError(Exception):
    """Configuração inválida ou ausente."""


class LiveModeNotConfirmedError(ConfigError):
    """Modo live sem a confirmação explícita CONFIRM_LIVE=SIM."""


def _check_band(value: tuple[float, float]) -> tuple[float, float]:
    low, high = value
    if low >= high:
        raise ValueError(f"faixa inválida {list(value)}: o primeiro valor deve ser menor que o segundo")
    return value


Band = Annotated[tuple[float, float], AfterValidator(_check_band)]
Pct = Annotated[float, Field(ge=0, le=100)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegInt = Annotated[int, Field(ge=0)]
Factor = Annotated[float, Field(gt=0, le=1)]


class StrictModel(BaseModel):
    # protected_namespaces=() libera campos como "model_screening" do Gemini.
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


# --------------------------------------------------------------------------- bybit
class RestUrls(StrictModel):
    live: str
    demo: str

    @field_validator("live", "demo")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("a URL REST deve começar com https://")
        return v.rstrip("/")


class BybitConfig(StrictModel):
    # Só spot: o projeto opera sem alavancagem. Derivativos exigem nova fase validada.
    category: Literal["spot"]
    quote: Literal["USDT"]
    rest_url: RestUrls
    ws_public_url: str
    recv_window_ms: Annotated[int, Field(ge=1000, le=60000)]
    max_requests_per_second: Annotated[float, Field(gt=0, le=20)]
    http_timeout_seconds: PositiveFloat
    max_retries: Annotated[int, Field(ge=0, le=10)]
    backoff_base_seconds: PositiveFloat
    backoff_max_seconds: PositiveFloat
    time_sync_minutes: PositiveFloat

    @model_validator(mode="after")
    def _backoff(self) -> BybitConfig:
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ValueError("backoff_max_seconds deve ser >= backoff_base_seconds")
        return self


class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]


KlineInterval = Literal["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W"]


class CacheTtlConfig(StrictModel):
    tickers: PositiveFloat
    orderbook: PositiveFloat
    derivatives: PositiveFloat
    instruments: PositiveFloat


class HistoryConfig(StrictModel):
    db_path: str
    months: Annotated[int, Field(ge=1, le=60)]
    top_n: Annotated[int, Field(ge=1, le=300)]
    intervals: list[KlineInterval]

    @field_validator("intervals")
    @classmethod
    def _not_empty(cls, v: list[str]) -> list[str]:
        if not v or len(set(v)) != len(v):
            raise ValueError("history.intervals deve ter intervalos sem repetição")
        return v


class MarketDataConfig(StrictModel):
    db_path: str
    kline_page_limit: Annotated[int, Field(ge=1, le=1000)]
    kline_close_grace_seconds: NonNegFloat
    orderbook_depth: Annotated[int, Field(ge=1, le=200)]
    derivatives_period: Literal["5min", "15min", "30min", "1h", "4h", "1d"]
    oi_change_hours: PositiveInt
    cache_ttl_seconds: CacheTtlConfig
    history: HistoryConfig


Direction = Literal["long", "short"]


class CryptoPerpConfig(StrictModel):
    enabled: bool
    directions: list[Direction]
    fee_rate_per_side: Annotated[float, Field(ge=0, lt=0.01)]
    history_db: str


class Mt5Config(StrictModel):
    enabled: bool
    server_utc_offset_hours: Annotated[int, Field(ge=-12, le=14)]
    history_db: str
    max_bars: Annotated[int, Field(ge=1000, le=10_000_000)]
    directions: list[Direction]
    spread_cost_multiplier: NonNegFloat
    commission_per_side_pct: NonNegFloat
    groups: dict[str, list[str]]
    benchmarks: dict[str, str]
    stop_pct_range: dict[str, tuple[PositiveFloat, PositiveFloat]] = {}

    @model_validator(mode="after")
    def _benchmarks_in_groups(self) -> Mt5Config:
        for group, symbol in self.benchmarks.items():
            if group not in self.groups:
                raise ValueError(f"markets.mt5.benchmarks: grupo desconhecido '{group}'")
            if symbol not in self.groups[group]:
                raise ValueError(f"markets.mt5.benchmarks: {symbol} não está no grupo {group}")
        for group, (low, high) in self.stop_pct_range.items():
            if group not in self.groups:
                raise ValueError(f"markets.mt5.stop_pct_range: grupo desconhecido '{group}'")
            if low >= high:
                raise ValueError(f"markets.mt5.stop_pct_range.{group}: mínimo deve ser menor que o máximo")
        return self


class MarketsConfig(StrictModel):
    cripto_perp: CryptoPerpConfig
    mt5: Mt5Config


class IndicatorsConfig(StrictModel):
    ema_short: PositiveInt
    ema_mid: PositiveInt
    ema_long: PositiveInt
    rsi_period: PositiveInt
    atr_period: PositiveInt
    atr_avg_period: PositiveInt
    adx_period: PositiveInt
    macd_fast: PositiveInt
    macd_slow: PositiveInt
    macd_signal: PositiveInt
    bollinger_period: Annotated[int, Field(ge=2)]
    bollinger_std: PositiveFloat
    bb_width_lookback: Annotated[int, Field(ge=2)]
    cmf_period: PositiveInt
    obv_ema_period: PositiveInt
    volume_avg_period: PositiveInt

    @model_validator(mode="after")
    def _coherence(self) -> IndicatorsConfig:
        if not self.ema_short < self.ema_mid < self.ema_long:
            raise ValueError("as EMAs devem obedecer ema_short < ema_mid < ema_long")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast deve ser menor que macd_slow")
        return self


class ScheduleConfig(StrictModel):
    universe_and_score_minutes: PositiveInt
    entry_triggers_minutes: PositiveInt
    position_management_minutes: PositiveInt
    heartbeat_seconds: PositiveInt


# --------------------------------------------------------------------------- scanner
class UniverseConfig(StrictModel):
    min_turnover_24h_usdt: PositiveFloat
    max_spread_pct: PositiveFloat
    min_bid_depth_2pct_usdt: NonNegFloat
    depth_window_pct: PositiveFloat
    min_daily_candles: PositiveInt
    max_change_24h_pct: float
    min_change_24h_pct: float
    exclude_bases: list[str]
    exclude_suffixes: list[str]
    blacklist: list[str]

    @model_validator(mode="after")
    def _change_range(self) -> UniverseConfig:
        if self.min_change_24h_pct >= self.max_change_24h_pct:
            raise ValueError("min_change_24h_pct deve ser menor que max_change_24h_pct")
        return self


class RegimeConfig(StrictModel):
    btc_symbol: str
    daily_ema: PositiveInt
    h4_fast_ema: PositiveInt
    h4_slow_ema: PositiveInt
    min_breadth_pct: Pct
    circuit_breaker_btc_drop_24h_pct: PositiveFloat
    circuit_breaker_pause_hours: PositiveFloat

    @model_validator(mode="after")
    def _emas(self) -> RegimeConfig:
        if self.h4_fast_ema >= self.h4_slow_ema:
            raise ValueError("h4_fast_ema deve ser menor que h4_slow_ema")
        return self


class ScoreWeights(StrictModel):
    trend: NonNegInt
    relative_strength: NonNegInt
    volume: NonNegInt
    squeeze: NonNegInt
    derivatives: NonNegInt
    momentum: NonNegInt

    @model_validator(mode="after")
    def _sum_100(self) -> ScoreWeights:
        total = sum(self.model_dump().values())
        if total != 100:
            raise ValueError(f"a soma dos pesos do score deve ser 100 (está {total})")
        return self


class TrendPoints(StrictModel):
    price_above_ema50_4h: NonNegFloat
    ema50_above_ema200_4h: NonNegFloat
    price_above_ema50_1d: NonNegFloat
    adx_trend_4h: NonNegFloat


class RelativeStrengthPoints(StrictModel):
    ret_short_vs_btc: NonNegFloat
    ret_long_vs_btc: NonNegFloat
    ratio_above_ema_1d: NonNegFloat


class VolumePoints(StrictModel):
    volume_ratio_in_band: NonNegFloat
    obv_rising_4h: NonNegFloat
    cmf_positive_4h: NonNegFloat


class SqueezePoints(StrictModel):
    bb_width_low_4h: NonNegFloat
    upper_third_range_4h: NonNegFloat
    atr_contracting_4h: NonNegFloat


class DerivativesPoints(StrictModel):
    oi_rising_price_flat: NonNegFloat
    funding_ok: NonNegFloat
    long_short_ok: NonNegFloat


class MomentumPoints(StrictModel):
    rsi_in_band_4h: NonNegFloat
    macd_hist_rising_4h: NonNegFloat


class ScorePoints(StrictModel):
    trend: TrendPoints
    relative_strength: RelativeStrengthPoints
    volume: VolumePoints
    squeeze: SqueezePoints
    derivatives: DerivativesPoints
    momentum: MomentumPoints


NonPosFloat = Annotated[float, Field(le=0)]


class ScorePenalties(StrictModel):
    rsi_overbought_4h: NonPosFloat
    stretched_from_ema20_4h: NonPosFloat
    pump_volume: NonPosFloat
    funding_hot: NonPosFloat
    upper_wick_rejection_1d: NonPosFloat


class ScoreCandles(StrictModel):
    d1: Annotated[int, Field(ge=50, le=1000)]
    h4: Annotated[int, Field(ge=50, le=1000)]
    h1: Annotated[int, Field(ge=50, le=1000)]


class ScoreConfig(StrictModel):
    watchlist_a_min: Pct
    watchlist_b_min: Pct
    neutral_regime_extra_min: NonNegFloat
    weights: ScoreWeights
    volume_ratio_band: Band
    pump_volume_ratio: PositiveFloat
    bb_width_percentile_max: Pct
    rsi_band_4h: Band
    rsi_overbought_4h: Pct
    max_dist_from_ema20_4h_pct: PositiveFloat
    funding_ok_range_pct: Band
    funding_hot_pct: float
    max_long_short_ratio: PositiveFloat
    derivatives_neutral_points: NonNegFloat
    relative_strength_neutral_points: NonNegFloat  # mercados sem ativo de referência
    points: ScorePoints
    penalties: ScorePenalties
    adx_min: NonNegFloat
    rs_short_days: PositiveInt
    rs_long_days: PositiveInt
    ratio_ema_period: PositiveInt
    obv_slope_bars: PositiveInt
    cmf_min: float
    range_lookback_4h: Annotated[int, Field(ge=2)]
    upper_range_fraction: Annotated[float, Field(gt=0, lt=1)]
    oi_rise_min_pct: float
    oi_price_rise_max_pct: float
    upper_wick_max_fraction: Annotated[float, Field(gt=0, le=1)]
    wick_lookback_days: PositiveInt
    candles: ScoreCandles
    workers: Annotated[int, Field(ge=1, le=16)]

    @model_validator(mode="after")
    def _points_match_weights(self) -> ScoreConfig:
        for component, weight in self.weights.model_dump().items():
            total = sum(getattr(self.points, component).model_dump().values())
            if abs(total - weight) > 1e-9:
                raise ValueError(f"score.points.{component} soma {total:g}, mas weights.{component} = {weight}")
        if self.rs_short_days >= self.rs_long_days:
            raise ValueError("rs_short_days deve ser menor que rs_long_days")
        return self

    @model_validator(mode="after")
    def _coherence(self) -> ScoreConfig:
        if self.watchlist_a_min <= self.watchlist_b_min:
            raise ValueError("watchlist_a_min deve ser maior que watchlist_b_min")
        if self.pump_volume_ratio <= self.volume_ratio_band[1]:
            raise ValueError("pump_volume_ratio deve ser maior que o topo de volume_ratio_band")
        if not (0 <= self.rsi_band_4h[0] and self.rsi_band_4h[1] <= 100):
            raise ValueError("rsi_band_4h deve ficar entre 0 e 100")
        if self.rsi_overbought_4h <= self.rsi_band_4h[1]:
            raise ValueError("rsi_overbought_4h deve ser maior que o topo de rsi_band_4h")
        if self.funding_hot_pct <= self.funding_ok_range_pct[1]:
            raise ValueError("funding_hot_pct deve ser maior que o topo de funding_ok_range_pct")
        if self.derivatives_neutral_points > self.weights.derivatives:
            raise ValueError("derivatives_neutral_points não pode passar do peso de derivatives")
        return self


# --------------------------------------------------------------------------- setups
class PullbackConfig(StrictModel):
    min_trend_points: NonNegFloat
    rsi_touch_band_1h: Band
    order_valid_candles_1h: PositiveInt
    stop_atr_buffer: NonNegFloat
    pullback_lookback_1h: Annotated[int, Field(ge=2)]
    entry_tolerance_pct: NonNegFloat
    min_body_fraction: Annotated[float, Field(gt=0, le=1)]


class BreakoutConfig(StrictModel):
    min_squeeze_points: NonNegFloat
    range_lookback_4h: PositiveInt
    breakout_volume_ratio: PositiveFloat
    retest_offset_pct: NonNegFloat
    order_valid_candles_1h: PositiveInt
    stop_atr_mult: PositiveFloat
    min_stop_atr: NonNegFloat


class OteFiboConfig(StrictModel):
    swing_bars: PositiveInt
    min_leg_atr: PositiveFloat
    ote_start: Annotated[float, Field(gt=0, lt=1)]
    ote_end: Annotated[float, Field(gt=0, lt=1)]
    displacement_atr: PositiveFloat
    use_order_block: bool
    ob_lookback: PositiveInt
    stop_atr_buffer: NonNegFloat
    tp1_level: Annotated[float, Field(ge=0, lt=1)]
    tp2_level: Annotated[float, Field(ge=0, lt=1)]
    tp3_extension: Annotated[float, Field(gt=1)]
    entry_tolerance_pct: NonNegFloat
    order_valid_candles_1h: PositiveInt

    @model_validator(mode="after")
    def _zone(self) -> OteFiboConfig:
        if self.ote_start >= self.ote_end:
            raise ValueError("ote_start deve ser menor que ote_end")
        if self.tp2_level > self.tp1_level:
            raise ValueError("tp2_level deve ficar mais perto do topo (menor) que tp1_level")
        return self


class CommonSetupConfig(StrictModel):
    min_rr_tp2: PositiveFloat
    min_stop_pct: PositiveFloat
    max_stop_pct: PositiveFloat
    reentry_cooldown_hours: NonNegFloat

    @model_validator(mode="after")
    def _stops(self) -> CommonSetupConfig:
        if self.min_stop_pct >= self.max_stop_pct:
            raise ValueError("min_stop_pct deve ser menor que max_stop_pct")
        return self


class StructureSetupConfig(StrictModel):
    pivot_bars: Annotated[int, Field(ge=1, le=20)]
    line_tolerance_atr: NonNegFloat
    min_line_touches: Annotated[int, Field(ge=2, le=6)]
    ema_fast: PositiveInt
    ema_slow: PositiveInt
    ema_mid: PositiveInt
    ema_long: PositiveInt
    context: Literal["dow_e_media", "dow", "media"]
    stop_atr_buffer: NonNegFloat
    min_stop_atr: NonNegFloat
    entry_tolerance_pct: NonNegFloat
    order_valid_candles: PositiveInt

    @model_validator(mode="after")
    def _emas(self) -> StructureSetupConfig:
        if not self.ema_fast < self.ema_slow < self.ema_mid < self.ema_long:
            raise ValueError("setups.estrutura: médias devem ser rápida < lenta < média < longa")
        return self


class SetupsConfig(StrictModel):
    enabled: list[SetupName]
    require_watchlist: Literal["A", "B", "todas"] = "A"   # quem pode gerar sinal
    trigger_interval: Literal["15", "60"]     # tempo gráfico do gatilho (15 = intraday)
    context_interval: Literal["60", "240"]    # tempo gráfico de contexto dos setups
    pullback_tendencia: PullbackConfig
    rompimento_compressao: BreakoutConfig
    ote_fibo: OteFiboConfig
    estrutura: StructureSetupConfig
    common: CommonSetupConfig

    @field_validator("enabled")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("setups.enabled tem nomes repetidos")
        return v

    @model_validator(mode="after")
    def _intervals(self) -> SetupsConfig:
        if int(self.context_interval) <= int(self.trigger_interval):
            raise ValueError("context_interval deve ser maior que trigger_interval")
        return self


# --------------------------------------------------------------------------- gemini / risco / saídas
class GeminiConfig(StrictModel):
    enabled: bool
    calls_enabled: bool = False
    provider: Literal["vertex", "ai_studio"]
    vertex_project: str = "bybit-scanner-bot"
    vertex_location: str = "global"
    model_screening: str
    model_final: str
    use_google_search_grounding: bool
    timeout_seconds: PositiveFloat
    cache_hours: NonNegFloat
    max_calls_per_day: NonNegInt = 30
    analyze_watchlists: list[Literal["A", "B"]] = ["A"]
    on_failure: Literal["cautela", "fail_closed"]
    unlock_lookahead_days: NonNegInt


class RiskConfig(StrictModel):
    risk_per_trade_pct: Annotated[float, Field(gt=0, le=5)]
    neutral_regime_risk_factor: Factor
    caution_risk_factor: Factor
    max_open_positions: PositiveInt
    max_open_positions_neutral: NonNegInt
    max_exposure_per_coin_pct: Annotated[float, Field(gt=0, le=100)]
    max_total_exposure_pct: Annotated[float, Field(gt=0, le=100)]  # sem alavancagem: nunca acima de 100 %
    max_positions_per_sector: PositiveInt
    daily_loss_limit_pct: PositiveFloat
    max_consecutive_losses: PositiveInt
    consecutive_losses_pause_hours: NonNegFloat
    weekly_drawdown_limit_pct: PositiveFloat
    max_drawdown_from_peak_pct: PositiveFloat
    min_order_notional_usdt: PositiveFloat
    sectors: dict[str, str]

    @model_validator(mode="after")
    def _coherence(self) -> RiskConfig:
        if self.max_open_positions_neutral > self.max_open_positions:
            raise ValueError("max_open_positions_neutral não pode passar de max_open_positions")
        if self.max_exposure_per_coin_pct > self.max_total_exposure_pct:
            raise ValueError("max_exposure_per_coin_pct não pode passar de max_total_exposure_pct")
        return self


class ExitsConfig(StrictModel):
    tp1_r: PositiveFloat
    tp1_close_fraction: Annotated[float, Field(gt=0, le=1)]   # 1 = alvo único (fecha tudo no TP1)
    move_stop_to_breakeven_after_tp1: bool
    mode_after_tp1: Literal["trailing", "fixed_tp2"]
    tp2_r: PositiveFloat
    trailing_lookback_candles_1h: PositiveInt
    trailing_atr_buffer: NonNegFloat
    time_stop_hours: PositiveFloat
    time_stop_min_r: float
    invalidation_close_below_ema50_4h: bool

    @model_validator(mode="after")
    def _targets(self) -> ExitsConfig:
        if self.tp2_r <= self.tp1_r:
            raise ValueError("tp2_r deve ser maior que tp1_r")
        return self


class CostsConfig(StrictModel):
    fee_rate_per_side: Annotated[float, Field(ge=0, lt=0.01)]
    backtest_slippage_pct: NonNegFloat


class BacktestCandles(StrictModel):
    h1: Annotated[int, Field(ge=100, le=1000)]
    h4: Annotated[int, Field(ge=100, le=1000)]
    d1_btc: Annotated[int, Field(ge=200, le=1000)]


class WalkForwardConfig(StrictModel):
    train_months: PositiveInt
    test_months: PositiveInt
    step_months: PositiveInt


class GateConfig(StrictModel):
    min_trades: PositiveInt
    min_profit_factor: PositiveFloat
    min_expectancy_r: float
    max_drawdown_pct: PositiveFloat
    max_single_trade_profit_share_pct: Pct


class BacktestConfig(StrictModel):
    initial_equity_usdt: PositiveFloat
    warmup_days: NonNegInt
    candles: BacktestCandles
    walk_forward: WalkForwardConfig
    gate: GateConfig


class DashboardConfig(StrictModel):
    enabled: bool
    ingest_url: str
    timeout_seconds: PositiveFloat
    max_retries: Annotated[int, Field(ge=0, le=10)]
    max_results_per_run: PositiveInt

    @field_validator("ingest_url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("ingest_url deve começar com https://")
        return v


class TelegramConfig(StrictModel):
    enabled: bool


# --------------------------------------------------------------------------- onchain (opcional)
class OnchainCircuitBreaker(StrictModel):
    failures_to_open: PositiveInt
    open_minutes: PositiveFloat


class OnchainHttp(StrictModel):
    timeout_seconds: PositiveFloat
    scan_budget_seconds: PositiveFloat
    trigger_budget_seconds: PositiveFloat
    max_retries: NonNegInt
    min_interval_ms: NonNegInt
    circuit_breaker: OnchainCircuitBreaker
    on_auth_error_disable_hours: NonNegFloat
    respect_retry_after: bool


class OnchainBudget(StrictModel):
    max_calls_per_day: PositiveInt
    max_calls_per_hour: PositiveInt
    reserve_for_triggers_per_day: NonNegInt
    priority: list[str]

    @model_validator(mode="after")
    def _reserve(self) -> OnchainBudget:
        if self.reserve_for_triggers_per_day >= self.max_calls_per_day:
            raise ValueError("reserve_for_triggers_per_day deve ser menor que max_calls_per_day")
        return self


class OnchainCacheTtl(StrictModel):
    cohort_history: PositiveFloat
    risk_snapshot: PositiveFloat
    risk_overview: PositiveFloat
    market_overview: PositiveFloat
    liquidation_summary_1h: PositiveFloat
    heatmap: PositiveFloat


RelativeWindow = Annotated[str, Field(pattern=r"^\d+[hd]$")]  # ex.: 3h, 90d


class OnchainSnapshotLog(StrictModel):
    enabled: bool
    uri: str
    async_write: bool
    export_cohort_history_on_start: bool
    local_db_path: str
    export_since: RelativeWindow
    refresh_since: RelativeWindow
    export_timeout_seconds: PositiveFloat
    export_min_interval_ms: NonNegInt


class SymbolOverride(StrictModel):
    hl: str
    mult: PositiveInt


class OnchainSymbolMap(StrictModel):
    auto_native: bool
    overrides: dict[str, SymbolOverride]
    native_dex: str
    exclude_hl_patterns: list[str]
    price_check_max_dev_pct: PositiveFloat
    deny: list[str]


class OnchainQuality(StrictModel):
    min_hl_oi_usd: NonNegFloat
    smart_min_accounts: NonNegInt
    smart_min_notional_usd: NonNegFloat
    crowd_min_accounts: NonNegInt
    crowd_min_notional_usd: NonNegFloat
    empty_tiers_is_missing: bool


class OnchainScore(StrictModel):
    smart_tiers: list[str]
    crowd_tiers: list[str]
    bias_from_notionals: bool
    sm_short_max: Annotated[float, Field(ge=-1, le=0)]
    crowd_hot_min: Annotated[float, Field(ge=0, le=1)]
    persistence_hours: PositiveInt
    persistence_min_hits: PositiveInt
    penalty_points: Annotated[float, Field(le=0)]
    min_adj: Annotated[float, Field(le=0)]
    max_adj: Annotated[float, Field(le=0)]  # nunca bônus
    can_promote: Literal[False]  # em active só rebaixa

    @model_validator(mode="after")
    def _coherence(self) -> OnchainScore:
        if self.persistence_min_hits > self.persistence_hours:
            raise ValueError("persistence_min_hits não pode passar de persistence_hours")
        if self.penalty_points < self.min_adj:
            raise ValueError("penalty_points não pode ser menor que min_adj")
        return self


class OnchainNearLiq(StrictModel):
    share_veto_pct: PositiveFloat
    avg_liq_distance_max_pct: PositiveFloat
    percentile_after_days: PositiveInt
    percentile: Pct


class OnchainCascade(StrictModel):
    window: str
    long_liq_pct_of_oi: PositiveFloat
    min_long_events: PositiveInt
    pause_hours: PositiveFloat


class OnchainFilter(StrictModel):
    near_liq: OnchainNearLiq
    cascade: OnchainCascade


class OnchainMarketNearLiq(StrictModel):
    share_warn_pct: PositiveFloat
    factor: Factor
    percentile_after_days: PositiveInt
    percentile: Pct


class OnchainBtcDivergence(StrictModel):
    factor: Factor


class OnchainRisk(StrictModel):
    market_near_liq: OnchainMarketNearLiq
    btc_inverse_divergence: OnchainBtcDivergence
    combine: Literal["min"]
    min_onchain_factor: Factor
    min_total_risk_factor: Factor
    on_unavailable_factor: Literal[1.0]  # ausência de dado nunca reduz nem bloqueia


class OnchainShadowOnly(StrictModel):
    log_heatmap_on_trigger: bool
    heatmap_range_pct: PositiveFloat
    heatmap_buckets: PositiveInt
    log_sm_delta_24h: bool
    log_crowd_bias: bool
    log_coin_leverage: bool


class OnchainGemini(StrictModel):
    include_in_prompt: bool
    show_in_dashboard: bool


class OnchainAlerts(StrictModel):
    telegram_max_per_hour: NonNegInt


class OnchainConfig(StrictModel):
    enabled: bool
    provider: Literal["coinversa", "replay", "null"]
    mode: Literal["shadow", "active"]
    rules_active: list[OnchainRule]
    base_url: str
    api_key_secret: str
    auth_header: str
    http: OnchainHttp
    budget: OnchainBudget
    cache_ttl_minutes: OnchainCacheTtl
    max_data_age_minutes: PositiveFloat
    history_lag_hours: NonNegFloat
    snapshot_log: OnchainSnapshotLog
    symbol_map: OnchainSymbolMap
    quality: OnchainQuality
    score: OnchainScore
    filter: OnchainFilter
    risk: OnchainRisk
    shadow_only: OnchainShadowOnly
    gemini: OnchainGemini
    alerts: OnchainAlerts


# --------------------------------------------------------------------------- raiz
class BotConfig(StrictModel):
    mode: Mode
    timezone: str
    bybit: BybitConfig
    logging: LoggingConfig
    market_data: MarketDataConfig
    indicators: IndicatorsConfig
    markets: MarketsConfig
    schedule: ScheduleConfig
    universe: UniverseConfig
    regime: RegimeConfig
    score: ScoreConfig
    setups: SetupsConfig
    gemini: GeminiConfig
    risk: RiskConfig
    exits: ExitsConfig
    costs: CostsConfig
    backtest: BacktestConfig
    dashboard: DashboardConfig
    telegram: TelegramConfig
    onchain: OnchainConfig

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuso horário desconhecido: {v}") from exc
        return v

    def rest_url_for(self, mode: Mode | None = None) -> str:
        """URL REST da Bybit para o modo. paper usa a API real só para dados públicos."""
        mode = mode or self.mode
        return self.bybit.rest_url.demo if mode == "demo" else self.bybit.rest_url.live


def load_config(path: str | Path | None = None) -> BotConfig:
    """Lê e valida o YAML. Erros de validação viram ConfigError com a lista de problemas."""
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"arquivo de configuração não encontrado: {path}")
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"configuração vazia ou malformada: {path}")
    try:
        return BotConfig.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError traz a lista de campos
        raise ConfigError(f"configuração inválida em {path}:\n{exc}") from exc


def ensure_live_allowed(config: BotConfig, env: dict[str, str] | None = None) -> None:
    """O modo live exige mode: live no config E a variável CONFIRM_LIVE=SIM."""
    env = os.environ if env is None else env
    if config.mode != "live":
        raise LiveModeNotConfirmedError(f"o config está em modo {config.mode}, não live")
    if env.get("CONFIRM_LIVE") != "SIM":
        raise LiveModeNotConfirmedError("modo live bloqueado: defina CONFIRM_LIVE=SIM para confirmar")
