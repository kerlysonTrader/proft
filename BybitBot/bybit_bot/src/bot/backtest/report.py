"""Relatório do backtest e verificação automática do Gate 5 (02_PLANO_DE_EXECUCAO.md)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from bot.backtest.engine import BacktestResult, TradeRecord

SETUP_LABEL = {"pullback_tendencia": "Pullback", "rompimento_compressao": "Rompimento", "ote_fibo": "OTE Fibo"}


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


@dataclass
class Metrics:
    trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    payoff: float
    expectancy_r: float
    profit_factor: float
    pnl: float
    fees: float
    avg_hours: float

    @classmethod
    def of(cls, trades: Iterable[TradeRecord]) -> Metrics:
        trades = list(trades)
        n = len(trades)
        if not n:
            return cls(0, math.nan, math.nan, math.nan, math.nan, math.nan, math.nan, 0.0, 0.0, math.nan)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gross_win = sum(t.pnl for t in wins)
        gross_loss = -sum(t.pnl for t in losses)
        avg_win = sum(t.r for t in wins) / len(wins) if wins else math.nan
        avg_loss = sum(t.r for t in losses) / len(losses) if losses else math.nan
        return cls(
            trades=n,
            win_rate=len(wins) / n * 100,
            avg_win_r=avg_win,
            avg_loss_r=avg_loss,
            payoff=avg_win / abs(avg_loss) if wins and losses and avg_loss else math.nan,
            expectancy_r=sum(t.r for t in trades) / n,
            profit_factor=gross_win / gross_loss if gross_loss > 0 else math.inf,
            pnl=sum(t.pnl for t in trades),
            fees=sum(t.fees for t in trades),
            avg_hours=sum((t.closed_ms - t.opened_ms) / 3_600_000 for t in trades) / n,
        )


def max_drawdown_pct(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((peak - equity) / peak).max() * 100)


def score_band(score: float) -> str:
    for low, high in ((90, 101), (80, 90), (75, 80), (70, 75)):
        if low <= score < high:
            return f"{low}–{min(high, 100)}"
    return "< 70"


@dataclass
class GateCheck:
    name: str
    value: str
    passed: bool


def gate_checks(result: BacktestResult, gate: Any, wf_windows: list[dict] | None = None) -> list[GateCheck]:
    m = Metrics.of(result.trades)
    dd = max_drawdown_pct(result.equity)
    months = (result.end_ms - result.start_ms) / (30.4 * 24 * 3_600_000)
    net = m.pnl
    best = max((t.pnl for t in result.trades), default=0.0)
    share = best / net * 100 if net > 0 else math.inf
    checks = [
        GateCheck("≥ 12 meses de teste", f"{months:.1f} meses", months >= 12),
        GateCheck(f"≥ {gate.min_trades} trades", str(m.trades), m.trades >= gate.min_trades),
        GateCheck(f"Profit factor ≥ {gate.min_profit_factor:g}", f"{m.profit_factor:.2f}",
                  m.profit_factor >= gate.min_profit_factor),
        GateCheck(f"Expectância ≥ {gate.min_expectancy_r:g} R", f"{m.expectancy_r:.3f} R",
                  m.expectancy_r >= gate.min_expectancy_r),
        GateCheck(f"Drawdown máximo ≤ {gate.max_drawdown_pct:g} %", f"{dd:.1f} %", dd <= gate.max_drawdown_pct),
        GateCheck(f"Nenhum trade > {gate.max_single_trade_profit_share_pct:g} % do lucro",
                  "sem lucro" if net <= 0 else f"maior = {share:.0f} %",
                  net > 0 and share <= gate.max_single_trade_profit_share_pct),
    ]
    if wf_windows is not None:
        tested = [w for w in wf_windows if w["trades"] > 0]
        positive = sum(w["expectancy_r"] > 0 for w in tested)
        oos = [t for w in wf_windows for t in w["trade_list"]]
        oos_exp = Metrics.of(oos).expectancy_r
        checks.append(GateCheck("Walk-forward positivo fora da amostra",
                                f"{positive}/{len(tested)} janelas positivas; expectância OOS {oos_exp:.3f} R",
                                bool(tested) and oos_exp > 0 and positive >= math.ceil(len(tested) / 2)))
    return checks


def _fmt(v: float, digits: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    return f"{v:,.{digits}f}"


def _group_table(title: str, groups: dict[str, list[TradeRecord]]) -> list[str]:
    lines = [f"### {title}", "", "| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, trades in groups.items():
        m = Metrics.of(trades)
        lines.append(f"| {name} | {m.trades} | {_fmt(m.win_rate, 1)}% | {_fmt(m.expectancy_r, 3)} | "
                     f"{_fmt(m.profit_factor)} | {_fmt(m.pnl)} |")
    return [*lines, ""]


def _groups(trades: list[TradeRecord], key) -> dict[str, list[TradeRecord]]:
    out: dict[str, list[TradeRecord]] = {}
    for t in trades:
        out.setdefault(key(t), []).append(t)
    return dict(sorted(out.items()))


def render_markdown(result: BacktestResult, config: Any, wf_windows: list[dict] | None = None,
                    title: str = "Backtest") -> str:
    m = Metrics.of(result.trades)
    eq = result.equity
    final = float(eq.iloc[-1]) if not eq.empty else result.initial_equity
    checks = gate_checks(result, config.backtest.gate, wf_windows)
    approved = all(c.passed for c in checks)
    lines = [
        f"# {title}",
        "",
        f"Período: **{_dt(result.start_ms):%d/%m/%Y} a {_dt(result.end_ms):%d/%m/%Y}** · "
        f"patrimônio inicial {result.initial_equity:,.0f} USDT · gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC",
        "",
        f"## Gate 5: **{'APROVADO' if approved else 'REPROVADO'}**",
        "",
        "| Critério | Resultado | |",
        "|---|---|---|",
        *[f"| {c.name} | {c.value} | {'✅' if c.passed else '❌'} |" for c in checks],
        "",
        "## Resumo",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Trades | {m.trades} |",
        f"| Acerto | {_fmt(m.win_rate, 1)}% |",
        f"| Ganho médio / perda média (R) | {_fmt(m.avg_win_r)} / {_fmt(m.avg_loss_r)} |",
        f"| Payoff | {_fmt(m.payoff)} |",
        f"| **Expectância** | **{_fmt(m.expectancy_r, 3)} R** |",
        f"| **Profit factor** | **{_fmt(m.profit_factor)}** |",
        f"| Resultado | {_fmt(m.pnl)} USDT ({_fmt((final / result.initial_equity - 1) * 100, 1)}%) |",
        f"| Taxas pagas | {_fmt(m.fees)} USDT |",
        f"| **Drawdown máximo** | **{_fmt(max_drawdown_pct(eq), 1)}%** |",
        f"| Tempo médio em posição | {_fmt(m.avg_hours, 1)} h |",
        f"| Sinais / barrados / ordens / expiradas | {result.signals_seen} / {result.signals_filtered} / "
        f"{result.orders_placed} / {result.orders_expired} |",
        "",
    ]
    lines += _group_table("Por setup", _groups(result.trades, lambda t: SETUP_LABEL.get(t.setup, t.setup)))
    lines += _group_table("Por regime na entrada", _groups(result.trades, lambda t: t.regime or "?"))
    lines += _group_table("Por faixa de score", _groups(result.trades, lambda t: score_band(t.score)))
    lines += _group_table("Por motivo de saída", _groups(result.trades, lambda t: t.exit_reason))
    lines += _group_table("Por mês", _groups(result.trades, lambda t: f"{_dt(t.opened_ms):%Y-%m}"))
    if wf_windows is not None:
        lines += ["## Walk-forward (só períodos de teste)", "",
                  "| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |",
                  "|---|---:|---:|---:|---:|"]
        for w in wf_windows:
            lines.append(f"| {w['label']} | {w['trades']} | {_fmt(w['expectancy_r'], 3)} | "
                         f"{_fmt(w['profit_factor'])} | {_fmt(w['pnl'])} |")
        lines.append("")
    ranked = sorted(result.trades, key=lambda t: t.pnl)
    for title_, subset in (("10 maiores ganhos", ranked[::-1][:10]), ("10 maiores perdas", ranked[:10])):
        lines += [f"### {title_}", "", "| Entrada | Par | Setup | R | USDT | Saída |", "|---|---|---|---:|---:|---|"]
        lines += [f"| {_dt(t.opened_ms):%d/%m/%Y %H:%M} | {t.symbol} | {SETUP_LABEL.get(t.setup, t.setup)} | "
                  f"{t.r:.2f} | {t.pnl:.2f} | {t.exit_reason} |" for t in subset]
        lines.append("")
    if result.risk_events:
        lines += ["## Eventos do motor de risco", "", *[f"- {e}" for e in result.risk_events[:50]], ""]
    lines += ["## Limitações", "", *[f"- {n}" for n in result.notes], ""]
    return "\n".join(lines)


def trades_frame(trades: list[TradeRecord]) -> pd.DataFrame:
    df = pd.DataFrame([t.__dict__ for t in trades])
    if not df.empty:
        df["opened"] = pd.to_datetime(df["opened_ms"], unit="ms", utc=True)
        df["closed"] = pd.to_datetime(df["closed_ms"], unit="ms", utc=True)
    return df
