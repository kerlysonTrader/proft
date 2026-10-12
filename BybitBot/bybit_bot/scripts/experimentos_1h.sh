#!/bin/bash
# Bateria de experimentos isolados (Fase 5). Cada linha muda UMA coisa em relação à base de pesquisa.
# Uso (na pasta bybit_bot):  bash scripts/experimentos_1h.sh
set -u
PY="${PY:-.venv/Scripts/python.exe}"
export PYTHONIOENCODING=utf-8
run() {
  echo "=================== $1"
  shift
  "$PY" -m bot.tools.run_backtest "$@" 2>&1 | grep -v "^ *[0-9.]*% ("
}
run "reproducao (config atual, com kill switch)" --label completo
run "base de pesquisa (sem kill switch)"        --label pesq_base --no-kill-switch
run "(b) alvo fixo TP2 em vez de trailing"      --label pesq_tp2_fixo --no-kill-switch --exit-mode fixed_tp2
run "(c) sem invalidacao 4H"                    --label pesq_sem_invalidacao --no-kill-switch --no-invalidation
run "(d) so pullback"                            --label pesq_so_pullback --no-kill-switch --setups pullback_tendencia
run "(d2) so rompimento"                         --label pesq_so_rompimento --no-kill-switch --setups rompimento_compressao
