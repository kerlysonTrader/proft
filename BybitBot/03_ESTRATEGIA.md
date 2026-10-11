# 03 — Especificação da Estratégia (o "cérebro" do robô)

> Este documento é a **regra de negócio** que o código deve implementar.
> Todos os números abaixo são **valores iniciais** e ficam em
> `config.example.yaml` — nunca fixos no código. Eles **precisam** ser
> validados no backtest (Fase 5) e no forward test (Fase 8) antes de
> qualquer capital real.

## 0. Princípios

1. **Ninguém prevê o mercado.** O objetivo não é "acertar a moeda que vai
   subir", e sim ter uma **vantagem estatística** (expectância positiva
   depois das taxas) comprovada em teste, com **perda máxima controlada**.
2. **Funil em camadas**: universo → regime de mercado → score → gatilho de
   entrada → veto da IA → gestão de risco → execução. Cada camada só pode
   **reduzir** o risco, nunca aumentar.
3. **Código decide, IA opina.** O Gemini é o analista qualitativo (notícias,
   eventos, contexto) e tem **apenas poder de veto/redução**. Preço de
   entrada, stop, tamanho da posição e saída são **determinísticos** e
   testáveis.
4. **Mercado SPOT, só compra (long), sem alavancagem** no MVP. Sem risco de
   liquidação; o pior caso de cada operação é o stop.
5. **Mesmo código no backtest, no paper e no real.** Só muda o "broker"
   (simulado × Bybit Demo × Bybit real).

## 1. Universo de moedas (roda a cada 1 hora)

Fonte: `GET /v5/market/tickers?category=spot` (1 chamada traz todos os pares)
+ `GET /v5/market/instruments-info?category=spot` (regras de precisão).

| Filtro | Regra inicial |
|---|---|
| Par | Cotação em **USDT**, `status = Trading` |
| Liquidez | `turnover24h` ≥ **5.000.000 USDT** |
| Exclusões | Stablecoins (USDC, FDUSD, DAI, TUSD, USDE, PYUSD, EURC…), tokens alavancados (`*2L`, `*3L`, `*2S`, `*3S`, `*5L`, `*5S`), wrapped/pegged (WBTC, STETH, WETH…), lista negra manual |
| Histórico | ≥ **120 candles diários** disponíveis |
| Spread | `(ask1 − bid1) / preço médio` ≤ **0,15 %** |
| Profundidade | Soma das ordens de compra até −2 % do preço ≥ **50.000 USDT** (`/v5/market/orderbook`, só para os finalistas) |
| Já esticada | Excluir se variação 24h > **+25 %** (pump) ou < **−15 %** (queda forte) |

## 2. Regime de mercado (filtro do BTC)

Calculado a cada execução do scanner:

| Regime | Condição | Efeito |
|---|---|---|
| `risk_on` | BTC fecha acima da EMA200 **diária** **e** EMA50 4H > EMA200 4H | Opera normal |
| `neutro` | Só uma das duas condições | Risco por trade ÷ 2, máx. 2 posições, score mínimo +5 |
| `risk_off` | Nenhuma das condições | **Não abre** novas posições (só gerencia as abertas) |

Extras:
- **Amplitude (breadth)**: % do universo acima da EMA50 4H. Se < **30 %** → tratar como `risk_off`.
- **Circuit breaker**: BTC caiu > **5 %** nas últimas 24h → sem novas entradas por **12 h**.

## 3. Score de oportunidade (0 a 100)

Timeframes: **1D** (contexto), **4H** (tendência/setup), **1H** (gatilho).

### A. Tendência — até 25 pts
| Condição | Pts |
|---|---|
| Preço > EMA50 (4H) | 7 |
| EMA50 (4H) > EMA200 (4H) | 7 |
| Preço > EMA50 (1D) | 5 |
| ADX(14) 4H > 20 **e** DI+ > DI− | 6 |

### B. Força relativa contra o BTC — até 20 pts
| Condição | Pts |
|---|---|
| Retorno 7d da moeda − retorno 7d do BTC > 0 | 6 |
| Retorno 30d da moeda − retorno 30d do BTC > 0 | 6 |
| Razão MOEDA/BTC (close ÷ close do BTC, diário) acima da sua EMA20 | 8 |

### C. Volume e acumulação — até 20 pts
| Condição | Pts |
|---|---|
| Volume 24h ÷ média de 20 dias entre **1,3×** e **4×** | 8 |
| OBV (4H) acima da sua EMA20 e inclinando para cima | 6 |
| CMF(20) 4H > 0,05 | 6 |

### D. Compressão de volatilidade ("antes de valorizar") — até 15 pts
| Condição | Pts |
|---|---|
| Largura das Bandas de Bollinger(20, 2) 4H no **percentil ≤ 25 %** dos últimos 120 candles | 8 |
| Preço no **terço superior** do range dos últimos 20 candles 4H (perto do rompimento) | 4 |
| ATR(14) 4H abaixo da média de 50 períodos do próprio ATR (contração) | 3 |

### E. Derivativos — até 10 pts (só se existir perpétuo linear `{SYMBOL}` na Bybit)
Fontes: `/v5/market/open-interest`, `/v5/market/tickers?category=linear`
(funding atual), `/v5/market/account-ratio`.

| Condição | Pts |
|---|---|
| Open Interest 24h subindo > +5 % com preço subindo < +8 % (posicionamento antes do movimento) | 4 |
| Funding atual entre −0,01 % e +0,03 % (não superaquecido) | 3 |
| Razão long/short de contas ≤ 1,5 (sem multidão comprada) | 3 |
| *Sem perpétuo listado* → pontuação neutra fixa | 5 |

### F. Momentum — até 10 pts
| Condição | Pts |
|---|---|
| RSI(14) 4H entre 50 e 68 | 5 |
| Histograma MACD(12, 26, 9) 4H > 0 e crescendo | 5 |

### Penalidades (subtraem do total)
| Condição | Pts |
|---|---|
| RSI(14) 4H > 75 | −10 |
| Preço > 12 % acima da EMA20 4H (esticado) | −10 |
| Volume 24h > 6× a média (pump suspeito) | −8 |
| Funding > +0,05 % | −5 |
| Pavio superior > 60 % do range em alguma das últimas 3 velas 1D (rejeição) | −5 |

### Classificação
- **≥ 70** → Watchlist **A** (elegível para gatilho de entrada)
- **60–69** → Watchlist **B** (só monitorar / mostrar no painel)
- **< 60** → descartada nesta rodada

## 4. Gatilhos de entrada (roda a cada 15 min, só para a Watchlist A)

O gatilho é avaliado **somente em velas fechadas** (nunca na vela em formação).

### Setup 1 — `pullback_tendencia`
1. Componente A (tendência) ≥ 18.
2. Preço recua até a zona entre **EMA20 e EMA50 do 1H** (ou toca a EMA20 4H).
3. RSI(14) 1H tocou entre 35 e 45 e voltou acima de 45.
4. Vela 1H de confirmação **fechada**: fecha acima da EMA20 1H, corpo ≥ 50 % do range e fecha acima da máxima da vela anterior (ou engolfo de alta).
5. **Entrada**: ordem limite no preço de fechamento da vela de confirmação (+0,1 % de tolerância), válida por 2 velas 1H.
6. **Stop**: mínima do pullback − 0,5 × ATR(14) 1H.

### Setup 2 — `rompimento_compressao`
1. Componente D (compressão) ≥ 10.
2. Vela 1H **fecha** acima da máxima dos últimos 20 candles 4H, com volume ≥ **1,8×** a média de 20 velas 1H.
3. **Entrada**: ordem limite no **reteste** do nível rompido (nível + 0,2 %), válida por 6 velas 1H; se não preencher, cancela (não persegue preço).
4. **Stop**: o mais próximo entre o meio do range e (nível rompido − 1,5 × ATR 1H), respeitando distância mínima de 1 × ATR.

### Setup 3 — `ote_fibo` (porta para Python a lógica já existente neste repositório)
Reaproveita a lógica de `MQL5/Experts/ICT_FiboEntry_EA.mq5`, só no lado comprado:
1. Perna de impulso de alta validada por fractais (5 velas de cada lado) com tamanho ≥ 3 × ATR (1H).
2. Retração para a zona **OTE 61,8 %–79 %** do Fibonacci da perna.
3. Confluência com **Order Block** (última vela de baixa antes da vela de deslocamento ≥ 1,5 × ATR).
4. Vela de rejeição fechada dentro da zona.
5. **Stop**: abaixo do OB / origem da perna + buffer. **Alvos**: 50 % da perna, topo da perna, extensão 1,618.

### Filtros comuns a todos os setups
- R:R até o TP2 ≥ **2,0**.
- Distância do stop entre **1,5 %** e **8 %** do preço de entrada.
- Spread ok no momento da ordem; regime ≠ `risk_off`.
- Sem posição aberta na mesma moeda; sem reentrada na mesma moeda por **24 h** após um stop.
- Veto do Gemini não acionado (seção 5).

## 5. Analista Gemini (veto qualitativo)

- **Quando**: (a) para cada sinal antes de enviar a ordem; (b) 1× por dia para toda a Watchlist A (para o painel).
- **Entrada**: JSON com métricas do score, indicadores, preço, variações, OI/funding + instrução de pesquisar notícias recentes com **Google Search grounding**.
- **O que checar**: hack/exploit, deslistagem ou tag de monitoramento (ST) na Bybit, **desbloqueio de tokens (unlock)** relevante nos próximos 14 dias, processos/regulação, falhas de rede, sinais de pump coordenado, eventos positivos (listagens, upgrades, parcerias).
- **Saída obrigatória (JSON validado por schema)**:
  ```json
  {
    "veredito": "aprovado | cautela | vetado",
    "risco": "baixo | medio | alto",
    "eventos": [{"tipo": "unlock", "data": "2026-10-20", "descricao": "...", "fonte": "url"}],
    "resumo": "até 400 caracteres em português",
    "confianca": 0.0
  }
  ```
- **Efeitos**: `vetado` → não entra. `cautela` → risco do trade ÷ 2. `aprovado` → segue normal.
- **Falhas** (timeout, JSON inválido, erro de API) → tratar como `cautela` (configurável para "fail-closed" = não entrar).
- O Gemini **nunca** define preço, quantidade, stop ou alvo e **nunca** aumenta o risco.
- Cache de 6 h por moeda; toda resposta é gravada (auditoria) e enviada ao painel.

## 6. Gestão de risco (o motor de risco tem a palavra final)

| Regra | Valor inicial |
|---|---|
| Risco por trade | **1 %** do patrimônio (0,5 % nas primeiras semanas em conta real) |
| Tamanho da posição | `(patrimônio × risco%) ÷ (entrada − stop)`, arredondado **para baixo** pelo `basePrecision`; respeitar `minOrderQty` e `minOrderAmt` (se não couber, **não entra**) |
| Posições simultâneas | máx. **4** |
| Exposição por moeda | máx. **25 %** do patrimônio |
| Exposição total | máx. **80 %** do patrimônio (spot, sem alavancagem) |
| Mesmo setor (L1, L2, DeFi, IA, memes…) | máx. **2** posições |
| Perda diária | **3 %** → sem novas entradas até 00:00 UTC |
| 3 stops seguidos | pausa de **24 h** |
| Drawdown semanal | **6 %** → pausa até revisão manual |
| Drawdown desde o pico | **15 %** → **kill switch** (fecha nada sozinho, apenas bloqueia entradas e alerta crítico) |
| Preço médio / alavancagem | **Proibidos** no MVP |

## 7. Saídas

1. **Stop inicial no servidor da Bybit** (ordem condicional), enviado logo após a execução da entrada — a posição fica protegida mesmo se o robô cair.
2. **TP1 em +1,5 R**: vende **50 %**; move o stop para **entrada + taxas** (breakeven).
3. **Restante**: trailing stop = máx(stop atual, mínima das 3 últimas velas 1H fechadas − 0,5 × ATR 1H). Alternativa configurável: alvo fixo TP2 em +3 R.
4. **Stop de tempo**: se em **48 h** o trade não chegou a +0,5 R → encerra.
5. **Invalidação**: fechamento 4H abaixo da EMA50 4H → encerra.
6. **Regime virou `risk_off`**: stops das posições com lucro vão para breakeven.

## 8. Custos e execução

- Considerar **0,1 % por lado** (taxa spot padrão; confira a sua tabela de taxas/VIP) + slippage de 0,05 % no backtest.
- Preferir ordens **limite** (PostOnly quando fizer sentido) para pagar taxa maker.
- Toda ordem tem `orderLinkId` único e determinístico (idempotência): `{SYMBOL}-{setup}-{AAAAMMDDHHmm}`.
- Antes de qualquer ordem: validar `tickSize`, `basePrecision`, `minOrderQty`, `minOrderAmt` do par.

## 9. O que medir (painel e relatórios)

Taxa de acerto, payoff, **expectância em R**, profit factor, drawdown máximo,
tempo médio em posição, resultado por setup, por regime, por faixa de score e
por veredito do Gemini (para saber se o veto realmente ajuda).
