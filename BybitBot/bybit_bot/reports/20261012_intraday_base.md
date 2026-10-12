# Backtest — intraday_base

Período: **21/11/2024 a 12/10/2026** · patrimônio inicial 1,000 USDT · gerado em 12/10/2026 18:54 UTC

## Gate 5: **REPROVADO**

| Critério | Resultado | |
|---|---|---|
| ≥ 12 meses de teste | 22.7 meses | ✅ |
| ≥ 150 trades | 361 | ✅ |
| Profit factor ≥ 1.3 | 0.92 | ❌ |
| Expectância ≥ 0.15 R | -0.091 R | ❌ |
| Drawdown máximo ≤ 20 % | 31.1 % | ❌ |
| Nenhum trade > 25 % do lucro | sem lucro | ❌ |
| Walk-forward positivo fora da amostra | 3/9 janelas positivas; expectância OOS -0.102 R | ❌ |

## Resumo

| Métrica | Valor |
|---|---:|
| Trades | 361 |
| Acerto | 36.8% |
| Ganho médio / perda média (R) | 1.54 / -1.04 |
| Payoff | 1.48 |
| **Expectância** | **-0.091 R** |
| **Profit factor** | **0.92** |
| Resultado | -104.99 USDT (-10.5%) |
| Taxas pagas | 153.68 USDT |
| **Drawdown máximo** | **31.1%** |
| Tempo médio em posição | 9.2 h |
| Sinais / barrados / ordens / expiradas | 2565 / 2195 / 365 / 4 |

### Por setup

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| OTE Fibo | 1 | 0.0% | -1.099 | 0.00 | -6.54 |
| Pullback | 356 | 36.5% | -0.101 | 0.91 | -114.25 |
| Rompimento | 4 | 75.0% | 1.067 | 4.16 | 15.80 |

### Por regime na entrada

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| neutro | 52 | 32.7% | -0.181 | 0.74 | -35.78 |
| risk_on | 309 | 37.5% | -0.076 | 0.94 | -69.21 |

### Por faixa de score

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 70–75 | 193 | 40.4% | 0.003 | 1.03 | 19.50 |
| 75–80 | 131 | 30.5% | -0.268 | 0.72 | -138.75 |
| 80–90 | 37 | 40.5% | 0.049 | 1.14 | 14.26 |

### Por motivo de saída

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| breakeven | 3 | 66.7% | 0.468 | 60.09 | 6.25 |
| invalidacao | 3 | 0.0% | -0.683 | 0.00 | -17.40 |
| stop | 203 | 0.0% | -1.112 | 0.00 | -1,161.15 |
| tempo | 21 | 0.0% | -0.466 | 0.00 | -65.65 |
| trailing | 131 | 100.0% | 1.552 | ∞ | 1,132.97 |

### Por mês

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 2025-04 | 17 | 47.1% | 0.275 | 1.76 | 42.32 |
| 2025-05 | 61 | 37.7% | -0.071 | 0.87 | -32.14 |
| 2025-06 | 9 | 22.2% | -0.571 | 0.21 | -31.58 |
| 2025-07 | 61 | 37.7% | -0.033 | 1.07 | 14.30 |
| 2025-08 | 37 | 37.8% | -0.102 | 0.82 | -23.17 |
| 2025-09 | 18 | 38.9% | -0.152 | 0.86 | -6.40 |
| 2025-10 | 7 | 14.3% | -0.603 | 0.18 | -25.44 |
| 2026-01 | 6 | 0.0% | -1.104 | 0.00 | -28.22 |
| 2026-03 | 4 | 50.0% | 0.289 | 1.65 | 4.20 |
| 2026-04 | 7 | 28.6% | -0.313 | 0.59 | -9.72 |
| 2026-05 | 14 | 21.4% | -0.384 | 0.44 | -28.31 |
| 2026-07 | 9 | 22.2% | -0.628 | 0.26 | -21.13 |
| 2026-08 | 17 | 29.4% | -0.293 | 0.65 | -23.45 |
| 2026-09 | 70 | 44.3% | 0.069 | 1.14 | 29.67 |
| 2026-10 | 24 | 41.7% | 0.147 | 1.41 | 34.08 |

## Walk-forward (só períodos de teste)

| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|
| 21/05/2025 – 21/07/2025 | 78 | 0.079 | 1.26 | 60.20 |
| 21/07/2025 – 21/09/2025 | 74 | -0.246 | 0.68 | -83.57 |
| 21/09/2025 – 21/11/2025 | 7 | -0.603 | 0.18 | -25.44 |
| 21/11/2025 – 21/01/2026 | 6 | -1.104 | 0.00 | -28.22 |
| 21/01/2026 – 21/03/2026 | 4 | 0.289 | 1.65 | 4.20 |
| 21/03/2026 – 21/05/2026 | 18 | -0.235 | 0.60 | -24.18 |
| 21/05/2026 – 21/07/2026 | 5 | -0.650 | 0.22 | -14.29 |
| 21/07/2026 – 21/09/2026 | 57 | -0.193 | 0.73 | -54.29 |
| 21/09/2026 – 12/10/2026 | 61 | 0.142 | 1.40 | 73.90 |

### 10 maiores ganhos

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 10/10/2026 13:45 | STRKUSDT | Pullback | 6.01 | 49.50 | trailing |
| 22/04/2025 04:00 | PEPEUSDT | Pullback | 2.10 | 20.72 | trailing |
| 25/04/2025 14:30 | FETUSDT | Pullback | 2.27 | 20.39 | trailing |
| 17/07/2025 06:30 | XRPUSDT | Pullback | 1.83 | 19.19 | trailing |
| 10/05/2025 13:30 | NEARUSDT | Pullback | 2.89 | 17.25 | trailing |
| 14/07/2025 00:00 | SUIUSDT | Pullback | 3.34 | 16.38 | trailing |
| 09/05/2025 17:45 | DOGEUSDT | Pullback | 2.43 | 15.89 | trailing |
| 22/05/2025 22:30 | PEPEUSDT | Pullback | 2.18 | 15.42 | trailing |
| 23/08/2026 17:00 | LITUSDT | Pullback | 1.76 | 15.17 | trailing |
| 08/07/2025 16:45 | UNIUSDT | Pullback | 3.42 | 14.95 | trailing |

### 10 maiores perdas

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 17/07/2025 21:30 | ONDOUSDT | Pullback | -1.06 | -11.17 | stop |
| 12/05/2025 14:15 | NEARUSDT | Pullback | -1.06 | -10.86 | stop |
| 21/07/2025 23:00 | TIAUSDT | Pullback | -1.06 | -10.83 | stop |
| 23/05/2025 09:00 | FETUSDT | Pullback | -1.06 | -10.78 | stop |
| 09/05/2025 11:00 | SUIUSDT | Pullback | -1.06 | -10.58 | stop |
| 19/05/2025 00:15 | DOGEUSDT | Pullback | -1.04 | -10.46 | stop |
| 19/05/2025 00:15 | PEPEUSDT | Pullback | -1.03 | -10.40 | stop |
| 26/07/2025 20:45 | CRVUSDT | Pullback | -1.05 | -10.32 | stop |
| 21/05/2025 12:45 | PEPEUSDT | Pullback | -1.05 | -10.28 | stop |
| 17/08/2025 05:30 | AEROUSDT | Pullback | -1.04 | -10.05 | stop |

## Por que os sinais foram barrados

| Motivo (primeiro) | Sinais |
|---|---:|
| pullback_tendencia: regime risk_off / circuit breaker: sem novas entradas | 564 |
| pullback_tendencia: pausa após perdas seguidas | 448 |
| pullback_tendencia: stop curto demais: #% < #% | 377 |
| pullback_tendencia: stop há menos de # h nesta moeda | 240 |
| pullback_tendencia: limite de # posições/ordens no regime risk_on | 230 |
| rompimento_compressao: stop curto demais: #% < #% | 138 |
| ote_fibo: R:R até o TP# # < # | 86 |
| pullback_tendencia: stop longo demais: #% > #% | 58 |
| rompimento_compressao: regime risk_off / circuit breaker: sem novas entradas | 25 |
| pullback_tendencia: limite de # posições/ordens no regime neutro | 9 |
| pullback_tendencia: pausa por drawdown semanal | 9 |
| rompimento_compressao: pausa após perdas seguidas | 4 |
| ote_fibo: regime risk_off / circuit breaker: sem novas entradas | 2 |
| rompimento_compressao: stop há menos de # h nesta moeda | 2 |
| rompimento_compressao: limite de # posições/ordens no regime risk_on | 2 |
| ote_fibo: stop curto demais: #% < #% | 1 |

## Eventos do motor de risco

- 2025-04-28 00:15 pausa: 3 perdas seguidas
- 2025-05-01 18:00 pausa: 3 perdas seguidas
- 2025-05-11 13:45 pausa: 3 perdas seguidas
- 2025-05-11 14:00 pausa: 3 perdas seguidas
- 2025-05-12 18:45 pausa: 3 perdas seguidas
- 2025-05-14 08:15 pausa: 3 perdas seguidas
- 2025-05-19 04:45 pausa: 3 perdas seguidas
- 2025-05-23 12:00 pausa: 3 perdas seguidas
- 2025-05-23 12:15 pausa: 3 perdas seguidas
- 2025-05-27 20:30 pausa: 3 perdas seguidas
- 2025-06-12 07:45 pausa: 3 perdas seguidas
- 2025-07-16 06:15 pausa: 3 perdas seguidas
- 2025-07-18 20:30 pausa: 3 perdas seguidas
- 2025-07-20 22:15 pausa: 3 perdas seguidas
- 2025-07-20 22:30 pausa: 3 perdas seguidas
- 2025-07-22 01:30 pausa: 3 perdas seguidas
- 2025-07-23 06:30 pausa: 3 perdas seguidas
- 2025-07-28 13:30 pausa: 3 perdas seguidas
- 2025-08-08 15:15 pausa: 3 perdas seguidas
- 2025-08-10 07:45 pausa: 3 perdas seguidas
- 2025-08-14 08:45 pausa: 3 perdas seguidas
- 2025-08-16 04:30 pausa: 3 perdas seguidas
- 2025-08-18 03:00 pausa: 3 perdas seguidas
- 2025-08-29 06:45 pausa: 3 perdas seguidas
- 2025-09-13 14:00 pausa: 3 perdas seguidas
- 2025-09-19 04:15 pausa: 3 perdas seguidas
- 2025-10-07 06:15 pausa: 3 perdas seguidas
- 2026-01-06 18:00 pausa: 3 perdas seguidas
- 2026-01-14 12:00 pausa: 3 perdas seguidas
- 2026-04-11 01:30 pausa: 3 perdas seguidas
- 2026-05-04 00:30 pausa: 3 perdas seguidas
- 2026-05-12 04:30 pausa: 3 perdas seguidas
- 2026-05-15 04:45 pausa: 3 perdas seguidas
- 2026-05-22 05:15 pausa: 3 perdas seguidas
- 2026-07-27 14:45 pausa: 3 perdas seguidas
- 2026-08-24 10:30 pausa: 3 perdas seguidas
- 2026-08-25 21:00 pausa: 3 perdas seguidas
- 2026-08-28 02:00 pausa semanal: drawdown 6.1% na semana
- 2026-08-28 05:00 pausa: 3 perdas seguidas
- 2026-09-01 22:30 pausa: 3 perdas seguidas
- 2026-09-04 12:45 pausa: 3 perdas seguidas
- 2026-09-06 12:45 pausa: 3 perdas seguidas
- 2026-09-08 12:00 pausa: 3 perdas seguidas
- 2026-09-17 15:15 pausa: 3 perdas seguidas
- 2026-09-20 03:30 pausa: 3 perdas seguidas
- 2026-09-21 20:15 pausa: 3 perdas seguidas
- 2026-09-23 12:15 pausa: 3 perdas seguidas
- 2026-09-28 03:45 pausa: 3 perdas seguidas
- 2026-10-01 08:00 pausa: 3 perdas seguidas
- 2026-10-07 02:15 pausa: 3 perdas seguidas

## Limitações

- Gemini desligado no backtest (veto qualitativo não simulado)
- Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas
- Spread e profundidade do livro não simulados (sem histórico)
- Universo = maiores moedas de hoje (viés de sobrevivência)
- Stop/alvo na mesma vela: considera o stop (conservador)
