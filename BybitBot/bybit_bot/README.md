# bybit_bot — código do robô

Especificação nos documentos da pasta acima (`../README.md`, `../02_PLANO_DE_EXECUCAO.md`,
`../03_ESTRATEGIA.md`, `../04_PROMPTS_GOOGLE.md`). Parâmetros em `config/config.yaml`
(cópia de `../config.example.yaml`; os dois devem ficar iguais — um teste confere).

## Estado

| Fase | Situação |
|---|---|
| 1 — Esqueleto + conector Bybit | ✅ pytest verde e smoke test aprovado na conta demo (11/10/2026) |
| 2 — Dados de mercado + indicadores | 🟡 testes verdes e histórico baixado; falta a conferência com o TradingView (você) |

## O que existe

```
src/bot/
  config.py            # pydantic de TODOS os campos; campo desconhecido = erro; live exige CONFIRM_LIVE=SIM
  secrets.py           # Secret Manager (com GCP_PROJECT) ou variáveis de ambiente/.env
  logging_setup.py     # logs JSON; segredos lidos são mascarados como ***
  bybit/client.py      # REST V5: assinatura, relógio, limitador, retentativas, idempotência
  bybit/errors.py      # exceções por retCode
  bybit/instruments.py # tickSize/basePrecision/mínimos; quantidade sempre para baixo
  tools/smoke_test.py  # teste de ponta a ponta na conta DEMO
  data/market_data.py  # velas (só fechadas, paginação, cache, SQLite), tickers, livro, derivativos
  storage/kline_store.py
  indicators/core.py   # EMA, RMA, RSI, ATR, DMI/ADX, MACD, Bollinger + percentil, OBV, CMF, fractais
  backtest/data_loader.py      # baixa 13 meses de 1H/4H/1D das 50 maiores + BTC
  tools/indicator_snapshot.py  # indicadores da última vela fechada (conferência com o TradingView)
tests/                 # Bybit simulada; nenhum teste chama a API real
```

### Dados de derivativos
O score usa open interest, funding e razão long/short do **perpétuo linear de mesmo nome**
(ex.: BTCUSDT). São consultas públicas: o cliente aceita `category=linear` só para dados de
mercado; ordens e chamadas privadas continuam só `spot`. Falha num desses dados = campo ausente
(o robô segue sem ele).

### Indicadores (iguais ao TradingView)
EMA semeada com média simples; RSI, ATR e ADX de Wilder (RMA); desvio populacional nas Bandas.
Cada valor usa só a vela atual e as anteriores (teste automático para todos, com controle negativo).
Fractais aparecem na vela em que ficam **confirmados** (pivô + 5 velas), nunca antes.
A EMA200 precisa de aquecimento: use ≥ 1000 velas para bater com o TradingView.

### Conferência do Gate 2
```bash
.venv\Scripts\python -m bot.tools.indicator_snapshot --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 240
```
No TradingView, abra `BYBIT:BTCUSDT` (spot) no mesmo tempo gráfico, passe o mouse na vela indicada
e compare EMA 20/50/200, RSI 14 e ATR 14 (diferença aceitável < 0,5 %).

### Histórico para o backtest
```bash
.venv\Scripts\python -m bot.backtest.data_loader   # padrão do config: 13 meses, top 50, 1H/4H/1D
```
Grava em `data/history.db` (fora do Git) e a lista em `data/history_symbols.json`. Rodar de novo só
baixa o que falta. Limitação: as 50 maiores de **hoje** → viés de sobrevivência no backtest.

### Travas de segurança do cliente
- Só a categoria `spot` passa (`CategoryNotAllowedError` antes de qualquer chamada). Na Conta
  Unificada a chave tem derivativos em bloco; o código é quem impede.
- Só os endpoints privados da lista `PRIVATE_ENDPOINTS` (saldo, chave, criar/cancelar/consultar
  ordens, execuções). Não existe caminho para saque, transferência, alavancagem ou posições.
- Criação de ordem nunca é reenviada às cegas: falha ambígua → procura pelo `orderLinkId`;
  `orderLinkId` repetido (retCode 170141 no spot) → devolve a ordem existente.

### Comportamentos da Bybit confirmados na conta demo
- `orderLinkId` repetido no spot: **retCode 170141**.
- `/v5/order/realtime` consultado por `orderLinkId` devolve também ordens **fechadas** há pouco
  (ex.: `Cancelled`). Por isso `get_open_orders` filtra por status e `find_order` usa a resposta crua.
- BTCUSDT: tick 0.1, passo 0.000001, valor mínimo 5 USDT; 390 pares USDT no spot.

## Desenvolvimento local (Windows)

```bash
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check src tests
```

No PC, chamadas privadas à Bybit falham com `BybitIPNotAllowedError` (a chave só aceita o IP da VM).

## Na VM (`bybit-bot-vm`, IP 34.151.204.72)

```bash
gcloud compute ssh bybit-bot-vm --zone=southamerica-east1-a --tunnel-through-iap
cd ~/app/bybit_bot
python3 -m venv .venv && .venv/bin/pip install -e ".[gcp,dev]"
.venv/bin/python -m pytest
GCP_PROJECT=bybit-scanner-bot .venv/bin/python -m bot.tools.smoke_test --symbol BTCUSDT
```
