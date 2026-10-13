"""Estatística do backtest por mercado, direção e setup — acompanha os planos no painel.

Lê os trades gravados pelo run_backtest (data/backtest/<label>_trades.csv). Assim cada plano mostra
o que aquele setup fez no histórico daquele mercado e naquela direção, e o usuário decide sabendo
se há vantagem medida ou não.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

SETUP_NAMES = {"pullback_tendencia": "pullback", "rompimento_compressao": "rompimento", "ote_fibo": "OTE"}
MIN_TRADES = 30   # abaixo disso a média não diz muito


@dataclass(frozen=True)
class SetupStats:
    trades: int
    win_rate: float       # %
    expectancy_r: float

    @property
    def has_edge(self) -> bool:
        return self.trades >= MIN_TRADES and self.expectancy_r > 0


def load_stats(csv_path: str | Path) -> dict[str, SetupStats]:
    """{setup: SetupStats, "todos": SetupStats}; vazio se o backtest ainda não foi rodado."""
    path = Path(csv_path)
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    out = {setup: _stats(g["r"]) for setup, g in df.groupby("setup")}
    out["todos"] = _stats(df["r"])
    return out


def _stats(r: pd.Series) -> SetupStats:
    return SetupStats(int(len(r)), float((r > 0).mean() * 100), float(r.mean()))


def _fmt_r(value: float) -> str:
    return f"{value:+.2f}R".replace(".", ",").replace("-", "−")


def stats_lines(stats: dict[str, SetupStats], what: str) -> list[str]:
    """Linhas para o painel. what = "metais · compra", por exemplo."""
    if not stats:
        return [f"Histórico ({what}): backtest ainda não rodado — sem estatística, use com cautela"]
    total = stats["todos"]
    parts = [f"{SETUP_NAMES.get(k, k)} {s.trades} trades, acerto {s.win_rate:.0f}%, {_fmt_r(s.expectancy_r)}"
             for k, s in stats.items() if k != "todos"]
    verdict = ("✅ vantagem medida no histórico" if total.has_edge
               else "⚠ SEM vantagem no histórico (amostra pequena)" if total.trades < MIN_TRADES
               else "⚠ SEM vantagem no histórico — não recomendado")
    return [f"Histórico do backtest ({what}, 15m/1H): {'; '.join(parts)} — {verdict}",
            "Informativo: você decide e executa; não é recomendação de investimento"]


STATS_FILE = "config/backtest_stats.json"   # vai junto com o código para a VM


def save_stats_file(path: str | Path, sources: dict[str, Path]) -> dict[str, int]:
    """Grava {chave: {setup: estatística}} a partir dos CSVs de trades. Devolve trades por chave."""
    data = {key: {setup: asdict(s) for setup, s in load_stats(csv).items()} for key, csv in sources.items()}
    payload = {"gerado_em": datetime.now(UTC).isoformat(timespec="seconds"), "mercados": data}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {key: v.get("todos", {}).get("trades", 0) for key, v in data.items()}


def load_stats_file(path: str | Path) -> dict[str, dict[str, SetupStats]]:
    """{chave: {setup: SetupStats}}; vazio se o arquivo não existir."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))["mercados"]
    except (FileNotFoundError, ValueError, KeyError):
        return {}
    return {key: {setup: SetupStats(**s) for setup, s in setups.items()} for key, setups in raw.items()}
