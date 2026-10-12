# Backtest — pesq_so_rompimento

Período: **21/11/2024 a 12/10/2026** · patrimônio inicial 1,000 USDT · gerado em 12/10/2026 18:21 UTC

## Gate 5: **REPROVADO**

| Critério | Resultado | |
|---|---|---|
| ≥ 12 meses de teste | 22.7 meses | ✅ |
| ≥ 150 trades | 24 | ❌ |
| Profit factor ≥ 1.3 | 1.00 | ❌ |
| Expectância ≥ 0.15 R | 0.052 R | ❌ |
| Drawdown máximo ≤ 20 % | 3.7 % | ✅ |
| Nenhum trade > 25 % do lucro | sem lucro | ❌ |
| Walk-forward positivo fora da amostra | 3/5 janelas positivas; expectância OOS 0.023 R | ✅ |

## Resumo

| Métrica | Valor |
|---|---:|
| Trades | 24 |
| Acerto | 41.7% |
| Ganho médio / perda média (R) | 1.67 / -1.11 |
| Payoff | 1.51 |
| **Expectância** | **0.052 R** |
| **Profit factor** | **1.00** |
| Resultado | -0.23 USDT (-0.0%) |
| Taxas pagas | 11.65 USDT |
| **Drawdown máximo** | **3.7%** |
| Tempo médio em posição | 13.8 h |
| Sinais / barrados / ordens / expiradas | 68 / 36 / 32 / 8 |

### Por setup

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| Rompimento | 24 | 41.7% | 0.052 | 1.00 | -0.23 |

### Por regime na entrada

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| neutro | 4 | 50.0% | -0.053 | 0.94 | -0.66 |
| risk_on | 20 | 40.0% | 0.073 | 1.01 | 0.43 |

### Por faixa de score

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 70–75 | 6 | 33.3% | -0.282 | 0.59 | -9.56 |
| 75–80 | 10 | 40.0% | -0.071 | 0.70 | -11.43 |
| 80–90 | 8 | 50.0% | 0.457 | 1.62 | 20.76 |

### Por motivo de saída

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| stop | 14 | 0.0% | -1.107 | 0.00 | -94.73 |
| trailing | 10 | 100.0% | 1.674 | ∞ | 94.50 |

### Por mês

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 2025-04 | 2 | 50.0% | 0.375 | 1.58 | 3.18 |
| 2025-05 | 3 | 0.0% | -1.112 | 0.00 | -21.14 |
| 2025-07 | 7 | 42.9% | 0.034 | 0.76 | -6.15 |
| 2025-08 | 2 | 100.0% | 1.798 | ∞ | 17.99 |
| 2026-04 | 3 | 66.7% | 0.294 | 1.94 | 4.80 |
| 2026-08 | 1 | 0.0% | -1.120 | 0.00 | -5.77 |
| 2026-09 | 5 | 20.0% | -0.101 | 1.11 | 3.59 |
| 2026-10 | 1 | 100.0% | 0.744 | ∞ | 3.27 |

## Walk-forward (só períodos de teste)

| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|
| 21/05/2025 – 21/07/2025 | 7 | -0.287 | 0.41 | -20.39 |
| 21/07/2025 – 21/09/2025 | 5 | 0.502 | 1.93 | 11.09 |
| 21/09/2025 – 21/11/2025 | 0 | — | — | 0.00 |
| 21/11/2025 – 21/01/2026 | 0 | — | — | 0.00 |
| 21/01/2026 – 21/03/2026 | 0 | — | — | 0.00 |
| 21/03/2026 – 21/05/2026 | 3 | 0.294 | 1.94 | 4.80 |
| 21/05/2026 – 21/07/2026 | 0 | — | — | 0.00 |
| 21/07/2026 – 21/09/2026 | 3 | 0.545 | 2.86 | 23.20 |
| 21/09/2026 – 12/10/2026 | 4 | -0.629 | 0.13 | -22.11 |

### 10 maiores ganhos

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 17/09/2026 10:00 | UNIUSDT | Rompimento | 3.85 | 35.70 | trailing |
| 12/08/2025 14:00 | ETHUSDT | Rompimento | 2.25 | 10.37 | trailing |
| 22/04/2025 20:00 | SOLUSDT | Rompimento | 1.84 | 8.64 | trailing |
| 09/07/2025 21:00 | SOLUSDT | Rompimento | 2.09 | 8.09 | trailing |
| 12/08/2025 17:00 | AAVEUSDT | Rompimento | 1.35 | 7.61 | trailing |
| 13/04/2026 19:00 | HYPEUSDT | Rompimento | 1.32 | 6.42 | trailing |
| 16/07/2025 03:00 | GRAMUSDT | Rompimento | 1.45 | 5.87 | trailing |
| 27/07/2025 04:00 | LINKUSDT | Rompimento | 1.15 | 5.02 | trailing |
| 22/04/2026 05:00 | PEPEUSDT | Rompimento | 0.70 | 3.50 | trailing |
| 06/10/2026 14:00 | AVAXUSDT | Rompimento | 0.74 | 3.27 | trailing |

### 10 maiores perdas

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 21/09/2026 14:00 | ARBUSDT | Rompimento | -1.05 | -10.64 | stop |
| 21/05/2025 18:00 | WLDUSDT | Rompimento | -1.06 | -10.59 | stop |
| 21/09/2026 06:00 | PUMPUSDT | Rompimento | -1.07 | -9.84 | stop |
| 18/07/2025 07:00 | SUIUSDT | Rompimento | -1.08 | -8.03 | stop |
| 23/07/2025 10:00 | APTUSDT | Rompimento | -1.10 | -6.89 | stop |
| 08/09/2026 17:00 | ADAUSDT | Rompimento | -1.10 | -6.73 | stop |
| 27/05/2025 10:00 | AAVEUSDT | Rompimento | -1.11 | -6.23 | stop |
| 30/08/2026 23:00 | MNTUSDT | Rompimento | -1.12 | -5.77 | stop |
| 21/04/2025 09:00 | CRVUSDT | Rompimento | -1.09 | -5.46 | stop |
| 07/07/2025 00:00 | AAVEUSDT | Rompimento | -1.13 | -5.19 | stop |

## Por que os sinais foram barrados

| Motivo (primeiro) | Sinais |
|---|---:|
| rompimento_compressao: regime risk_off / circuit breaker: sem novas entradas | 19 |
| rompimento_compressao: stop curto demais: #% < #% | 13 |
| rompimento_compressao: pausa após perdas seguidas | 3 |
| rompimento_compressao: stop há menos de # h nesta moeda | 1 |

## Eventos do motor de risco

- 2025-05-28 11:00 pausa: 3 perdas seguidas
- 2025-07-23 10:00 pausa: 3 perdas seguidas
- 2026-09-08 19:00 pausa: 3 perdas seguidas
- 2026-10-01 14:00 pausa: 3 perdas seguidas

## Limitações

- Gemini desligado no backtest (veto qualitativo não simulado)
- Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas
- Spread e profundidade do livro não simulados (sem histórico)
- Universo = maiores moedas de hoje (viés de sobrevivência)
- Stop/alvo na mesma vela: considera o stop (conservador)
