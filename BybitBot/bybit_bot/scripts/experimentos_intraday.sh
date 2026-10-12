#!/bin/bash
# Experimentos intraday no spot (Fase 5): completa o histórico 1H/4H/1D das moedas novas da lista,
# roda o Bull H1M1 em 15m e os nossos setups com gatilho em 15m (contexto 1H).
# Uso (na pasta bybit_bot):  bash scripts/experimentos_intraday.sh
set -u
PY="${PY:-.venv/Scripts/python.exe}"
export PYTHONIOENCODING=utf-8
echo "=================== completando 1H/4H/1D das moedas novas (incremental)"
"$PY" -m bot.backtest.data_loader --months 25 --intervals 60,240,D 2>&1 | grep -E "^Moedas|^Falhas"
run() {
  echo "=================== $1"
  shift
  "$@" 2>&1 | grep -v "^ *[0-9.]*% ("
}
run "Bull 15m — universo + regime (sem kill switch, pesquisa)" \
    "$PY" -m bot.tools.run_bull_backtest --label bull_universo_regime --no-kill-switch
run "Bull 15m — puro: todas as moedas, sem regime (sem kill switch, pesquisa)" \
    "$PY" -m bot.tools.run_bull_backtest --label bull_puro --no-universe --no-regime --no-kill-switch
run "Nossos setups 15m/1H — stop de tempo 12h (sem kill switch, pesquisa)" \
    "$PY" -m bot.tools.run_backtest --label intraday_base --intraday --time-stop-hours 12 --no-kill-switch
run "Nossos setups 15m/1H — stop mínimo 0,8% (sem kill switch, pesquisa)" \
    "$PY" -m bot.tools.run_backtest --label intraday_stop08 --intraday --time-stop-hours 12 --min-stop-pct 0.8 \
    --no-kill-switch
