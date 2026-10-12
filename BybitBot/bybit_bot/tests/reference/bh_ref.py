#!/usr/bin/env python3
"""
bh_ref.py - implementacao de REFERENCIA (Python) do Bull H1M1, com as regras medidas no indicador real:
  canal de abertura, 1o ciclo (grande: ponto medio / pequeno: projecao), avaliacao na mesma vela, sinal por fechamento,
  SL/TP, filtro de rompimento, pullback (toque), cancelamentos (zb / zw) e a TRAVA "Aguardar trade atual" do indicador:
    * so o trade confirmado APOS PULLBACK trava (sinal direto nao trava);
    * o trade virtual resolve quando a maxima/minima de uma vela POSTERIOR toca o TP ou o SL;
    * enquanto ha trade virtual na virada da hora, a hora nao e marcada (objetos antigos ficam); quando o trade
      resolve, a marcacao da hora CORRENTE comeca naquela vela (canal = 1as N velas da hora; so a vela atual e avaliada).
Saida: lista de marcos (causa, tipo, payload, "") no mesmo formato de bh_analyze.observed().
"""


class Ref:
    def __init__(self, nc=4, minsize=5.00, stop_pct=10.0, filt_pct=15.0, pb="touch", excess_base="H",
                 zb=50.0, zw=50.0, cum=False, lock=True):
        self.nc, self.minsize, self.stop_pct, self.filt_pct = nc, minsize, stop_pct, filt_pct
        self.pb, self.excess_base, self.zb, self.zw, self.cum, self.lock = pb, excess_base, zb, zw, cum, lock
        self.ev = []
        self.hk = None
        self.state = "IDLE"
        self.nseen = 0
        self.mx = self.mn = 0.0
        self.size = 0.0
        self.T = self.B = 0.0
        self.pbdir = 0
        self.ext_run = 0.0
        self.vt = None

    # ---------------------------------------------------------------- utilidades
    def emit(self, t, kind, payload):
        self.ev.append((t, kind, payload, ""))

    def complete(self, t):
        self.size = round(self.mx - self.mn, 2)
        self.emit(t, "CHANNEL", (self.mx, self.mn))
        if self.size >= self.minsize - 1e-9:
            self.T, self.B = self.mx, self.mn
            self.emit(t, "CYCLE1", (round((self.mx + self.mn) / 2, 2), "CANAL FATIADO"))
            self.state = "ARMED"
        else:
            self.state = "WAIT1"

    def signal(self, t, dirn, afterpb):
        H = self.T - self.B
        if dirn > 0:
            line = self.T
            sl, tp = round(self.B - self.stop_pct / 100 * H, 2), round(self.T + H, 2)
            v = ("BUY", line, 65280, sl, tp)
        else:
            line = self.B
            sl, tp = round(self.T + self.stop_pct / 100 * H, 2), round(self.B - H, 2)
            v = ("SELL", line, 255, sl, tp)
        self.emit(t, "ARROW~" if afterpb else "ARROW+", v)
        self.state = "DONE"
        if afterpb and self.lock:
            self.vt = {"t": t, "dir": dirn, "sl": sl, "tp": tp}

    def evaluate(self, t, o, h, l, c):
        if self.state == "WAIT1":
            if c > self.mx:
                self.T, self.B = round(self.mx + self.size, 2), self.mn
                self.emit(t, "CYCLE1", (self.T, "PRIMEIRO CICLO"))
                self.state = "ARMED"
            elif c < self.mn:
                self.T, self.B = self.mx, round(self.mn - self.size, 2)
                self.emit(t, "CYCLE1", (self.B, "PRIMEIRO CICLO"))
                self.state = "ARMED"
            if self.state == "WAIT1":
                return
        H = self.T - self.B
        base = H if self.excess_base == "H" else self.size
        if self.state == "ARMED":
            if c > self.T or c < self.B:
                up = c > self.T
                line = self.T if up else self.B
                exc = ((c - self.T) if up else (self.B - c)) / base * 100
                ext = ((h - self.T) if up else (self.B - l)) / base * 100
                if exc <= self.filt_pct:
                    self.signal(t, +1 if up else -1, False)
                elif self.zb > 0 and exc > self.zb:
                    self.emit(t, "ARROW+", ("CANCELADO", line, 255, None, None))
                    self.state = "DONE"
                else:
                    self.emit(t, "ARROW+", ("AGUARDANDO PULLBACK", line, 42495, None, None))
                    self.state = "PB"
                    self.pbdir = +1 if up else -1
                    self.ext_run = ext
        elif self.state == "PB":
            up = self.pbdir > 0
            line = self.T if up else self.B
            ext = ((h - self.T) if up else (self.B - l)) / base * 100
            self.ext_run = max(self.ext_run, ext) if self.cum else ext
            if self.zw > 0 and self.ext_run >= self.zw:
                self.emit(t, "ARROW~", ("CANCELADO", line, 255, None, None))
                self.state = "DONE"
                return
            if self.pb == "touch":
                hit = (l <= self.T) if up else (h >= self.B)
            else:
                hit = (((c - self.T) if up else (self.B - c)) / base * 100 <= self.filt_pct)
            if hit:
                self.signal(t, self.pbdir, True)

    # ---------------------------------------------------------------- uma barra M1 FECHADA
    def feed(self, t, o, h, l, c):
        hk = t.replace(minute=0)
        # 1) trade virtual: resolve pela maxima/minima de uma vela POSTERIOR ao sinal
        if self.vt is not None and t > self.vt["t"]:
            d = self.vt
            htp = (h >= d["tp"]) if d["dir"] > 0 else (l <= d["tp"])
            hsl = (l <= d["sl"]) if d["dir"] > 0 else (h >= d["sl"])
            if htp or hsl:
                self.vt = None
        # 2) virada de hora
        if hk != self.hk:
            self.hk = hk
            self.nseen = 0
            self.mx, self.mn = -1e18, 1e18
            self.state = "LOCKED" if (self.lock and self.vt is not None) else "COLLECT"
        # 3) canal de abertura (acumula sempre, mesmo travado)
        just = False
        if self.nseen < self.nc:
            self.mx = max(self.mx, h)
            self.mn = min(self.mn, l)
            self.nseen += 1
            just = (self.nseen == self.nc)
        if self.state == "LOCKED":
            if self.vt is not None:
                return
            self.state = "COLLECT"
            if self.nseen >= self.nc and not just:
                # liberou DEPOIS das velas do canal: a marcacao comeca agora, avaliando so esta vela
                self.complete(t)
                self.evaluate(t, o, h, l, c)
                return
        if self.state == "COLLECT":
            if just:
                self.complete(t)
            return
        self.evaluate(t, o, h, l, c)


def simulate(bars, **params):
    r = Ref(**params)
    for (t, o, h, l, c) in bars:
        r.feed(t, o, h, l, c)
    return r.ev


# =====================================================================================================
# MODO CONTINUO (teoria dos ciclos; especificacao do usuario) - espelha CBullCore(cycleMode=1)
#   * 1o canal = primeiras N velas da ABERTURA DO MERCADO (gap >= gap_min entre barras);
#   * apos TAKE ou LOSS a vela que fechou o trade e a 1a vela do proximo canal;
#   * apos LOSS: VIRADA DE MAO (operacao inversa) com alvo de "2 niveis" = borda -/+ rev_mult*H e SL na borda oposta
#     -/+ stop_pct*H; a virada nao se repete; o cancelamento tambem reinicia o canal a partir da vela.
# =====================================================================================================
class RefCont(Ref):
    def __init__(self, max_rev=1, rev_mult=3.0, gap_min=30, bar_sec=60, **kw):
        kw["lock"] = False
        super().__init__(**kw)
        self.max_rev, self.rev_mult, self.gap_min, self.bar_sec = max_rev, rev_mult, gap_min, bar_sec
        self.anchor = None
        self.last_t = None
        self.cycle = 0

    def start_collect(self, anchor):
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

    def signal(self, t, dirn, afterpb):
        H = self.T - self.B
        if dirn > 0:
            line = self.T
            sl, tp = round(self.B - self.stop_pct / 100 * H, 2), round(self.T + H, 2)
            v = ("BUY", line, 65280, sl, tp)
        else:
            line = self.B
            sl, tp = round(self.T + self.stop_pct / 100 * H, 2), round(self.B - H, 2)
            v = ("SELL", line, 255, sl, tp)
        self.emit(t, "ARROW~" if afterpb else "ARROW+", v)
        self.state = "IN_TRADE"
        self.vt = {"t": t, "dir": dirn, "sl": sl, "tp": tp, "nrev": 0, "top": self.T, "bot": self.B, "H": H}

    def trade_closed(self, t, is_loss):
        d = self.vt
        self.emit(t, "TRADE_END", (d["dir"], "SL" if is_loss else "TP", d["nrev"]))
        if is_loss and d["nrev"] < self.max_rev:
            nd = -d["dir"]
            if nd < 0:
                line = d["bot"]
                sl = round(d["top"] + self.stop_pct / 100 * d["H"], 2)
                tp = round(d["bot"] - self.rev_mult * d["H"], 2)
            else:
                line = d["top"]
                sl = round(d["bot"] - self.stop_pct / 100 * d["H"], 2)
                tp = round(d["top"] + self.rev_mult * d["H"], 2)
            self.emit(t, "REV", ("BUY" if nd > 0 else "SELL", line, sl, tp))
            self.vt = {"t": t, "dir": nd, "sl": sl, "tp": tp, "nrev": d["nrev"] + 1, "top": d["top"], "bot": d["bot"], "H": d["H"]}
            self.state = "IN_TRADE"
            return True
        self.vt = None
        self.start_collect(t)
        return False

    def feed(self, t, o, h, l, c):
        if (self.last_t is not None and self.gap_min > 0 and self.state != "IN_TRADE"
                and (t - self.last_t).total_seconds() - self.bar_sec >= self.gap_min * 60):
            self.start_collect(t)
        self.last_t = t
        if self.state == "IN_TRADE" and t > self.vt["t"]:
            d = self.vt
            htp = (h >= d["tp"]) if d["dir"] > 0 else (l <= d["tp"])
            hsl = (l <= d["sl"]) if d["dir"] > 0 else (h >= d["sl"])
            if htp or hsl:
                if self.trade_closed(t, hsl):     # TP e SL na mesma vela: assume STOP
                    return
        if self.state == "IN_TRADE":
            return
        if self.state == "IDLE":
            self.start_collect(t)
        if self.state == "COLLECT":
            if t < self.anchor:
                return
            self.mx = max(self.mx, h)
            self.mn = min(self.mn, l)
            self.nseen += 1
            if self.nseen >= self.nc:
                self.complete(t)
            return
        self.evaluate(t, o, h, l, c)
        if self.state == "DONE":
            self.start_collect(t)
            self.mx = max(self.mx, h)
            self.mn = min(self.mn, l)
            self.nseen = 1
            if self.nseen >= self.nc:
                self.complete(t)


def simulate_cont(bars, **params):
    r = RefCont(**params)
    for (t, o, h, l, c) in bars:
        r.feed(t, o, h, l, c)
    return r.ev
