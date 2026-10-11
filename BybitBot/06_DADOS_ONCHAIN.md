# 06 — Camada on-chain (Coinversa + Liquid)

> **Resumo**: dados de posicionamento on-chain da **Hyperliquid** (quem está
> comprado ou vendido, separado por lucratividade, alavancagem, liquidações)
> entram no robô como uma camada **opcional**, que **só pode reduzir risco** e
> começa em **modo sombra (shadow)**: o robô calcula e grava tudo, mas nada
> muda nas decisões até a regra provar valor no teste.
>
> **Atenção**: Hyperliquid **não é** a Bybit. São perpétuos de outra
> corretora, usados como termômetro de sentimento. O efeito disso no spot da
> Bybit é uma hipótese a validar, não um fato.

## 1. Fontes e papel de cada uma

| Fonte | O que traz | Papel no projeto | Como o robô acessa |
|---|---|---|---|
| **Coinversa Pulse** | Viés por coorte de lucratividade (Apex, Sharps, Grinders, Scrapers, The Crowd, Bleeders, Trapped, Blown Out), histórico horário de coortes (~90 dias), mapa de liquidação, risco/alavancagem por moeda e do mercado, liquidações reais, OI, funding | **Fonte principal** da camada on-chain | API REST com chave (`X-API-Key`, formato `cvsa_...`) guardada no Secret Manager como `COINVERSA_API_KEY` |
| **Liquid** | Atividade de volume incomum (última hora vs média 24h), manchetes, divisão lucrativos vs multidão, indicadores técnicos | **Fonte secundária**: checagem cruzada e revisão humana/semanal | Só via conector MCP (sem API pública conhecida para o robô). **Usar somente para leitura** |
| **Quiver Quant** | Dados alternativos de **ações dos EUA** (congresso, 13F, insiders) | **Não usado**: não há dados de cripto | — |

> ⚠️ **Liquid também é uma corretora**. A conta conectada está em **modo real**
> (paper trading desligado). Nenhuma ordem deve ser enviada por ela; o
> robô deste projeto opera **só na Bybit**.

## 2. API da Coinversa (confirmar antes de codar)

| Item | Valor encontrado | Status |
|---|---|---|
| Base URL | `https://api.coinversa.ai/api/public/v1` | Visto no código do cliente oficial (v0.12.0); **confirmar em docs.coinversa.ai** |
| Autenticação | Header `X-API-Key: cvsa_...` (chaves em developers.coinversa.ai/keys) | Só visto no código-fonte; **confirmar** |
| Plano atual | **Pro**: 600 req/min, 20.000/dia (pode ser o trial de 14 dias) | Lido via `/plan` |
| Plano Free | 30 req/min, 1.000/dia | O orçamento do robô (800/dia) cabe no Free |

Rotas usadas (todas GET):

| Uso | Rota |
|---|---|
| Viés por coorte atual | `/live/cohort-bias/{COIN}` (netBias em **fração** −1..1) |
| Histórico horário de coortes | `/pulse/cohort-bias/history?coin=X&since=…` (netBias em **%**; janela máx. 30d por chamada) |
| Risco/crowding por moeda | `/live/risk/coins/{COIN}` |
| Risco do mercado inteiro | `/live/risk/overview` |
| Liquidações reais | `/live/risk/liquidations/summary?since=1h&coin=X` |
| Mapa de liquidação | `/live/liquidation-heatmap/{COIN}?range=10&buckets=30` |
| Funding/OI/volume de todos os perps | `/pulse/market-overview` |

**Pegadinhas**: netBias vem em % numa rota e em fração em outra (sempre
recalcular `(L−S)/(L+S)` a partir dos notionals); OI ora em moeda, ora em USD;
timestamps em ms ou ISO sem fuso; prefixo **k = 1000 unidades** (kPEPE →
PEPEUSDT, preços ÷ 1000); símbolos com `:`, `#` ou `@` não são cripto
(ações, HIP-4, spot interno) e devem ser excluídos; moeda sem perp na HL
devolve **lista vazia**, que deve contar como **ausente**, nunca como "viés 0".

> 🕒 **Urgente**: o histórico de coortes parece ser uma **janela móvel de ~90
> dias** (o snapshot mais antigo encontrado foi 2026-07-13). O que não for
> exportado agora pode sumir. O robô deve exportar o histórico disponível
> logo na Fase 2 e gravar snapshots próprios a partir daí.

## 3. Regras mantidas (após revisão crítica)

Todas começam em `mode: shadow` e só são ativadas **uma de cada vez**
(`rules_active`), com pelo menos 4 semanas entre ativações.

| Regra | Camada | O que faz | Efeito máximo |
|---|---|---|---|
| **S1** Divergência lucrativos × multidão | Score | `SM_pool = (L−S)/(L+S)` de Apex+Sharps somados (sem peso) e `CROWD` do The Crowd. Dispara se `SM_pool ≤ −0,25` **e** `CROWD ≥ +0,35` em 3 das últimas 4 horas fechadas (snapshot ≤ decisão − 1h) | **−3 pontos**, nunca bônus; em `active` só rebaixa (A→B) |
| **F2** Fragilidade da moeda | Filtro | Veta entrada se `nearLiquidationNotional / OI ≥ 15 %` **e** `avgLiquidationDistancePct ≤ 5 %` | Veto da entrada |
| **F3** Cascata de liquidação | Filtro | Se liquidações de longs na última 1h ≥ 1 % do OI da moeda **e** ≥ 20 eventos → sem nova entrada na moeda por 2h | Pausa de 2h na moeda |
| **R2** Fragilidade do mercado | Risco | Se `nearLiquidation / OI total` da HL ≥ 8 % → risco × 0,75 | Fator 0,75 |
| **R3** Divergência no BTC | Risco | S1 aplicado ao BTC → risco × 0,75 em todas as entradas (não muda o regime) | Fator 0,75 |
| **R4** Combinação | Risco | `fator_onchain = min(R2, R3)` ∈ {0,75; 1,0}. Se o produto de todos os fatores (regime × Gemini × on-chain) < 0,25 → não entra | — |

Gates de qualidade (se falhar, a regra fica **ausente = neutra**): OI da moeda
na HL ≥ US$ 20 mi; Apex+Sharps com ≥ 50 contas e ≥ US$ 20 mi; The Crowd com
≥ 300 contas e ≥ US$ 5 mi; preço da HL a ±2 % do preço da Bybit.

## 4. Regras derrubadas (só gravadas para estudo)

| Regra | Por que caiu |
|---|---|
| S2 variação 24h do smart money | Coortes são definidas por PnL e mudam com o preço: vira momentum disfarçado, ruído horário alto |
| S3 multidão contrarian | Repete o componente "derivativos" e a perna CROWD do S1 (contagem dupla) |
| S4 alavancagem/near-liq no score | Sem histórico; pune majors (BTC) por estrutura |
| F1 veto por cluster de liquidação entre preço e stop | Sem histórico do heatmap; o corte dos buckets se move com o preço; dispararia o tempo todo no BTC |
| ST1 stop abaixo do cluster | Muda R, TP1, stop de tempo e trailing — altera o sistema validado no backtest. Medido como contrafactual |
| G1 dados on-chain no prompt do Gemini | Contagem dupla e impede medir se o veto do Gemini ajuda; o Gemini fica com notícias/eventos |
| R1 alavancagem média do mercado | Repete o R2 |

## 5. Regras de engenharia (obrigatórias)

- **D1 Mapeamento e qualidade**: tabela explícita par Bybit → coin HL, validação de preço ±2 %, lista vazia = ausente, recalcular bias dos notionals, dado mais velho que `max_data_age_minutes` = ausente.
- **D2 Isolamento e fail-open**: chamadas on-chain **só** no scanner horário e no ciclo de gatilho — **nunca** no caminho de stop, trailing, reconciliação ou kill switch. Timeout 4s, circuito abre após 3 falhas (15 min), 401/403 desliga por 24h com alerta, 429 respeita `retryAfterSeconds`. Nenhuma exceção sai do `OnchainProvider`. **Sem a Coinversa o robô funciona exatamente como a estratégia base.**
- **D3 Gravação contínua**: desde o primeiro dia (em qualquer modo) gravar snapshots com `asOf`, versão do servidor e hash do config em GCS/BigQuery; exportar o histórico de coortes disponível na primeira execução.
- **D4 Paridade e anti-look-ahead**: o replay do backtest só usa snapshot com timestamp ≤ decisão − 1h. Teste de regressão: com `onchain.enabled=false` **e** com `mode=shadow`, o backtest gera **exatamente os mesmos trades** da estratégia base.
- **D5 Pré-registro**: limiares congelados antes do forward test; proibido ajustá-los depois de ver resultados; contrafactual "sem a regra" continua gravado após a ativação, com desativação automática se piorar a expectância.

## 6. Plano de validação

1. **Pré-requisitos**: confirmar rotas/header/tiers em docs.coinversa.ai; testes unitários do adaptador (unidades, k×1000, listas vazias, timestamps); regressão do item D4.
2. **Backtest (só o que tem histórico)**: S1 e R3 via estudo de evento nos ~90 dias de coortes — comparar retorno e excursão adversa (MAE) em 24h/72h no spot da Bybit com e sem sinal; bootstrap em blocos diários; mesmo sinal nas duas metades da amostra. F3 só checagem diária. F2, R2 e as derrubadas: sem backtest.
3. **Forward test em shadow (Fase 8)**: todas as regras calculadas e gravadas em todos os candidatos e trades; A/B contrafactual sobre os mesmos trades (remover vetados, rebaixar A→B, escalar R pelos fatores, simular stop alternativo com candles da Bybit).
4. **Ativação**: uma regra por vez, com critério escrito antes, ≥ 4 semanas entre ativações e desativação automática se a expectância piorar.

## 7. Uso da Liquid (fonte secundária)

- **Volume incomum** (última hora vs média 24h) e **lucrativos vs multidão**: checagem cruzada manual dos candidatos A e insumo da revisão semanal.
- **Manchetes**: complementam a pesquisa do analista Gemini nas revisões humanas.
- Possível rotina diária (opcional, a decidir): um relatório "radar on-chain" gerado pelo Claude com Coinversa + Liquid e publicado no Notion.
- **Nunca** enviar ordens pela Liquid neste projeto.

## 8. Retrato de exemplo (11/10/2026 ~11:19 UTC — dado descritivo, não recomendação)

Em 11 das 12 moedas analisadas (BTC, ETH, SOL, HYPE, XRP, DOGE, SUI, AVAX,
LINK, NEAR, ENA, ZEC), Sharps e The Crowd estavam comprados por notional
enquanto o Apex estava vendido em 10 das 12. A maior divergência era no ENA
(Apex −0,58 contra Sharps +0,54 e Crowd +0,56); o AVAX tinha o perfil
invertido (Apex comprado, Sharps vendidos). Alavancagem média da HL: 8,07x;
US$ 664 mi em posições perto de liquidação (≈ 4,2 % do OI — abaixo do limiar
de 8 % do R2). Pela regra S1 revisada, o BTC **não** disparava
(SM_pool −0,157; CROWD +0,308).
