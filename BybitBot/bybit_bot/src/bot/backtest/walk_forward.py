"""Walk-forward: janelas de teste fora da amostra (Fase 5).

Sem otimização automática de parâmetros (pedido do plano: ver o efeito de cada mudança isolada),
o "treino" de cada janela não ajusta nada — só define a partir de quando se testa. Assim, o
walk-forward avalia a mesma execução contínua em janelas sucessivas de `test_months`, avançando
`step_months`, começando `train_months` depois do início. Cada janela conta só os trades
ABERTOS dentro dela.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from bot.backtest.engine import BacktestResult
from bot.backtest.report import Metrics


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def walk_forward_windows(result: BacktestResult, wf: Any) -> list[dict]:
    start = pd.Timestamp(datetime.fromtimestamp(result.start_ms / 1000, tz=UTC))
    end = pd.Timestamp(datetime.fromtimestamp(result.end_ms / 1000, tz=UTC))
    windows = []
    test_start = start + pd.DateOffset(months=wf.train_months)
    while test_start < end:
        test_end = min(test_start + pd.DateOffset(months=wf.test_months), end)
        trades = [t for t in result.trades if _ms(test_start) <= t.opened_ms < _ms(test_end)]
        m = Metrics.of(trades)
        windows.append({
            "label": f"{test_start:%d/%m/%Y} – {test_end:%d/%m/%Y}",
            "trades": m.trades, "expectancy_r": m.expectancy_r, "profit_factor": m.profit_factor, "pnl": m.pnl,
            "trade_list": trades,
        })
        test_start += pd.DateOffset(months=wf.step_months)
    return windows
