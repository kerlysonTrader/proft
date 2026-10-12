#!/bin/bash
# Robustez do único candidato da bateria de estrutura: BOS de compra nos perpétuos (intraday 15m/1H).
set -u
PY="${PY:-.venv/Scripts/python.exe}"
export PYTHONIOENCODING=utf-8
run() {
  echo "=================== $1"
  shift
  "$@" 2>&1 | grep -v '"level"' | grep -v "^ *[0-9.]*% (" | grep -E "^Trades|Walk-forward|ativos em"
}
base=(--intraday --no-kill-switch --sem-score --setups estrutura_bos)
perp=(--market perp --min-stop-pct 0.8)
run "BOS sozinho — perpétuos compra (pivôs 3)" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --label rob_bos_perp
run "BOS sozinho — alvo fixo 1R" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --alvo-fixo 1 --label rob_bos_perp_1r
run "BOS — pivôs 2" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --pivot-bars 2 --label rob_bos_perp_p2
run "BOS — pivôs 5" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --pivot-bars 5 --label rob_bos_perp_p5
run "BOS — contexto só Dow" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --contexto dow --label rob_bos_perp_dow
run "BOS — contexto só médias" "$PY" -m bot.tools.run_backtest "${perp[@]}" "${base[@]}" --contexto media --label rob_bos_perp_media
run "BOS — spot (taxa 0,1%)" "$PY" -m bot.tools.run_backtest --market spot --min-stop-pct 0.8 "${base[@]}" --label rob_bos_spot
