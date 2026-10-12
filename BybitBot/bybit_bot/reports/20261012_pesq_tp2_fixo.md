# Backtest — pesq_tp2_fixo

Período: **21/11/2024 a 12/10/2026** · patrimônio inicial 1,000 USDT · gerado em 12/10/2026 18:05 UTC

## Gate 5: **REPROVADO**

| Critério | Resultado | |
|---|---|---|
| ≥ 12 meses de teste | 22.7 meses | ✅ |
| ≥ 150 trades | 127 | ❌ |
| Profit factor ≥ 1.3 | 0.82 | ❌ |
| Expectância ≥ 0.15 R | -0.127 R | ❌ |
| Drawdown máximo ≤ 20 % | 19.1 % | ✅ |
| Nenhum trade > 25 % do lucro | sem lucro | ❌ |
| Walk-forward positivo fora da amostra | 4/8 janelas positivas; expectância OOS -0.118 R | ❌ |

## Resumo

| Métrica | Valor |
|---|---:|
| Trades | 127 |
| Acerto | 31.5% |
| Ganho médio / perda média (R) | 1.41 / -0.83 |
| Payoff | 1.69 |
| **Expectância** | **-0.127 R** |
| **Profit factor** | **0.82** |
| Resultado | -102.42 USDT (-10.2%) |
| Taxas pagas | 47.29 USDT |
| **Drawdown máximo** | **19.1%** |
| Tempo médio em posição | 35.3 h |
| Sinais / barrados / ordens / expiradas | 615 / 479 / 130 / 3 |

### Por setup

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| Pullback | 115 | 31.3% | -0.112 | 0.83 | -83.65 |
| Rompimento | 12 | 33.3% | -0.263 | 0.64 | -18.77 |

### Por regime na entrada

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| neutro | 18 | 22.2% | -0.428 | 0.34 | -36.74 |
| risk_on | 109 | 33.0% | -0.077 | 0.87 | -65.68 |

### Por faixa de score

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 70–75 | 57 | 29.8% | -0.093 | 0.87 | -34.95 |
| 75–80 | 52 | 32.7% | -0.167 | 0.77 | -49.24 |
| 80–90 | 17 | 35.3% | -0.082 | 0.83 | -11.65 |
| 90–100 | 1 | 0.0% | -0.693 | 0.00 | -6.59 |

### Por motivo de saída

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| breakeven | 27 | 77.8% | 0.576 | 230.78 | 119.64 |
| invalidacao | 24 | 8.3% | -0.489 | 0.20 | -89.99 |
| stop | 52 | 0.0% | -1.070 | 0.00 | -414.85 |
| tempo | 7 | 0.0% | -0.390 | 0.00 | -26.47 |
| tp2 | 17 | 100.0% | 2.261 | ∞ | 309.25 |

### Por mês

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 2025-04 | 7 | 42.9% | -0.220 | 0.73 | -10.02 |
| 2025-05 | 19 | 15.8% | -0.330 | 0.37 | -54.77 |
| 2025-06 | 3 | 66.7% | 1.308 | 7.06 | 35.83 |
| 2025-07 | 20 | 50.0% | 0.387 | 2.15 | 66.48 |
| 2025-08 | 8 | 0.0% | -0.881 | 0.00 | -60.48 |
| 2025-09 | 6 | 16.7% | -0.451 | 0.24 | -22.70 |
| 2025-10 | 6 | 33.3% | 0.046 | 1.10 | 2.30 |
| 2026-01 | 5 | 0.0% | -0.943 | 0.00 | -21.90 |
| 2026-04 | 6 | 16.7% | -0.651 | 0.15 | -17.33 |
| 2026-05 | 4 | 50.0% | 0.215 | 0.86 | -2.19 |
| 2026-07 | 3 | 33.3% | -0.232 | 0.46 | -3.50 |
| 2026-08 | 5 | 40.0% | -0.189 | 0.77 | -4.03 |
| 2026-09 | 26 | 42.3% | 0.142 | 1.15 | 19.33 |
| 2026-10 | 9 | 22.2% | -0.528 | 0.25 | -29.42 |

## Walk-forward (só períodos de teste)

| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|
| 21/05/2025 – 21/07/2025 | 24 | 0.409 | 2.12 | 86.02 |
| 21/07/2025 – 21/09/2025 | 20 | -0.620 | 0.09 | -101.79 |
| 21/09/2025 – 21/11/2025 | 6 | 0.046 | 1.10 | 2.30 |
| 21/11/2025 – 21/01/2026 | 5 | -0.943 | 0.00 | -21.90 |
| 21/01/2026 – 21/03/2026 | 0 | — | — | 0.00 |
| 21/03/2026 – 21/05/2026 | 10 | -0.305 | 0.45 | -19.51 |
| 21/05/2026 – 21/07/2026 | 2 | 0.177 | 1.69 | 1.21 |
| 21/07/2026 – 21/09/2026 | 20 | 0.266 | 1.48 | 40.83 |
| 21/09/2026 – 12/10/2026 | 21 | -0.399 | 0.45 | -59.67 |

### 10 maiores ganhos

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 11/05/2025 12:00 | PEPEUSDT | Pullback | 2.27 | 22.22 | tp2 |
| 15/07/2025 19:00 | ETHUSDT | Pullback | 2.27 | 22.18 | tp2 |
| 10/07/2025 23:00 | UNIUSDT | Pullback | 2.27 | 21.76 | tp2 |
| 13/07/2025 06:00 | XRPUSDT | Pullback | 2.27 | 21.56 | tp2 |
| 09/06/2025 18:00 | UNIUSDT | Pullback | 2.27 | 20.89 | tp2 |
| 09/06/2025 17:00 | AAVEUSDT | Pullback | 2.27 | 20.84 | tp2 |
| 24/09/2026 06:00 | AEROUSDT | Pullback | 2.27 | 20.81 | tp2 |
| 20/09/2026 17:00 | SUIUSDT | Pullback | 2.27 | 20.17 | tp2 |
| 05/09/2026 11:00 | ARBUSDT | Pullback | 2.27 | 20.15 | tp2 |
| 04/09/2026 15:00 | UNIUSDT | Pullback | 2.27 | 20.07 | tp2 |

### 10 maiores perdas

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 18/07/2025 11:00 | SUIUSDT | Pullback | -1.06 | -11.07 | stop |
| 13/08/2025 09:00 | GRAMUSDT | Pullback | -1.06 | -10.52 | stop |
| 25/04/2025 13:00 | CRVUSDT | Pullback | -1.05 | -10.47 | stop |
| 28/04/2025 21:00 | SUIUSDT | Pullback | -1.06 | -10.45 | stop |
| 12/08/2025 21:00 | UNIUSDT | Pullback | -1.04 | -10.31 | stop |
| 30/04/2025 13:00 | PEPEUSDT | Pullback | -1.05 | -10.29 | stop |
| 21/05/2025 18:00 | WLDUSDT | Rompimento | -1.06 | -10.24 | stop |
| 17/08/2025 17:00 | MNTUSDT | Pullback | -1.05 | -10.19 | stop |
| 11/05/2025 23:00 | STRKUSDT | Pullback | -1.05 | -10.19 | stop |
| 13/05/2025 17:00 | XRPUSDT | Pullback | -1.04 | -10.10 | stop |

## Por que os sinais foram barrados

| Motivo (primeiro) | Sinais |
|---|---:|
| pullback_tendencia: stop longo demais: #% > #% | 241 |
| pullback_tendencia: regime risk_off / circuit breaker: sem novas entradas | 87 |
| pullback_tendencia: limite de # posições/ordens no regime risk_on | 73 |
| pullback_tendencia: pausa após perdas seguidas | 21 |
| rompimento_compressao: regime risk_off / circuit breaker: sem novas entradas | 19 |
| rompimento_compressao: stop curto demais: #% < #% | 12 |
| ote_fibo: R:R até o TP# # < # | 8 |
| rompimento_compressao: pausa após perdas seguidas | 6 |
| pullback_tendencia: stop há menos de # h nesta moeda | 5 |
| rompimento_compressao: limite de # posições/ordens no regime risk_on | 5 |
| pullback_tendencia: limite de # posições/ordens no regime neutro | 1 |
| pullback_tendencia: perda do dia #% ≥ #% (até #:# UTC) | 1 |

## Eventos do motor de risco

- 2025-05-14 21:00 pausa: 3 perdas seguidas
- 2025-05-16 04:00 pausa: 3 perdas seguidas
- 2025-05-21 18:00 pausa: 3 perdas seguidas
- 2025-05-28 00:00 pausa: 3 perdas seguidas
- 2025-05-28 21:00 pausa: 3 perdas seguidas
- 2025-07-20 05:00 pausa: 3 perdas seguidas
- 2025-07-29 16:00 pausa: 3 perdas seguidas
- 2025-08-11 20:00 pausa: 3 perdas seguidas
- 2025-08-14 13:00 pausa: 3 perdas seguidas
- 2025-09-14 05:00 pausa: 3 perdas seguidas
- 2025-09-19 12:00 pausa: 3 perdas seguidas
- 2025-10-08 13:00 pausa: 3 perdas seguidas
- 2026-01-07 16:00 pausa: 3 perdas seguidas
- 2026-04-23 00:00 pausa: 3 perdas seguidas
- 2026-09-02 20:00 pausa: 3 perdas seguidas
- 2026-09-09 16:00 pausa: 3 perdas seguidas
- 2026-09-09 23:00 pausa: 3 perdas seguidas
- 2026-09-09 23:00 pausa semanal: drawdown 6.1% na semana
- 2026-10-01 16:00 pausa: 3 perdas seguidas
- 2026-10-07 02:00 pausa: 3 perdas seguidas

## Limitações

- Gemini desligado no backtest (veto qualitativo não simulado)
- Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas
- Spread e profundidade do livro não simulados (sem histórico)
- Universo = maiores moedas de hoje (viés de sobrevivência)
- Stop/alvo na mesma vela: considera o stop (conservador)
