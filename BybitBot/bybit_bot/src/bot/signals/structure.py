"""Leitura objetiva da estrutura de preço — Teoria de Dow, BOS/CHoCH, LTA/LTB, cunha — e médias móveis.

Tudo é calculado vela a vela SEM olhar o futuro: um topo/fundo (pivô com `pivot_bars` velas de cada
lado) só passa a existir quando a vela `pivô + pivot_bars` fecha. `structure_arrays` devolve, para
cada vela, a leitura daquele momento: o robô ao vivo usa a última vela e o backtest calcula a série
inteira uma vez (tests/test_structure.py garante que as duas formas dão o mesmo resultado).

- Dow: "alta" com os dois últimos topos E os dois últimos fundos ascendentes; "baixa" com ambos
  descendentes; senão "lateral".
- Quebra de estrutura: fechamento além do último topo/fundo confirmado (a vela anterior ainda não
  tinha passado). A favor da tendência = BOS; contra ela (rompe o último topo numa baixa, ou perde o
  último fundo numa alta) = CHoCH, a mudança de caráter.
- LTA: reta pelos dois últimos fundos ascendentes; LTB: pelos dois últimos topos descendentes. Só
  vale se nenhum fechamento cruzou a reta entre as âncoras (tolerância em ATR). Toques = âncoras +
  pivôs anteriores que encostam na reta prolongada. Quebra = primeiro fechamento além da reta.
- Cunha de baixa (falling wedge): topos e fundos descendentes, retas convergindo (os topos caem mais
  rápido); vale o rompimento da reta de cima. Cunha de alta (rising wedge): o espelho, rompimento da
  reta de baixo.
- Médias: MME 9, 21, 50 e 200 no padrão do TradingView; alinhamento e cruzamento 9 × 21.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from bot.indicators import atr, ema
from bot.signals.ote_fibo import Pivot, find_pivots

TREND_LABEL = {1: "alta", -1: "baixa", 0: "lateral"}
MAX_TOUCH_LOOKBACK = 6   # pivôs anteriores examinados para contar toques na reta
READING_NOTE = ("📐 Leitura descritiva: entrar mecanicamente nesses gatilhos (BOS, CHoCH, LTB, cunha, "
                "médias) não mostrou vantagem no backtest intraday 15m/1H (12/10/2026) — use como apoio")
EVENT_COLUMNS = ("bos_up", "bos_down", "choch_up", "choch_down", "lta_break", "ltb_break",
                 "wedge_up", "wedge_down", "cross_up", "cross_down")
VALUE_COLUMNS = ("close", "atr", "ema_fast", "ema_slow", "ema_mid", "ema_long", "trend", "ma_align",
                 "last_high", "last_low", "prev_high", "prev_low", "break_level",
                 "lta", "ltb", "lta_touches", "ltb_touches")


@dataclass(frozen=True)
class StructureParams:
    pivot_bars: int = 3
    line_tolerance_atr: float = 0.25
    ema_fast: int = 9
    ema_slow: int = 21
    ema_mid: int = 50
    ema_long: int = 200
    atr_period: int = 14

    @classmethod
    def from_config(cls, st: Any, atr_period: int) -> StructureParams:
        return cls(st.pivot_bars, st.line_tolerance_atr, st.ema_fast, st.ema_slow, st.ema_mid, st.ema_long,
                   atr_period)


@dataclass
class _Line:
    """Reta por duas âncoras (índice, preço). broken = já houve fechamento além dela."""
    i1: int
    p1: float
    i2: int
    p2: float
    broken: bool = False
    touches: int = 2

    @property
    def key(self) -> tuple[int, int]:
        return self.i1, self.i2

    @property
    def slope(self) -> float:
        return (self.p2 - self.p1) / (self.i2 - self.i1)

    def at(self, i: int) -> float:
        return self.p2 + self.slope * (i - self.i2)


def _zigzag_add(zz: list[Pivot], p: Pivot) -> None:
    """Alterna topo/fundo; em sequência do mesmo tipo fica o mais extremo (empate: o mais antigo)."""
    if zz and zz[-1].is_high == p.is_high:
        if (p.price > zz[-1].price) if p.is_high else (p.price < zz[-1].price):
            zz[-1] = p
    else:
        zz.append(p)


def _last(zz: list[Pivot], is_high: bool, n: int) -> list[Pivot]:
    out = []
    for p in reversed(zz):
        if p.is_high == is_high:
            out.append(p)
            if len(out) == n:
                break
    return out[::-1]


def structure_arrays(df: pd.DataFrame, p: StructureParams | None = None) -> dict[str, np.ndarray]:
    """Leitura vela a vela (sem olhar o futuro). Eventos são booleanos na vela em que acontecem."""
    p = p or StructureParams()
    n = len(df)
    high, low, close = (df[c].to_numpy(float) for c in ("high", "low", "close"))
    out: dict[str, np.ndarray] = {c: np.zeros(n, dtype=bool) for c in EVENT_COLUMNS}
    out.update({c: np.full(n, np.nan) for c in VALUE_COLUMNS})
    out["close"] = close.copy()
    if n == 0:
        return out
    a = atr(df, p.atr_period).to_numpy(float)
    out["atr"] = a
    for name, period in (("ema_fast", p.ema_fast), ("ema_slow", p.ema_slow), ("ema_mid", p.ema_mid),
                         ("ema_long", p.ema_long)):
        out[name] = ema(df["close"], period).to_numpy(float)
    f, s, m, lg = out["ema_fast"], out["ema_slow"], out["ema_mid"], out["ema_long"]
    out["ma_align"] = np.where((f > s) & (s > m) & (m > lg), 1, np.where((f < s) & (s < m) & (m < lg), -1, 0))
    out["cross_up"][1:] = (f[1:] > s[1:]) & (f[:-1] <= s[:-1])
    out["cross_down"][1:] = (f[1:] < s[1:]) & (f[:-1] >= s[:-1])

    confirmations: dict[int, list[Pivot]] = defaultdict(list)
    for piv in find_pivots(df, p.pivot_bars):
        confirmations[piv.pos + p.pivot_bars].append(piv)

    zz: list[Pivot] = []
    lta: _Line | None = None
    ltb: _Line | None = None
    tol = p.line_tolerance_atr
    tol_arr = tol * np.nan_to_num(a, nan=0.0)
    for t in range(n):
        for piv in confirmations.get(t, ()):
            _zigzag_add(zz, piv)
        highs, lows = _last(zz, True, 2), _last(zz, False, 2)
        trend = 0
        if len(highs) == 2 and len(lows) == 2:
            if highs[1].price > highs[0].price and lows[1].price > lows[0].price:
                trend = 1
            elif highs[1].price < highs[0].price and lows[1].price < lows[0].price:
                trend = -1
        out["trend"][t] = trend
        if highs:
            out["last_high"][t] = highs[-1].price
        if lows:
            out["last_low"][t] = lows[-1].price
        if len(highs) == 2:
            out["prev_high"][t] = highs[0].price
        if len(lows) == 2:
            out["prev_low"][t] = lows[0].price
        tol_t = tol_arr[t]

        # quebra de estrutura (pivô confirmado agora nunca é rompido na mesma vela)
        if t >= 1:
            if highs and close[t] > highs[-1].price >= close[t - 1]:
                out["choch_up" if trend == -1 else "bos_up"][t] = True
                out["break_level"][t] = highs[-1].price
            if lows and close[t] < lows[-1].price <= close[t - 1]:
                out["choch_down" if trend == 1 else "bos_down"][t] = True
                out["break_level"][t] = lows[-1].price

        # LTA (fundos ascendentes) e LTB (topos descendentes)
        lta = _update_line(lta, lows, ascending=True, close=close, tol_arr=tol_arr, t=t, zz=zz)
        ltb = _update_line(ltb, highs, ascending=False, close=close, tol_arr=tol_arr, t=t, zz=zz)
        if lta is not None and not lta.broken:
            value = lta.at(t)
            out["lta"][t], out["lta_touches"][t] = value, lta.touches
            if close[t] < value - tol_t:
                lta.broken = True
                out["lta_break"][t] = True
                # cunha de alta (rising wedge): topos também sobem, mas mais devagar que os fundos
                if len(highs) == 2 and highs[1].price > highs[0].price:
                    upper = _Line(highs[0].pos, highs[0].price, highs[1].pos, highs[1].price)
                    out["wedge_down"][t] = 0 < upper.slope < lta.slope and upper.at(t) > value
        if ltb is not None and not ltb.broken:
            value = ltb.at(t)
            out["ltb"][t], out["ltb_touches"][t] = value, ltb.touches
            if close[t] > value + tol_t:
                ltb.broken = True
                out["ltb_break"][t] = True
                # cunha de baixa (falling wedge): fundos também caem, mas mais devagar que os topos
                if len(lows) == 2 and lows[1].price < lows[0].price:
                    lower = _Line(lows[0].pos, lows[0].price, lows[1].pos, lows[1].price)
                    out["wedge_up"][t] = ltb.slope < lower.slope < 0 and lower.at(t) < value
    return out


def _update_line(line: _Line | None, anchors: list[Pivot], ascending: bool, close: np.ndarray,
                 tol_arr: np.ndarray, t: int, zz: list[Pivot]) -> _Line | None:
    """Reta das duas últimas âncoras; refeita (e validada) só quando as âncoras mudam."""
    if len(anchors) < 2:
        return None
    a1, a2 = anchors
    if (a2.price > a1.price) != ascending or a2.price == a1.price:
        return None
    if line is not None and line.key == (a1.pos, a2.pos):
        return line
    new = _Line(a1.pos, a1.price, a2.pos, a2.price)
    sign = 1 if ascending else -1   # LTA: fechamentos acima da reta; LTB: abaixo
    j = np.arange(a1.pos, t)        # entre as âncoras E depois delas até agora: não pode ter cruzado
    if len(j) and np.any(sign * (close[j] - new.at(j)) < -tol_arr[j]):
        new.broken = True
    seen = 0
    for piv in reversed(zz):        # toques: pivôs anteriores (recentes) encostados na reta prolongada
        if piv.pos >= a1.pos or piv.is_high == ascending:
            continue
        seen += 1
        if seen > MAX_TOUCH_LOOKBACK:
            break
        if abs(piv.price - new.at(piv.pos)) <= tol_arr[piv.pos]:
            new.touches += 1
    return new


def row_at(arrays: dict[str, np.ndarray], i: int) -> dict[str, float]:
    return {k: v[i].item() for k, v in arrays.items()}


# ---------------------------------------------------------------------------- texto para o painel
def _fmt(value: float) -> str:
    return f"{value:.6g}".replace(".", ",")


def reading_lines(row: dict[str, float], ctx_row: dict[str, float] | None, tf: str, ctx_tf: str) -> list[str]:
    """Leitura objetiva para o painel, sempre no gráfico REAL (a venda só usa o invertido no teste)."""
    def known(*keys: str) -> bool:
        return all(row[k] == row[k] for k in keys)

    lines = []
    if ctx_row is not None:
        above = ctx_row["close"] > ctx_row["ema_mid"]
        lines.append(f"Estrutura {ctx_tf}: {TREND_LABEL[int(ctx_row['trend'])]} (Dow); preço "
                     f"{'acima' if above else 'abaixo'} da MME50 {ctx_tf}")
    if known("last_high", "last_low"):
        lines.append(f"Estrutura {tf}: {TREND_LABEL[int(row['trend'])]} (Dow); último topo "
                     f"{_fmt(row['last_high'])}, último fundo {_fmt(row['last_low'])}")
    else:
        lines.append(f"Estrutura {tf}: pivôs insuficientes")
    lt = []
    if known("lta"):
        lt.append(f"LTA em {_fmt(row['lta'])} ({int(row['lta_touches'])} toques)")
    if known("ltb"):
        lt.append(f"LTB em {_fmt(row['ltb'])} ({int(row['ltb_touches'])} toques)")
    if lt:
        lines.append(f"Linhas {tf}: {'; '.join(lt)}")
    events = {"bos_up": "BOS de alta", "bos_down": "BOS de baixa", "choch_up": "CHoCH de alta (virada para alta)",
              "choch_down": "CHoCH de baixa (virada para baixa)", "lta_break": "quebra da LTA",
              "ltb_break": "quebra da LTB", "wedge_up": "rompimento de cunha de baixa (falling wedge)",
              "wedge_down": "perda de cunha de alta (rising wedge)", "cross_up": "MME9 cruzou acima da MME21",
              "cross_down": "MME9 cruzou abaixo da MME21"}
    fired = [label for key, label in events.items() if row.get(key)]
    if fired:
        lines.append(f"Na última vela de {tf}: {', '.join(fired)}")
    align = int(row["ma_align"])
    lines.append(f"Médias {tf}: " + ("alinhadas em alta (9 > 21 > 50 > 200)" if align == 1 else
                                     "alinhadas em baixa (9 < 21 < 50 < 200)" if align == -1 else
                                     "sem alinhamento"))
    if ctx_row is not None and known("last_high", "last_low"):
        lines.append(watch_line(row, ctx_row, tf, ctx_tf))
    return lines


def watch_line(row: dict[str, float], ctx_row: dict[str, float], tf: str, ctx_tf: str) -> str:
    """O que observar juntando os dois tempos gráficos (leitura, não recomendação)."""
    ctx_trend, above = int(ctx_row["trend"]), ctx_row["close"] > ctx_row["ema_mid"]
    trend, hi, lo = int(row["trend"]), _fmt(row["last_high"]), _fmt(row["last_low"])
    if ctx_trend == 1 and above:
        if trend == 1:
            text = (f"{ctx_tf} e {tf} em alta: continuação com BOS acima de {hi}; a estrutura do {tf} "
                    f"se perde abaixo de {lo}")
        else:
            text = f"a favor do {ctx_tf} (compra): aguardar CHoCH/BOS de alta no {tf} acima de {hi}"
            if row["ltb"] == row["ltb"]:
                text += f" ou a quebra da LTB em {_fmt(row['ltb'])}"
            text += f"; invalida abaixo de {lo}"
    elif ctx_trend == -1 and not above:
        if trend == -1:
            text = (f"{ctx_tf} e {tf} em baixa: continuação com BOS abaixo de {lo}; a estrutura do {tf} "
                    f"se perde acima de {hi}")
        else:
            text = f"a favor do {ctx_tf} (venda): aguardar CHoCH/BOS de baixa no {tf} abaixo de {lo}"
            if row["lta"] == row["lta"]:
                text += f" ou a quebra da LTA em {_fmt(row['lta'])}"
            text += f"; invalida acima de {hi}"
    else:
        text = (f"{ctx_tf} sem direção clara (Dow e MME50 não concordam): melhor aguardar; "
                f"no {tf}, rompimento acima de {hi} ou abaixo de {lo}")
    return f"Gatilho a observar: {text}"


def structure_reading(trig: pd.DataFrame, ctx: pd.DataFrame, params: StructureParams | None = None,
                      tf: str = "15m", ctx_tf: str = "1H") -> list[str]:
    """Leitura do momento (velas FECHADAS) para o painel; vazia se faltar histórico."""
    if len(trig) < 60 or len(ctx) < 60:
        return []
    t = row_at(structure_arrays(trig, params), len(trig) - 1)
    c = row_at(structure_arrays(ctx, params), len(ctx) - 1)
    return ["📐 " + line for line in reading_lines(t, c, tf, ctx_tf)] + [READING_NOTE]
