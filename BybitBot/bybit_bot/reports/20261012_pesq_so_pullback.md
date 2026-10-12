# Backtest — pesq_so_pullback

Período: **21/11/2024 a 12/10/2026** · patrimônio inicial 1,000 USDT · gerado em 12/10/2026 18:18 UTC

## Gate 5: **REPROVADO**

| Critério | Resultado | |
|---|---|---|
| ≥ 12 meses de teste | 22.7 meses | ✅ |
| ≥ 150 trades | 123 | ❌ |
| Profit factor ≥ 1.3 | 0.92 | ❌ |
| Expectância ≥ 0.15 R | -0.058 R | ❌ |
| Drawdown máximo ≤ 20 % | 18.4 % | ✅ |
| Nenhum trade > 25 % do lucro | sem lucro | ❌ |
| Walk-forward positivo fora da amostra | 4/8 janelas positivas; expectância OOS -0.043 R | ❌ |

## Resumo

| Métrica | Valor |
|---|---:|
| Trades | 123 |
| Acerto | 32.5% |
| Ganho médio / perda média (R) | 1.56 / -0.84 |
| Payoff | 1.86 |
| **Expectância** | **-0.058 R** |
| **Profit factor** | **0.92** |
| Resultado | -46.67 USDT (-4.7%) |
| Taxas pagas | 47.98 USDT |
| **Drawdown máximo** | **18.4%** |
| Tempo médio em posição | 31.8 h |
| Sinais / barrados / ordens / expiradas | 545 / 422 / 123 / 0 |

### Por setup

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| Pullback | 123 | 32.5% | -0.058 | 0.92 | -46.67 |

### Por regime na entrada

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| neutro | 16 | 18.8% | -0.282 | 0.55 | -24.71 |
| risk_on | 107 | 34.6% | -0.024 | 0.96 | -21.96 |

### Por faixa de score

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 70–75 | 64 | 34.4% | 0.015 | 1.03 | 10.20 |
| 75–80 | 47 | 29.8% | -0.165 | 0.76 | -55.98 |
| 80–90 | 11 | 36.4% | 0.034 | 1.16 | 6.25 |
| 90–100 | 1 | 0.0% | -0.693 | 0.00 | -7.14 |

### Por motivo de saída

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| breakeven | 9 | 44.4% | 0.328 | 49.71 | 22.39 |
| invalidacao | 23 | 0.0% | -0.615 | 0.00 | -124.53 |
| stop | 51 | 0.0% | -1.062 | 0.00 | -460.00 |
| tempo | 4 | 0.0% | -0.303 | 0.00 | -12.14 |
| trailing | 36 | 100.0% | 1.653 | ∞ | 527.61 |

### Por mês

| Grupo | Trades | Acerto | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|---:|
| 2025-04 | 7 | 42.9% | 0.002 | 0.99 | -0.20 |
| 2025-05 | 17 | 17.6% | -0.293 | 0.33 | -49.75 |
| 2025-06 | 3 | 66.7% | 1.434 | 7.62 | 39.91 |
| 2025-07 | 22 | 63.6% | 0.542 | 2.79 | 122.00 |
| 2025-08 | 7 | 0.0% | -0.859 | 0.00 | -53.82 |
| 2025-09 | 6 | 16.7% | -0.338 | 0.46 | -17.54 |
| 2025-10 | 6 | 33.3% | 0.266 | 1.55 | 14.42 |
| 2026-01 | 5 | 0.0% | -0.943 | 0.00 | -24.15 |
| 2026-04 | 4 | 0.0% | -0.864 | 0.00 | -17.33 |
| 2026-05 | 4 | 50.0% | 0.711 | 1.40 | 6.78 |
| 2026-07 | 4 | 25.0% | -0.261 | 0.57 | -5.17 |
| 2026-08 | 4 | 50.0% | 0.164 | 1.47 | 6.24 |
| 2026-09 | 22 | 36.4% | 0.036 | 0.90 | -14.01 |
| 2026-10 | 12 | 16.7% | -0.583 | 0.20 | -54.04 |

## Walk-forward (só períodos de teste)

| Janela de teste | Trades | Expectância (R) | Profit factor | Resultado (USDT) |
|---|---:|---:|---:|---:|
| 21/05/2025 – 21/07/2025 | 22 | 0.885 | 5.99 | 190.53 |
| 21/07/2025 – 21/09/2025 | 21 | -0.648 | 0.15 | -121.04 |
| 21/09/2025 – 21/11/2025 | 6 | 0.266 | 1.55 | 14.42 |
| 21/11/2025 – 21/01/2026 | 5 | -0.943 | 0.00 | -24.15 |
| 21/01/2026 – 21/03/2026 | 0 | — | — | 0.00 |
| 21/03/2026 – 21/05/2026 | 8 | -0.076 | 0.69 | -10.55 |
| 21/05/2026 – 21/07/2026 | 2 | 0.580 | 3.50 | 4.91 |
| 21/07/2026 – 21/09/2026 | 19 | 0.239 | 1.44 | 41.82 |
| 21/09/2026 – 12/10/2026 | 21 | -0.585 | 0.21 | -113.71 |

### 10 maiores ganhos

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 05/09/2026 11:00 | ARBUSDT | Pullback | 3.82 | 38.15 | trailing |
| 04/10/2025 12:00 | MNTUSDT | Pullback | 3.51 | 31.92 | trailing |
| 09/06/2025 18:00 | UNIUSDT | Pullback | 2.67 | 24.99 | trailing |
| 19/07/2025 05:00 | ENAUSDT | Pullback | 2.08 | 22.50 | trailing |
| 20/09/2026 17:00 | SUIUSDT | Pullback | 2.17 | 21.56 | trailing |
| 09/06/2025 17:00 | AAVEUSDT | Pullback | 2.25 | 20.94 | trailing |
| 04/09/2026 15:00 | UNIUSDT | Pullback | 1.95 | 19.39 | trailing |
| 20/05/2026 07:00 | NEARUSDT | Pullback | 3.48 | 17.16 | trailing |
| 19/07/2025 05:00 | WLDUSDT | Pullback | 1.54 | 16.70 | trailing |
| 15/07/2025 19:00 | XRPUSDT | Pullback | 1.64 | 16.59 | trailing |

### 10 maiores perdas

| Entrada | Par | Setup | R | USDT | Saída |
|---|---|---|---:|---:|---|
| 22/07/2025 03:00 | LTCUSDT | Pullback | -1.06 | -11.81 | stop |
| 22/07/2025 03:00 | PEPEUSDT | Pullback | -1.03 | -11.65 | stop |
| 13/08/2025 09:00 | GRAMUSDT | Pullback | -1.06 | -11.19 | stop |
| 17/07/2025 11:00 | SUIUSDT | Pullback | -1.04 | -11.13 | stop |
| 07/09/2026 01:00 | AAVEUSDT | Pullback | -1.06 | -11.11 | stop |
| 17/08/2025 17:00 | MNTUSDT | Pullback | -1.05 | -11.04 | stop |
| 22/09/2026 18:00 | LTCUSDT | Pullback | -1.06 | -11.04 | stop |
| 06/09/2026 21:00 | ASTERUSDT | Pullback | -1.05 | -11.03 | stop |
| 22/09/2026 15:00 | AVAXUSDT | Pullback | -1.04 | -10.96 | stop |
| 22/09/2026 11:00 | VVVUSDT | Pullback | -1.03 | -10.90 | stop |

## Por que os sinais foram barrados

| Motivo (primeiro) | Sinais |
|---|---:|
| pullback_tendencia: stop longo demais: #% > #% | 242 |
| pullback_tendencia: regime risk_off / circuit breaker: sem novas entradas | 87 |
| pullback_tendencia: limite de # posições/ordens no regime risk_on | 64 |
| pullback_tendencia: pausa após perdas seguidas | 23 |
| pullback_tendencia: stop há menos de # h nesta moeda | 3 |
| pullback_tendencia: perda do dia #% ≥ #% (até #:# UTC) | 1 |
| pullback_tendencia: limite de # posições/ordens no regime neutro | 1 |
| pullback_tendencia: pausa por drawdown semanal | 1 |

## Eventos do motor de risco

- 2025-04-30 14:00 pausa: 3 perdas seguidas
- 2025-05-14 21:00 pausa: 3 perdas seguidas
- 2025-05-16 04:00 pausa: 3 perdas seguidas
- 2025-05-23 12:00 pausa: 3 perdas seguidas
- 2025-05-28 08:00 pausa: 3 perdas seguidas
- 2025-07-28 14:00 pausa: 3 perdas seguidas
- 2025-08-11 12:00 pausa: 3 perdas seguidas
- 2025-08-12 00:00 pausa: 3 perdas seguidas
- 2025-08-24 12:00 pausa: 3 perdas seguidas
- 2025-09-19 20:00 pausa: 3 perdas seguidas
- 2025-10-08 13:00 pausa: 3 perdas seguidas
- 2026-01-07 16:00 pausa: 3 perdas seguidas
- 2026-04-18 17:00 pausa: 3 perdas seguidas
- 2026-04-23 04:00 pausa: 3 perdas seguidas
- 2026-07-29 21:00 pausa: 3 perdas seguidas
- 2026-09-09 16:00 pausa: 3 perdas seguidas
- 2026-09-09 23:00 pausa: 3 perdas seguidas
- 2026-09-09 23:00 pausa semanal: drawdown 6.1% na semana
- 2026-09-23 16:00 pausa: 3 perdas seguidas
- 2026-09-28 20:00 pausa: 3 perdas seguidas
- 2026-10-02 19:00 pausa: 3 perdas seguidas
- 2026-10-02 19:00 pausa semanal: drawdown 6.6% na semana
- 2026-10-07 02:00 pausa: 3 perdas seguidas

## Limitações

- Gemini desligado no backtest (veto qualitativo não simulado)
- Sem histórico de derivativos: componente de derivativos com pontuação neutra para todas
- Spread e profundidade do livro não simulados (sem histórico)
- Universo = maiores moedas de hoje (viés de sobrevivência)
- Stop/alvo na mesma vela: considera o stop (conservador)
