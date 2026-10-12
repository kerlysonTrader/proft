#!/bin/bash
# Backtests por mercado (multi-mercado): nossos setups intraday (15m/1H) e o Bull H1M1 15m,
# em COMPRA e em VENDA (gráfico invertido). Pesquisa: sem kill switch, para ver o período inteiro.
# Uso (na pasta bybit_bot):
#   bash scripts/experimentos_mercados.sh mt5    # grupos do MT5 (precisa de data/history_mt5.db)
#   bash scripts/experimentos_mercados.sh perp   # perpétuos da Bybit (precisa de data/history_perp.db)
set -u
PY="${PY:-.venv/Scripts/python.exe}"
export PYTHONIOENCODING=utf-8
run() {
  echo "=================== $1"
  shift
  "$@" 2>&1 | grep -v '"level"' | grep -v "^ *[0-9.]*% ("
}
case "${1:-}" in
  mt5)
    for group in ${MT5_GROUPS:-metais forex indices energia}; do
      for side in long short; do
        flag=""; [ "$side" = short ] && flag="--short"
        run "MT5 $group — nossos setups 15m/1H — $side" \
            "$PY" -m bot.tools.run_backtest --market mt5 --group "$group" --intraday --no-kill-switch $flag \
            --label "mt5_${group}_$side"
        chan=0.24; [ "$group" = forex ] && chan=0.1   # forex oscila ~1/3 do ouro: canal mínimo menor
        run "MT5 $group — Bull 15m (canal mín. $chan%) — $side" \
            "$PY" -m bot.tools.run_bull_backtest --market mt5 --group "$group" --no-kill-switch $flag \
            --min-channel-pct "$chan" --label "bull_mt5_${group}_$side"
      done
    done
    ;;
  perp)
    for side in long short; do
      flag=""; [ "$side" = short ] && flag="--short"
      run "Perpétuos — nossos setups 15m/1H, stop mín. 0,8% — $side" \
          "$PY" -m bot.tools.run_backtest --market perp --intraday --min-stop-pct 0.8 --time-stop-hours 12 \
          --no-kill-switch $flag --label "perp_intraday_$side"
      run "Perpétuos — Bull 15m puro (sem universo/regime) — $side" \
          "$PY" -m bot.tools.run_bull_backtest --market perp --no-universe --no-regime --no-kill-switch $flag \
          --label "bull_perp_$side"
    done
    ;;
  *)
    echo "uso: bash scripts/experimentos_mercados.sh mt5|perp"
    exit 1
    ;;
esac
