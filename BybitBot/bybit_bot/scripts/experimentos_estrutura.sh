#!/bin/bash
# Setups de ESTRUTURA (Dow, BOS/CHoCH, LTB, cunha, médias) — intraday 15m/1H, compra e venda,
# sem exigir o score (só a estrutura decide), três saídas: padrão (parcial + móvel), alvo fixo 1R e 2R.
# Pesquisa: sem kill switch. Uso (na pasta bybit_bot):
#   bash scripts/experimentos_estrutura.sh mt5     # metais, forex, índices, energia
#   bash scripts/experimentos_estrutura.sh perp    # perpétuos da Bybit
set -u
PY="${PY:-.venv/Scripts/python.exe}"
export PYTHONIOENCODING=utf-8
SETUPS="cunha,estrutura_choch,lt_rompimento,estrutura_bos,medias_cruzamento"   # mais específico primeiro
run() {
  echo "=================== $1"
  shift
  "$@" 2>&1 | grep -v '"level"' | grep -v "^ *[0-9.]*% (" | grep -E "^Trades|Gate 5|ativos em"
}
exits() {   # $1 = rótulo base, demais = argumentos do mercado
  local base=$1; shift
  run "$base — saída padrão" "$PY" -m bot.tools.run_backtest "$@" --label "${base}_padrao"
  run "$base — alvo fixo 1R" "$PY" -m bot.tools.run_backtest "$@" --alvo-fixo 1 --label "${base}_1r"
  run "$base — alvo fixo 2R" "$PY" -m bot.tools.run_backtest "$@" --alvo-fixo 2 --label "${base}_2r"
}
common=(--intraday --no-kill-switch --sem-score --setups "$SETUPS")
case "${1:-}" in
  mt5)
    for group in ${MT5_GROUPS:-metais forex indices energia}; do
      for side in long short; do
        flag=(); [ "$side" = short ] && flag=(--short)
        exits "est_${group}_${side}" --market mt5 --group "$group" "${common[@]}" "${flag[@]}"
      done
    done
    ;;
  perp)
    for side in long short; do
      flag=(); [ "$side" = short ] && flag=(--short)
      exits "est_perp_${side}" --market perp --min-stop-pct 0.8 "${common[@]}" "${flag[@]}"
    done
    ;;
  *)
    echo "uso: bash scripts/experimentos_estrutura.sh mt5|perp"; exit 1 ;;
esac
