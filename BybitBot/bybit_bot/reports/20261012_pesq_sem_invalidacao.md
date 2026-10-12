# Backtest — pesq_sem_invalidacao

Período: **21/11/2024 a 12/10/2026** · patrimônio inicial 1,000 USDT · gerado em 12/10/2026 18:12 UTC

## Gate 5: **REPROVADO**

| Critério | Resultado | |
|---|---|---|
| ≥ 12 meses de teste | 22.7 meses | ✅ |
| ≥ 150 trades | 136 | ❌ |
| Profit factor ≥ 1.3 | 0.85 | ❌ |
| Expectância ≥ 0.15 R | -0.090 R | ❌ |
| Drawdown máximo ≤ 20 % | 16.5 % | ✅ |
| Nenhum trade > 25 % do lucro | sem lucro | ❌ |
| Walk-forward positivo fora da amostra | 4/8 janelas positivas; expectância OOS -0.068 R | ❌ |

## Resumo

| Métrica | Valor |
|---|---:|
| Trades | 136 |
| Acerto | 33.1% |
| Ganho médio / perda média (R) | 1.57 / -0.91 |
| Payoff | 1.72 |
| **Expectância** | **-0.090 R** |
| **Profit factor** | **0.85** |
| Resultado | -95.89 USDT (-9.6%) |
| Taxas pagas | 50.66 USDT |
| **Drawdown máximo** | **16.5%** |
| Tempo médio em posição | 37.7 h |
| Sinais / barrados / ordens / expiradas | 608 / 463 / 139 / 3 |

### Por setup

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| Pullback | 124 | 33.1% | -0.095 | 0.83 | -100.08 |
| Rompimento | 12 | 33.3% | -0.040 | 1.09 | 4.19 |

### Por regime na entrada

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| neutro | 19 | 26.3% | -0.263 | 0.58 | -24.63 |
| risk_on | 117 | 34.2% | -0.062 | 0.88 | -71.26 |

### Por faixa de score

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 70–75 | 65 | 33.8% | -0.049 | 0.94 | -18.41 |
| 75–80 | 55 | 29.1% | -0.231 | 0.60 | -110.14 |
| 80–90 | 15 | 46.7% | 0.274 | 1.84 | 37.70 |
| 90–100 | 1 | 0.0% | -0.538 | 0.00 | -5.05 |

### Por motivo de saída

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| breakeven | 13 | 30.8% | 0.223 | 30.22 | 20.97 |
| stop | 74 | 0.0% | -1.065 | 0.00 | -616.49 |
| tempo | 9 | 11.1% | -0.445 | 0.00 | -37.83 |
| trailing | 40 | 100.0% | 1.690 | ∞ | 537.46 |

### Por mês

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 2025-04 | 8 | 37.5% | -0.173 | 0.82 | -8.65 |
| 2025-05 | 22 | 13.6% | -0.479 | 0.21 | -91.02 |
| 2025-06 | 3 | 66.7% | 1.291 | 4.50 | 33.86 |
| 2025-07 | 26 | 57.7% | 0.414 | 2.20 | 95.34 |
| 2025-08 | 8 | 12.5% | -0.923 | 0.00 | -65.35 |
| 2025-09 | 6 | 16.7% | -0.396 | 0.41 | -19.24 |
| 2025-10 | 6 | 33.3% | 0.182 | 1.29 | 8.28 |
| 2026-01 | 5 | 0.0% | -1.054 | 0.00 | -24.37 |
| 2026-04 | 6 | 16.7% | -0.503 | 0.31 | -13.25 |
| 2026-05 | 4 | 50.0% | 0.711 | 1.40 | 6.12 |
| 2026-07 | 4 | 25.0% | -0.166 | 0.68 | -2.98 |
| 2026-08 | 5 | 40.0% | -0.036 | 1.19 | 2.84 |
| 2026-09 | 23 | 43.5% | 0.285 | 1.35 | 43.65 |
| 2026-10 | 10 | 20.0% | -0.663 | 0.10 | -61.12 |

## Walk-forward (só períodos de teste)

| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|
| 21/05/2025 – 21/07/2025 | 29 | 0.436 | 2.32 | 117.22 |
| 21/07/2025 – 21/09/2025 | 24 | -0.636 | 0.16 | -131.55 |
| 21/09/2025 – 21/11/2025 | 6 | 0.182 | 1.29 | 8.28 |
| 21/11/2025 – 21/01/2026 | 5 | -1.054 | 0.00 | -24.37 |
| 21/01/2026 – 21/03/2026 | 0 | — | — | 0.00 |
| 21/03/2026 – 21/05/2026 | 10 | -0.017 | 0.79 | -7.12 |
| 21/05/2026 – 21/07/2026 | 2 | 0.769 | 84.28 | 6.13 |
| 21/07/2026 – 21/09/2026 | 20 | 0.530 | 2.36 | 99.58 |
| 21/09/2026 – 12/10/2026 | 20 | -0.653 | 0.15 | -123.33 |

### 10 maiores ganhos

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 05/09/2026 11:00 | ARBUSDT | Pullback | 3.82 | 34.82 | trailing |
| 17/09/2026 10:00 | UNIUSDT | Rompimento | 3.85 | 33.91 | trailing |
| 04/10/2025 12:00 | MNTUSDT | Pullback | 3.51 | 28.98 | trailing |
| 09/06/2025 18:00 | UNIUSDT | Pullback | 2.67 | 23.68 | trailing |
| 19/07/2025 05:00 | ENAUSDT | Pullback | 2.08 | 20.85 | trailing |
| 20/09/2026 17:00 | SUIUSDT | Pullback | 2.17 | 20.76 | trailing |
| 09/06/2025 17:00 | AAVEUSDT | Pullback | 2.25 | 19.85 | trailing |
| 04/09/2026 15:00 | UNIUSDT | Pullback | 1.95 | 17.69 | trailing |
| 20/09/2026 17:00 | ADAUSDT | Pullback | 1.81 | 15.50 | trailing |
| 20/05/2026 07:00 | NEARUSDT | Pullback | 3.48 | 15.50 | trailing |

### 10 maiores perdas

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 22/07/2025 03:00 | LTCUSDT | Pullback | -1.06 | -10.94 | stop |
| 22/07/2025 03:00 | PEPEUSDT | Pullback | -1.03 | -10.80 | stop |
| 22/09/2026 18:00 | LTCUSDT | Pullback | -1.06 | -10.63 | stop |
| 10/08/2025 17:00 | CRVUSDT | Pullback | -1.05 | -10.60 | stop |
| 13/08/2025 09:00 | GRAMUSDT | Pullback | -1.06 | -10.60 | stop |
| 10/08/2025 20:00 | LTCUSDT | Pullback | -1.05 | -10.57 | stop |
| 22/09/2026 15:00 | AVAXUSDT | Pullback | -1.04 | -10.56 | stop |
| 28/04/2025 21:00 | SUIUSDT | Pullback | -1.06 | -10.51 | stop |
| 22/09/2026 11:00 | VVVUSDT | Pullback | -1.03 | -10.49 | stop |
| 25/04/2025 13:00 | CRVUSDT | Pullback | -1.05 | -10.49 | stop |

## Por que os sinais foram barrados

| Motivo (primeiro) | Sinais |
|---|---:|
| pullback_tendencia: stop longo demais: #% > #% | 238 |
| pullback_tendencia: regime risk_off / circuit breaker: sem novas entradas | 87 |
| pullback_tendencia: limite de # posições/ordens no regime risk_on | 68 |
| rompimento_compressao: regime risk_off / circuit breaker: sem novas entradas | 19 |
| pullback_tendencia: pausa após perdas seguidas | 17 |
| rompimento_compressao: stop curto demais: #% < #% | 10 |
| ote_fibo: R:R até o TP# # < # | 9 |
| pullback_tendencia: stop há menos de # h nesta moeda | 5 |
| rompimento_compressao: limite de # posições/ordens no regime risk_on | 4 |
| rompimento_compressao: pausa após perdas seguidas | 3 |
| pullback_tendencia: perda do dia #% ≥ #% (até #:# UTC) | 1 |
| pullback_tendencia: limite de # posições/ordens no regime neutro | 1 |
| pullback_tendencia: pausa por drawdown semanal | 1 |

## Eventos do motor de risco

- 2025-04-30 14:00 pausa: 3 perdas seguidas
- 2025-05-14 21:00 pausa: 3 perdas seguidas
- 2025-05-16 04:00 pausa: 3 perdas seguidas
- 2025-05-21 18:00 pausa: 3 perdas seguidas
- 2025-05-28 00:00 pausa: 3 perdas seguidas
- 2025-05-29 15:00 pausa: 3 perdas seguidas
- 2025-05-30 01:00 pausa: 3 perdas seguidas
- 2025-07-29 16:00 pausa: 3 perdas seguidas
- 2025-08-11 20:00 pausa: 3 perdas seguidas
- 2025-08-15 16:00 pausa: 3 perdas seguidas
- 2025-09-20 03:00 pausa: 3 perdas seguidas
- 2025-10-08 13:00 pausa: 3 perdas seguidas
- 2026-01-07 15:00 pausa: 3 perdas seguidas
- 2026-01-19 01:00 pausa: 3 perdas seguidas
- 2026-04-23 01:00 pausa: 3 perdas seguidas
- 2026-07-29 21:00 pausa: 3 perdas seguidas
- 2026-09-09 16:00 pausa: 3 perdas seguidas
- 2026-09-10 13:00 pausa semanal: drawdown 6.0% na semana
- 2026-09-11 16:00 pausa: 3 perdas seguidas
- 2026-09-23 16:00 pausa: 3 perdas seguidas
- 2026-09-28 20:00 pausa: 3 perdas seguidas
- 2026-10-02 19:00 pausa: 3 perdas seguidas
- 2026-10-02 19:00 pausa semanal: drawdown 7.2% na semana
- 2026-10-07 02:00 pausa: 3 perdas seguidas

## Limitações

- Gemini desligado no backtest (veto qualitativo não simulado)
- Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas
- Spread e profundidade do livro não simulados (sem histórico)
- Universo = maiores moedas de hoje (viés de sobrevivência)
- Stop/alvo na mesma vela: considera o stop (conservador)
