# 02 — Plano de execução

Cada fase termina num **portão (gate)**: só avance quando todos os critérios
forem atendidos. Os prazos consideram você + Gemini trabalhando algumas horas
por dia; ajuste à sua realidade.

```
Construção (≈ 4–6 semanas)                        Validação (≈ 2–3 meses)            Real
F0 ─ F1 ─ F2 ─ F3 ─ F4 ─ F5(backtest) ─ F6 ─ F7 ─── F8 (paper + Bybit Demo) ─────── F9 ─ F10
```

| Fase | Nome | Duração estimada | Prompt (em 04) |
|---|---|---|---|
| 0 | Preparação, contas e segurança | 1–2 dias | — |
| 1 | Esqueleto do projeto + conector Bybit | 2–3 dias | Prompt Fase 1 |
| 2 | Dados de mercado + indicadores | 2–3 dias | Prompt Fase 2 |
| 3 | Universo, regime e score | 3–4 dias | Prompt Fase 3 |
| 4 | Gatilhos de entrada (3 setups) | 3–4 dias | Prompt Fase 4 |
| 5 | Backtest + walk-forward | 5–7 dias | Prompt Fase 5 |
| 6 | Risco, execução e analista Gemini | 4–5 dias | Prompt Fase 6 |
| 6B | Camada on-chain (Coinversa) em modo sombra | 2–3 dias | Prompt Fase 6B |
| 7 | Painel, alertas e deploy no Google Cloud | 2–3 dias | Prompt Fase 7 |
| 8 | Forward test (paper → Bybit Demo) | 4–8 semanas | Prompt Fase 8 |
| 9 | Conta real com capital pequeno | 4 semanas | — |
| 10 | Operação contínua e melhoria | contínuo | Prompt de revisão semanal |

---

## Fase 0 — Preparação, contas e segurança
**Fazer**: seção A e B do [checklist](01_CHECKLIST.md): subconta Bybit,
Demo Trading, projeto Google Cloud com alerta de orçamento, VM fora dos EUA
com IP estático, Secret Manager, acesso ao Gemini, Telegram, painel Lovable
com seu login e o `BOT_INGEST_TOKEN`.

**Gate 0**
- `curl https://api.bybit.com/v5/market/time` na VM → **HTTP 200**.
- Chaves da conta **demo** no Secret Manager (nenhuma chave em arquivo).
- Você consegue logar no painel e carregar os dados de demonstração.

## Fase 1 — Esqueleto + conector Bybit
**Entregáveis**: estrutura do projeto, `config.yaml` validado, cliente REST
V5 (assinatura, horário, retries, limites, erros), leitura das regras de
instrumento, leitura de saldo, criação/cancelamento de ordem na **conta demo**,
logs estruturados, testes.

**Gate 1**
- `pytest` 100 % verde.
- Script `python -m bot.tools.smoke_test` (em modo `demo`): lê saldo, baixa 200
  candles do BTCUSDT, cria uma ordem limite bem longe do preço e cancela.

## Fase 2 — Dados de mercado + indicadores
**Entregáveis**: coleta de tickers/klines/orderbook/OI/funding/long-short
com cache e paginação; indicadores com testes.

**Gate 2**
- Indicadores conferidos contra o TradingView em 3 moedas (diferença < 0,5 %).
- Download de 12 meses de candles 1H de 50 moedas salvo localmente (insumo do backtest).

## Fase 3 — Universo, regime e score
**Entregáveis**: filtro de universo, regime do BTC + amplitude + circuit
breaker, score 0–100 com detalhamento por componente, envio do ranking ao
painel (`scanner_run`).

**Gate 3**
- Scanner completo roda em **< 2 min** e aparece na página **Scanner** do painel.
- Você revisa manualmente as 5 primeiras moedas no gráfico e o score "faz sentido".

## Fase 4 — Gatilhos de entrada
**Entregáveis**: setups `pullback_tendencia`, `rompimento_compressao` e
`ote_fibo` (porta da lógica do EA MQL5 deste repositório), filtros comuns,
sinais enviados ao painel (`signal`).

**Gate 4**
- Testes unitários com candles sintéticos para cada setup (casos que devem e que **não** devem disparar).
- Sinais aparecem no painel com entrada/stop/alvos coerentes no gráfico.

## Fase 5 — Backtest + walk-forward
**Entregáveis**: motor de backtest orientado a eventos usando **o mesmo código**
de score/setups/risco/saídas, com taxas e slippage; relatório (HTML ou
markdown) com métricas por setup, regime, faixa de score.

**Gate 5 (critério de aprovação da estratégia)**
- ≥ 12 meses de dados incluindo período de baixa; ≥ 150 trades.
- Profit factor ≥ **1,3** e expectância ≥ **0,15 R** após custos.
- Drawdown máximo ≤ **20 %**.
- Walk-forward positivo fora da amostra.
- Nenhum trade isolado responsável por > 25 % do lucro.

> Se reprovar: mude **um** parâmetro/regra por vez, registre o motivo, e
> desconfie de resultados bons demais (overfitting). Desligar um setup que
> não funciona é uma decisão válida.

## Fase 6 — Risco, execução e analista Gemini
**Entregáveis**: motor de risco completo, executor (ordem limite → stop no
servidor → TP1 parcial → breakeven → trailing/tempo/invalidação),
reconciliação na inicialização, broker simulado, analista Gemini com JSON
validado e regra de falha, comandos `pause/resume` do painel.

**Gate 6 — cenários testados na conta demo**
- Entrada executada → stop aparece no servidor em < 5 s.
- TP1 parcial executa e o stop do restante vai para breakeven.
- Robô derrubado com posição aberta → ao voltar, reconcilia sem duplicar ordens.
- Kill switch e limite de perda diária bloqueiam novas entradas.
- Gemini fora do ar / JSON inválido → comportamento de falha correto.

## Fase 6B — Camada on-chain em modo sombra (opcional)
**Entregáveis**: `OnchainProvider` (Coinversa/Replay/Null), regras S1, F2, F3,
R2, R3 e R4 calculadas e **gravadas sem efeito**, exportação do histórico de
coortes, gravação contínua de snapshots. Detalhes em
[06_DADOS_ONCHAIN.md](06_DADOS_ONCHAIN.md).

**Gate 6B**
- Com `onchain.enabled=false` **e** com `mode=shadow`, o backtest gera
  exatamente os mesmos trades da estratégia base.
- Derrubar a Coinversa (chave inválida, timeout) não atrasa nem bloqueia
  nada no robô.

## Fase 7 — Painel, alertas e deploy
**Entregáveis**: Dockerfile, docker compose, script de setup da VM, leitura
de segredos do Secret Manager, heartbeat, envio de todos os eventos ao painel,
alertas no Telegram, backup diário.

**Gate 7**
- 72 h rodando na VM em modo `paper` sem intervenção.
- Painel mostra ONLINE continuamente; reiniciar a VM → robô volta sozinho.

## Fase 8 — Forward test (paper → Bybit Demo)
**Fazer**: 2 semanas em `paper` + ≥ 4 semanas em `demo`. Revisão semanal.

**Gate 8**
- ≥ 30 trades no demo; métricas dentro de ±30 % do backtest.
- Camada on-chain continua em shadow; o contrafactual de cada regra é
  revisado, e uma regra só é ativada se cumprir o critério pré-registrado.
- Zero erros críticos de execução; zero posições sem stop no servidor.

## Fase 9 — Conta real com capital pequeno
**Fazer**: chave real (IP fixo, sem saque), `mode: live`, risco 0,25–0,5 %
por trade, capital pequeno, 4 semanas.

**Gate 9**: mesma consistência do Gate 8 → aumentar capital no máximo +50 % ao mês.

## Fase 10 — Operação contínua
Rotina da seção F do checklist + prompt de revisão semanal (Gemini analisa o
diário de operações e **propõe** melhorias; nada é aplicado sem passar de novo
pelas Fases 5 e 8).

---

## Custos estimados (mensais, aproximados)

| Item | Estimativa |
|---|---|
| VM `e2-small` em São Paulo/Singapura + disco | US$ 15–25 |
| IP estático em uso | ~US$ 3–4 |
| Gemini (algumas centenas de análises/dia com modelo Flash; Pro só no sinal final) | US$ 2–15 |
| Cloud Logging / Storage / Secret Manager | < US$ 2 |
| Painel Lovable | conforme seu plano Lovable |

Confira os preços atuais no console do Google Cloud — eles mudam.

## Riscos principais e como o plano os trata

| Risco | Mitigação |
|---|---|
| Estratégia sem vantagem real | Gates 5 e 8 com critérios numéricos; capital pequeno na Fase 9 |
| Chave de API vazada | Sem permissão de saque, IP fixo, subconta, Secret Manager |
| Robô cai com posição aberta | Stop sempre no servidor da Bybit + reconciliação + alerta de OFFLINE |
| Ordem duplicada | `orderLinkId` idempotente + reconciliação |
| IA "alucina" | Gemini só veta/reduz; JSON validado; fallback definido |
| Bloqueio geográfico (403) | VM fora dos EUA, testado no Gate 0 |
| Overfitting | Walk-forward, uma mudança por vez, forward test longo |
| Dados on-chain enganosos ou fora do ar | Hyperliquid ≠ Bybit: camada opcional, só reduz risco, começa em shadow e é fail-open |
