"""Setup experimental — bull_canal: porte do Bull H1M1 (Felipe Bull), modo CONTÍNUO.

Fonte: projeto BullH1M1 (ESTUDO_Bull_H1M1.md §8 e §10; referência Python tools/bh_ref.py, validada
com 0 divergências contra o indicador real e contra o núcleo MQL do EA). Este porte reproduz a
`RefCont` evento a evento (tests/test_bull_canal.py compara com a própria referência).

Regras (por vela FECHADA do tempo gráfico, ex.: 15m):
1. Canal = máxima/mínima das primeiras `n_candles` velas do ciclo.
2. Canal grande (altura >= mínimo) -> canal inteiro = [mín, máx]; pequeno -> espera o 1º fechamento
   fora e projeta 1× a altura (canal inteiro com 2× a altura). Avalia o sinal na mesma vela.
3. Fechamento acima do topo T -> COMPRA; abaixo do fundo B -> VENDA. H = T − B.
   SL = borda oposta ∓ stop_pct % de H; TP = T + H (compra) / B − H (venda).
4. Excesso do fechamento (% de H) <= filter_pct -> sinal; > cancel_break_pct -> cancela;
   entre os dois -> espera o pullback (toque na linha); na espera, extremo >= cancel_wait_pct -> cancela.
5. Depois de TAKE, LOSS ou cancelamento, a vela que encerrou vira a 1ª vela do próximo canal.

Adaptações para cripto spot (documentadas):
- `max_reversals = 0`: sem virada de mão (a virada após um loss na compra seria uma venda).
- Vendas seguem o fluxo como trade VIRTUAL (não executado), como o EA faz com sinais não operados.
- Canal mínimo em % do preço (`min_channel_pct`) em vez de pontos; `min_channel_abs` existe para
  a comparação com a referência (ouro, 2 casas). Sem arredondamento por padrão.
- Mercado 24/7: o reinício por "abertura do mercado" só ocorre se houver buraco nos dados.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BullSignal:
    t: int               # abertura da vela do sinal (ms)
    direction: int       # +1 compra, −1 venda (virtual em spot)
    line: float          # linha rompida
    sl: float
    tp: float
    after_pullback: bool
    top: float
    bottom: float


class BullCycle:
    """Máquina de estados do modo contínuo. `feed` recebe uma vela fechada por vez, em ordem."""

    def __init__(self, n_candles: int = 4, min_channel_pct: float = 0.24, stop_pct: float = 10.0,
                 filter_pct: float = 15.0, cancel_break_pct: float = 50.0, cancel_wait_pct: float = 50.0,
                 max_reversals: int = 0, reversal_mult: float = 3.0, gap_minutes: float = 30.0,
                 bar_ms: int = 15 * 60_000, min_channel_abs: float | None = None,
                 round_digits: int | None = None) -> None:
        self.nc, self.min_pct, self.min_abs = n_candles, min_channel_pct, min_channel_abs
        self.stop_pct, self.filt_pct = stop_pct, filter_pct
        self.zb, self.zw = cancel_break_pct, cancel_wait_pct
        self.max_rev, self.rev_mult = max_reversals, reversal_mult
        self.gap_ms, self.bar_ms = gap_minutes * 60_000, bar_ms
        self.digits = round_digits
        self.events: list[tuple] = []      # (t, tipo, dados, "") — mesmo formato da referência
        self.signals: list[BullSignal] = []
        self.state = "IDLE"
        self.nseen = 0
        self.mx = self.mn = 0.0
        self.size = 0.0
        self.T = self.B = 0.0
        self.pbdir = 0
        self.ext_run = 0.0
        self.vt: dict | None = None
        self.anchor: int | None = None
        self.last_t: int | None = None
        self.cycle = 0

    # ---------------------------------------------------------------- utilidades
    def _r(self, x: float) -> float:
        return round(x, self.digits) if self.digits is not None else x

    def _emit(self, t: int, kind: str, payload: tuple) -> None:
        self.events.append((t, kind, payload, ""))

    def _big_enough(self) -> bool:
        if self.min_abs is not None:
            return self.size >= self.min_abs - 1e-9
        mid = (self.mx + self.mn) / 2
        return mid > 0 and self.size / mid * 100 >= self.min_pct - 1e-12

    def _complete(self, t: int) -> None:
        self.size = self._r(self.mx - self.mn)
        self._emit(t, "CHANNEL", (self.mx, self.mn))
        if self._big_enough():
            self.T, self.B = self.mx, self.mn
            self._emit(t, "CYCLE1", (self._r((self.mx + self.mn) / 2), "CANAL FATIADO"))
            self.state = "ARMED"
        else:
            self.state = "WAIT1"

    def _start_collect(self, anchor: int) -> None:
        self.state = "COLLECT"
        self.nseen = 0
        self.mx, self.mn = -1e18, 1e18
        self.size = 0.0
        self.T = self.B = 0.0
        self.pbdir = 0
        self.ext_run = 0.0
        self.anchor = anchor
        self.cycle += 1
        self.vt = None

    def _signal(self, t: int, direction: int, after_pb: bool) -> None:
        H = self.T - self.B
        if direction > 0:
            line, sl, tp = self.T, self._r(self.B - self.stop_pct / 100 * H), self._r(self.T + H)
            payload = ("BUY", line, 65280, sl, tp)
        else:
            line, sl, tp = self.B, self._r(self.T + self.stop_pct / 100 * H), self._r(self.B - H)
            payload = ("SELL", line, 255, sl, tp)
        self._emit(t, "ARROW~" if after_pb else "ARROW+", payload)
        self.signals.append(BullSignal(t, direction, line, sl, tp, after_pb, self.T, self.B))
        self.state = "IN_TRADE"
        self.vt = {"t": t, "dir": direction, "sl": sl, "tp": tp, "nrev": 0, "top": self.T, "bot": self.B, "H": H}

    def _trade_closed(self, t: int, is_loss: bool) -> bool:
        d = self.vt
        self._emit(t, "TRADE_END", (d["dir"], "SL" if is_loss else "TP", d["nrev"]))
        if is_loss and d["nrev"] < self.max_rev:
            nd = -d["dir"]
            if nd < 0:
                line = d["bot"]
                sl, tp = self._r(d["top"] + self.stop_pct / 100 * d["H"]), self._r(d["bot"] - self.rev_mult * d["H"])
            else:
                line = d["top"]
                sl, tp = self._r(d["bot"] - self.stop_pct / 100 * d["H"]), self._r(d["top"] + self.rev_mult * d["H"])
            self._emit(t, "REV", ("BUY" if nd > 0 else "SELL", line, sl, tp))
            self.vt = {"t": t, "dir": nd, "sl": sl, "tp": tp, "nrev": d["nrev"] + 1, "top": d["top"],
                       "bot": d["bot"], "H": d["H"]}
            self.state = "IN_TRADE"
            return True
        self.vt = None
        self._start_collect(t)
        return False

    def _evaluate(self, t: int, o: float, h: float, low: float, c: float) -> None:
        if self.state == "WAIT1":
            if c > self.mx:
                self.T, self.B = self._r(self.mx + self.size), self.mn
                self._emit(t, "CYCLE1", (self.T, "PRIMEIRO CICLO"))
                self.state = "ARMED"
            elif c < self.mn:
                self.T, self.B = self.mx, self._r(self.mn - self.size)
                self._emit(t, "CYCLE1", (self.B, "PRIMEIRO CICLO"))
                self.state = "ARMED"
            if self.state == "WAIT1":
                return
        H = self.T - self.B
        if self.state == "ARMED":
            if c > self.T or c < self.B:
                up = c > self.T
                line = self.T if up else self.B
                exc = ((c - self.T) if up else (self.B - c)) / H * 100
                ext = ((h - self.T) if up else (self.B - low)) / H * 100
                if exc <= self.filt_pct:
                    self._signal(t, +1 if up else -1, False)
                elif self.zb > 0 and exc > self.zb:
                    self._emit(t, "ARROW+", ("CANCELADO", line, 255, None, None))
                    self.state = "DONE"
                else:
                    self._emit(t, "ARROW+", ("AGUARDANDO PULLBACK", line, 42495, None, None))
                    self.state = "PB"
                    self.pbdir = +1 if up else -1
                    self.ext_run = ext
        elif self.state == "PB":
            up = self.pbdir > 0
            line = self.T if up else self.B
            self.ext_run = ((h - self.T) if up else (self.B - low)) / H * 100
            if self.zw > 0 and self.ext_run >= self.zw:
                self._emit(t, "ARROW~", ("CANCELADO", line, 255, None, None))
                self.state = "DONE"
                return
            if (low <= self.T) if up else (h >= self.B):
                self._signal(t, self.pbdir, True)

    # ---------------------------------------------------------------- uma vela FECHADA
    def feed(self, t: int, o: float, h: float, low: float, c: float) -> None:
        """t = abertura da vela (ms). As velas devem chegar em ordem e já fechadas."""
        if (self.last_t is not None and self.gap_ms > 0 and self.state != "IN_TRADE"
                and (t - self.last_t) - self.bar_ms >= self.gap_ms):
            self._start_collect(t)
        self.last_t = t
        if self.state == "IN_TRADE" and t > self.vt["t"]:
            d = self.vt
            htp = (h >= d["tp"]) if d["dir"] > 0 else (low <= d["tp"])
            hsl = (low <= d["sl"]) if d["dir"] > 0 else (h >= d["sl"])
            if (htp or hsl) and self._trade_closed(t, hsl):  # TP e SL na mesma vela: assume STOP
                return
        if self.state == "IN_TRADE":
            return
        if self.state == "IDLE":
            self._start_collect(t)
        if self.state == "COLLECT":
            if t < self.anchor:
                return
            self.mx = max(self.mx, h)
            self.mn = min(self.mn, low)
            self.nseen += 1
            if self.nseen >= self.nc:
                self._complete(t)
            return
        self._evaluate(t, o, h, low, c)
        if self.state == "DONE":
            self._start_collect(t)
            self.mx = max(self.mx, h)
            self.mn = min(self.mn, low)
            self.nseen = 1
            if self.nseen >= self.nc:
                self._complete(t)
