from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from bot.signals.bull_canal import BullCycle
from reference.bh_ref import RefCont

MIN = 60_000


def gold_bars(n: int, seed: int, gaps: bool = False):
    """Velas M1 aleatórias estilo ouro (2 casas), com rompimentos fortes de vez em quando."""
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    bars, price, t = [], 2400.0, t0
    for i in range(n):
        if gaps and i % 300 == 299:
            t += timedelta(minutes=95)  # buraco: "abertura do mercado"
        jump = rng.normal(0, 4.0) if rng.random() < 0.06 else rng.normal(0, 0.9)
        o = price
        c = round(o + jump, 2)
        h = round(max(o, c) + abs(rng.normal(0, 0.6)), 2)
        low = round(min(o, c) - abs(rng.normal(0, 0.6)), 2)
        bars.append((t, round(o, 2), h, low, c))
        price, t = c, t + timedelta(minutes=1)
    return bars


def to_ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def run_both(bars, max_rev=0):
    ref = RefCont(max_rev=max_rev, rev_mult=3.0, gap_min=30, bar_sec=60, nc=4, minsize=5.0, stop_pct=10.0,
                  filt_pct=15.0, zb=50.0, zw=50.0)
    port = BullCycle(n_candles=4, min_channel_abs=5.0, round_digits=2, stop_pct=10.0, filter_pct=15.0,
                     cancel_break_pct=50.0, cancel_wait_pct=50.0, max_reversals=max_rev, reversal_mult=3.0,
                     gap_minutes=30, bar_ms=MIN)
    for (t, o, h, low, c) in bars:
        ref.feed(t, o, h, low, c)
        port.feed(to_ms(t), o, h, low, c)
    expected = [(to_ms(t), kind, payload) for (t, kind, payload, _) in ref.ev]
    got = [(t, kind, payload) for (t, kind, payload, _) in port.events]
    return expected, got, port


@pytest.mark.parametrize("seed, gaps, max_rev", [(1, False, 0), (2, False, 0), (3, True, 0), (4, True, 1),
                                                 (5, False, 1), (6, True, 0)])
def test_porte_identico_a_referencia_validada(seed, gaps, max_rev):
    expected, got, _ = run_both(gold_bars(3000, seed, gaps), max_rev)
    assert len(expected) > 100  # o teste exercita bastante coisa
    kinds = {k for _, k, _ in expected}
    assert {"CHANNEL", "CYCLE1", "ARROW+", "TRADE_END"} <= kinds
    assert got == expected


def test_sem_virada_em_spot():
    _, got, port = run_both(gold_bars(3000, 7), max_rev=0)
    assert not any(kind == "REV" for _, kind, _ in got)
    buys = [s for s in port.signals if s.direction > 0]
    assert buys and all(s.sl < s.line < s.tp for s in buys)
    for s in buys:
        H = s.top - s.bottom
        assert s.tp == pytest.approx(s.top + H, abs=0.01)
        assert s.sl == pytest.approx(s.bottom - 0.10 * H, abs=0.01)


def test_canal_minimo_em_percentual():
    # canal de 4 velas com 0,5 % de altura: grande se o mínimo for 0,24 %, pequeno se for 1 %
    rows = [(100, 100.5, 100.0, 100.2)] * 4
    for pct, state in ((0.24, "ARMED"), (1.0, "WAIT1")):
        cyc = BullCycle(min_channel_pct=pct, bar_ms=15 * MIN)
        for i, (o, h, low, c) in enumerate(rows):
            cyc.feed(i * 15 * MIN, o, h, low, c)
        assert cyc.state == state
