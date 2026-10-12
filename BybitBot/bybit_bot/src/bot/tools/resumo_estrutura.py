"""Tabela-resumo dos backtests de estrutura (scripts/experimentos_estrutura.sh).

    python -m bot.tools.resumo_estrutura            # lê data/backtest/est_*_trades.csv

Para cada mercado × direção × saída × setup: trades, acerto, expectância (R), profit factor e em
quantos anos o resultado foi positivo. Destaca as combinações que passam no critério mínimo
(≥ 100 trades, expectância > 0,10 R, PF ≥ 1,2 e positivo em pelo menos 2/3 dos anos).
Grava reports/<data>_estrutura_resumo.md.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime

import pandas as pd

from bot.config import PROJECT_ROOT, resolve_path

LABEL = re.compile(r"est_(?P<mercado>[a-z0-9]+)_(?P<lado>long|short)_(?P<saida>padrao|1r|2r)_trades\.csv$")
SIDE = {"long": "compra", "short": "venda"}
EXIT = {"padrao": "parcial + móvel", "1r": "alvo 1R", "2r": "alvo 2R"}
MIN_TRADES, MIN_EXP, MIN_PF, MIN_YEARS = 100, 0.10, 1.2, 2 / 3


def md_table(df: pd.DataFrame) -> str:
    """Tabela Markdown sem dependências extras."""
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def stats(r: pd.Series, years: pd.Series) -> dict:
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    by_year = r.groupby(years).sum()
    return {"trades": len(r), "acerto": (r > 0).mean() * 100, "exp_r": r.mean(),
            "pf": wins / losses if losses > 0 else float("inf"),
            "anos_pos": f"{int((by_year > 0).sum())}/{len(by_year)}",
            "anos_frac": (by_year > 0).mean() if len(by_year) else 0.0}


def main() -> int:
    rows = []
    for path in sorted(resolve_path("data/backtest").glob("est_*_trades.csv")):
        m = LABEL.search(path.name)
        if not m:
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        years = pd.to_datetime(df["opened_ms"], unit="ms").dt.year
        for setup, g in [("todos", df), *df.groupby("setup")]:
            s = stats(g["r"], years.loc[g.index])
            rows.append({"mercado": m["mercado"], "lado": SIDE[m["lado"]], "saida": EXIT[m["saida"]],
                         "setup": setup, **s})
    if not rows:
        print("Nenhum resultado (rode scripts/experimentos_estrutura.sh)")
        return 1
    tab = pd.DataFrame(rows)
    tab["passa"] = ((tab["trades"] >= MIN_TRADES) & (tab["exp_r"] > MIN_EXP) & (tab["pf"] >= MIN_PF)
                    & (tab["anos_frac"] >= MIN_YEARS))
    fmt = tab.assign(acerto=tab["acerto"].map("{:.1f}%".format), exp_r=tab["exp_r"].map("{:+.3f}".format),
                     pf=tab["pf"].map("{:.2f}".format), passa=tab["passa"].map({True: "✅", False: ""}))
    cols = ["mercado", "lado", "saida", "setup", "trades", "acerto", "exp_r", "pf", "anos_pos", "passa"]
    lines = [f"# Setups de estrutura — resumo ({datetime.now(UTC):%d/%m/%Y})", "",
             f"Critério mínimo (✅): ≥ {MIN_TRADES} trades, expectância > {MIN_EXP} R, PF ≥ {MIN_PF} e positivo "
             f"em pelo menos 2/3 dos anos. Intraday 15m/1H, sem exigir score, custos incluídos.", ""]
    best = fmt[tab["passa"]]
    lines += ["## Combinações que passam", "",
              md_table(best[cols]) if len(best) else "Nenhuma combinação passou.", ""]
    top = fmt.loc[tab[tab["setup"] != "todos"].sort_values("exp_r", ascending=False).index[:15]]
    lines += ["## 15 melhores por expectância (setup individual)", "", md_table(top[cols]), ""]
    lines += ["## Tabela completa", "", md_table(fmt[cols]), ""]
    out = PROJECT_ROOT / "reports" / f"{datetime.now(UTC):%Y%m%d}_estrutura_resumo.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(top[cols].to_string(index=False))
    print(f"\n{int(tab['passa'].sum())} combinações passam. Relatório: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
