# ICT Fibo Entry — Indicador de Entrada para MT5

Indicador para MetaTrader 5 (`.mq5`) que automatiza o fluxo mostrado nas
suas imagens de referência:

1. **Estrutura**: detecta a última perna de impulso (topo → fundo ou
   fundo → topo) através de fractais de preço.
2. **Fibonacci a favor da tendência**: desenha o retracement sempre no
   sentido do impulso (0% = extremo mais recente, 100% = origem do
   movimento) e destaca a **zona OTE** (Optimal Trade Entry, 61,8%–79%
   por padrão) — o nível SNR/ICT do primeiro print.
3. **Order Block (RBS/OB)**: localiza, dentro da perna, a última vela
   oposta antes da vela de deslocamento, e marca essa zona (retângulo +
   linha "RBS/OB") — como no segundo print.
4. **Entrada**: quando o preço entra na zona de confluência (OTE + OB) e
   fecha em rejeição a favor da tendência, o indicador plota:
   - **Seta de ENTRADA** no ponto exato;
   - **STOP** (ponto definido), com buffer configurável além da
     estrutura/OB;
   - **3 ALVOS** (TP1 = 50% da perna, TP2 = retorno ao extremo/estrutura,
     TP3 = extensão 1.618 além da estrutura) — como no resultado final
     (print "Sonuç").
5. Opcionalmente dispara `Alert()` e/ou notificação push quando um sinal
   é confirmado.

## Instalação no MetaTrader 5

1. Copie `MQL5/Indicators/ICT_FiboEntry.mq5` para a pasta
   `MQL5/Indicators` do seu terminal MT5
   (no MT5: **Arquivo → Abrir pasta de dados → MQL5 → Indicators**).
2. Abra o **MetaEditor** (F4), localize o arquivo e compile (F7).
3. No MT5, arraste o indicador **ICT Fibo Entry** para o gráfico
   desejado.
4. Ajuste os parâmetros de entrada conforme a seção abaixo.

## Parâmetros principais

| Grupo | Parâmetro | Descrição |
|---|---|---|
| Estrutura | `InpSwingBars` | Nº de velas de cada lado para validar um topo/fundo (fractal). Aumente para pernas mais "macro", diminua para mais sinais/mais ruído. |
| Estrutura | `InpMinLegATR` | Tamanho mínimo da perna, em múltiplos do ATR, para ser considerada válida (filtra ruído). |
| Fibonacci | `InpOTEStart` / `InpOTEEnd` | Limites da zona OTE (padrão 61,8%–79%). |
| Fibonacci | `InpTP1Level` / `InpTP2Level` / `InpTP3Extension` | Níveis fib usados para os 3 alvos. |
| Order Block | `InpUseOB` | Se `true`, exige confluência entre a zona OTE e um Order Block para liberar a entrada (mais seletivo). Se `false`, entra só pela zona OTE. |
| Order Block | `InpDisplacementATR` | Múltiplo do ATR que define uma vela de "deslocamento" (rompimento forte). |
| Gestão | `InpSLBufferPoints` | Buffer (em pontos) do stop além da estrutura/OB. |
| Alertas | `InpAlertOnSignal` / `InpPushNotification` | Ativam alerta no terminal e/ou notificação push ao celular. |

## Observações importantes

- O indicador só recalcula a lógica de sinal no **fechamento de cada
  vela** (não em cada tick), e sempre usa a última vela **fechada** como
  referência — a vela em formação nunca é usada para gerar sinal.
- Cada nova perna de impulso gera um novo conjunto de objetos gráficos
  (prefixo `ICTFE_<timestamp>_`); ao surgir uma perna nova ou ao romper a
  estrutura (invalidação), os objetos da perna anterior são apagados
  automaticamente.
- As caixas/linhas se estendem por `InpBoxExtendBars` velas para a
  direita a partir do momento em que são desenhadas.
- Esta é uma ferramenta de **apoio visual/discricionário**, não um
  robô de execução automática e não constitui recomendação de
  investimento. Faça backtest e forward test em conta demo antes de
  usar em conta real, e ajuste os parâmetros ao ativo/timeframe
  operado.

---

# ICT Fibo Entry EA — versão robô (Expert Advisor)

`MQL5/Experts/ICT_FiboEntry_EA.mq5` usa a **mesma lógica de estrutura,
Fibonacci/OTE e Order Block** do indicador acima, mas em vez de apenas
desenhar, **envia ordens reais** quando o sinal é confirmado.

## O que o EA faz ao confirmar um sinal

1. Calcula o **lote total** para arriscar `InpRiskPercent`% do saldo da
   conta, com base na distância entre a entrada (preço de mercado no
   momento do sinal) e o Stop Loss.
2. Divide esse lote em **até 3 posições simultâneas** (mesmo SL, um TP
   diferente cada — TP1/TP2/TP3), cada uma enviada e gerenciada pelo
   próprio servidor da corretora (funciona mesmo se o terminal cair
   depois de aberta).
3. Se o lote mínimo do símbolo não permitir dividir em 3, o EA reduz
   automaticamente para 2 pernas (TP1/TP2) e, em último caso, para 1
   perna só (usando o alvo intermediário TP2). Se nem 1 lote mínimo
   couber dentro do risco definido, **a entrada é ignorada** (log no
   terminal) — o EA nunca infla o lote além do risco configurado só
   para conseguir operar.
4. Desenha no gráfico a seta de ENTRADA, o STOP e os alvos realmente
   enviados — esses objetos só somem quando as posições dessa entrada
   forem fechadas (por SL, TP ou manualmente).
5. Com `InpOneSetupAtATime = true` (padrão), enquanto houver posição
   aberta deste EA no símbolo, a busca por uma nova perna fica
   **congelada**: o Fibo/OTE/OB continua exatamente como estava quando
   a entrada foi disparada, em vez de "pular" para uma perna nova a
   cada vela (o que faria a zona exibida perder relação com a operação
   já aberta). A busca só recomeça depois que a posição for fechada.

## Instalação

1. Copie `MQL5/Experts/ICT_FiboEntry_EA.mq5` para `MQL5/Experts` do seu
   terminal MT5.
2. Compile no MetaEditor (F7).
3. Arraste **ICT_FiboEntry_EA** para o gráfico do ativo/timeframe
   desejado.
4. Habilite o **Auto Trading** no terminal (botão no topo do MT5) e
   confirme "Permitir negociação automatizada" nas propriedades do EA.

## Parâmetros específicos do EA

| Grupo | Parâmetro | Descrição |
|---|---|---|
| Risco/Execução | `InpEnableTrading` | Se `false`, o EA só desenha e envia `Alert()`/`Print()`, sem enviar ordens — útil para observar os sinais antes de ligar a execução real. |
| Risco/Execução | `InpRiskPercent` | % do **saldo** arriscado por sinal, dividido entre as pernas efetivamente abertas. |
| Risco/Execução | `InpMagicNumber` | Identifica as ordens deste EA (não misturar com outros EAs/robôs no mesmo símbolo). |
| Risco/Execução | `InpSlippagePoints` | Desvio máximo de preço aceito no preenchimento da ordem. |
| Risco/Execução | `InpMaxSpreadPoints` | Se maior que 0, ignora sinais quando o spread do símbolo estiver acima desse valor (proteção contra spread alto em notícias/abertura de mercado). |
| Risco/Execução | `InpOneSetupAtATime` | Se `true` (recomendado), não abre um novo conjunto de ordens enquanto houver posições abertas deste EA no símbolo. |

Os demais parâmetros (estrutura, Fibonacci/OTE, Order Block, visual,
alertas) têm o mesmo significado do indicador `ICT_FiboEntry.mq5`.

## Contas NETTING (posição única por símbolo)

Algumas corretoras/símbolos operam em modo **netting** ou **exchange**
(só existe 1 posição por símbolo — várias ordens no mesmo símbolo se
fundem automaticamente numa única posição, e a última chamada
sobrescreve o SL/TP das anteriores). Nesse modo, abrir "3 pernas"
separadas quebraria a lógica de TP1/TP2/TP3 (o TP final ficaria sendo
só o da última chamada). Por isso, o EA detecta o modo da conta no
`OnInit()` (`ACCOUNT_MARGIN_MODE`) e, se não for **hedging**, usa
automaticamente **1 única entrada por sinal**, com o alvo intermediário
TP2 — a mensagem "conta em modo NETTING/EXCHANGE detectada" aparece no
log (aba **Experts**) quando isso acontece.

Além disso, o EA verifica a cada tick se o preço já ultrapassou o Stop
de alguma posição própria que continua aberta (o que não deveria
acontecer, mas serve de rede de segurança contra falha de execução da
corretora) e fecha a posição manualmente nesse caso — evitando que o
robô fique travado indefinidamente numa operação que nunca fecha
sozinha.

## Observações importantes (leia antes de usar em conta real)

- **Sempre valide primeiro no Strategy Tester** (modo "Visual" e depois
  otimização/backtest normal) e depois em **conta demo**, no
  ativo/timeframe que pretende operar, antes de qualquer conta real.
- Se a entrada não for executada no momento do sinal (spread acima do
  limite, já existe posição aberta, ou lote calculado abaixo do mínimo
  do símbolo), o EA **não tenta novamente** na mesma perna — ele
  aguarda a formação de uma nova perna de estrutura. Isso evita sinais
  duplicados, mas significa que um filtro momentâneo pode custar uma
  entrada.
- O EA **não fecha posições automaticamente** se a estrutura for
  invalidada depois da entrada (rompimento além da origem da perna) —
  a proteção nesse cenário é o próprio Stop Loss já enviado à
  corretora. Fechamento antecipado por invalidação de estrutura não
  está implementado nesta versão.
- `InpRiskPercent` é aplicado sobre o **saldo atual** a cada sinal (não
  sobre o saldo inicial), então o tamanho da posição se ajusta conforme
  a conta cresce ou diminui.
- Esta é uma ferramenta educacional de automação de uma estratégia
  discricionária; não constitui recomendação de investimento. Ajuste
  todos os parâmetros de risco à sua realidade e opere sempre com
  capital que pode perder.

---

# DowStructure EA — estrutura de mercado (Teoria de Dow)

`MQL5/Experts/DowStructure_EA.mq5` é um robô de **seguimento de tendência
pela estrutura de topos e fundos**, no mesmo estilo dos EAs anteriores
(risco por % do saldo, SL no servidor, objetos no gráfico, `Alert`).

## Lógica

| Etapa | Venda | Compra (espelho) |
|---|---|---|
| **Filtro** | último fechamento **abaixo** da média móvel (padrão 178) | último fechamento **acima** da média |
| **Gatilho** | um **novo topo** é confirmado (fractal) | um **novo fundo** é confirmado (fractal) |
| **Estrutura** | o novo topo é **menor** que o topo anterior (topos descendentes) | o novo fundo é **maior** que o fundo anterior (fundos ascendentes) |
| **Entrada** | venda **a mercado** na hora em que o topo é confirmado | compra **a mercado** na hora em que o fundo é confirmado |
| **Saída** | o mercado **rompe o último topo** (quebra da estrutura baixista) → fecha **todas** as vendas | o mercado **rompe o último fundo** → fecha **todas** as compras |

Pontos importantes da implementação:

- **Topo/fundo = fractal de `InpSwingBars` velas de cada lado.** Ele só é
  confirmado depois que essas velas fecham, então nunca "repinta" — mas a
  entrada sai `InpSwingBars` velas depois do topo/fundo (é o custo de
  confirmar a estrutura).
- **Acumula posições:** a cada novo topo mais baixo (venda) / novo fundo mais
  alto (compra) abre mais uma entrada, até `InpMaxEntries` por sentido.
- **O nível de saída acompanha a estrutura:** com vendas abertas, cada novo
  topo mais baixo vira o novo nível de quebra (o stop desce junto, travando
  lucro das entradas anteriores). Ele **nunca se afasta** do preço. O mesmo
  vale, espelhado, para as compras.
- **"Rompe" = fechamento da vela além do nível** (`InpBreakByClose = true`,
  critério de Dow por fechamento). Com `false`, basta o preço tocar o nível
  (checado a cada tick). `InpBOSBufferPoints` adiciona uma folga ao nível.
- **Nunca opera contra posição aberta:** se o preço cruzar a média com vendas
  ainda abertas, as compras só começam depois da quebra de estrutura.
- **SL de emergência (servidor):** `nível da estrutura + InpHardSLATRMult × ATR`
  (padrão 3×ATR), movido junto com o nível. Serve para gaps/picos e se o
  terminal cair; a saída "normal" continua sendo a quebra de estrutura. Se
  você diminuir muito esse múltiplo, ele passa a disparar antes do
  fechamento da vela e a saída deixa de ser pela estrutura.
- **Lote:** `InpRiskPercent`% do saldo **até o SL de emergência** (ou
  `InpFixedLot`). Se nem o lote mínimo couber no risco, a entrada é ignorada.
- **Contas NETTING/EXCHANGE:** as entradas se fundem numa posição só (o
  volume acumula) e o EA aplica SL/fechamento sobre ela inteira — funciona
  igual, só não há posições separadas.
- **Reinício:** ao anexar o EA (ou reiniciar o terminal) ele **não** entra em
  topos/fundos antigos; se já houver posições dele, o nível de saída é
  reconstruído a partir do último topo/fundo confirmado.

## Instalação

1. Copie `MQL5/Experts/DowStructure_EA.mq5` para `MQL5/Experts` do terminal MT5.
2. Compile no MetaEditor (F7).
3. Arraste **DowStructure_EA** para o gráfico (ex.: XAUUSD M1) e habilite o
   Auto Trading.
4. No painel do gráfico (canto superior esquerdo) aparecem a tendência, os
   últimos topos/fundos e o nível de saída em vigor.

## Parâmetros

| Grupo | Parâmetro | Descrição |
|---|---|---|
| Filtro | `InpMAPeriod` / `InpMAMethod` / `InpMAPrice` | Média móvel do filtro (padrão SMA 178 sobre o fechamento). |
| Filtro | `InpMATimeframe` | Timeframe da média (`CURRENT` = o do gráfico; dá para usar, por exemplo, a média de 178 do M5 num gráfico M1). |
| Estrutura | `InpSwingBars` | Velas de cada lado para confirmar topo/fundo. Menor = entra mais cedo, mais ruído; maior = estrutura mais "macro". |
| Estrutura | `InpRequireStructure` | `true` = só vende em topo menor que o anterior / só compra em fundo maior que o anterior. `false` = qualquer topo/fundo a favor da média. |
| Entradas | `InpAllowSell` / `InpAllowBuy` | Liga/desliga cada sentido. |
| Entradas | `InpMaxEntries` | Máximo de entradas acumuladas por sentido (0 = sem limite). |
| Saída | `InpBreakByClose` | `true` = vela fecha além do nível; `false` = preço toca o nível. |
| Saída | `InpBOSBufferPoints` | Folga (pontos) além do topo/fundo para considerar a estrutura quebrada. |
| Saída | `InpUseHardSL` / `InpHardSLATRMult` / `InpATRPeriod` | SL de emergência no servidor (ver acima). |
| Risco | `InpEnableTrading` | `false` = só desenha e envia alerta (modo "ver os sinais" sem operar). |
| Risco | `InpRiskPercent` / `InpFixedLot` | Risco por entrada em % do saldo, ou lote fixo. |
| Risco | `InpMagicNumber`, `InpSlippagePoints`, `InpMaxSpreadPoints` | Como nos outros EAs. |

## Observações

- **Validação feita:** este ambiente não tem o MetaEditor, então o `.mq5` não
  foi compilado aqui. A lógica foi exercitada compilando o próprio arquivo
  contra um *mock* da API do MT5 em barras sintéticas e comparada com uma
  implementação independente (mesmas entradas, saídas, lotes e SL em 30
  cenários), mas isso **não substitui** compilar no MetaEditor e rodar o
  **Strategy Tester** (modo visual) e uma conta **demo** no seu ativo/timeframe.
- Em tendência forte o robô acumula várias posições no mesmo sentido; o risco
  de cada entrada é calculado individualmente (até o SL de emergência), e o
  nível de saída ao se aproximar do preço protege as anteriores. Em mercado
  lateral/sem tendência (muitas quebras seguidas) o resultado tende a ser de
  várias pequenas perdas — é a característica natural de um seguidor de
  estrutura.
- Esta é uma ferramenta educacional de automação de uma estratégia
  discricionária; não constitui recomendação de investimento. Opere sempre
  com capital que pode perder.

---

# MA200 Candle Trail EA — continuação de tendência, sem alvo

`MQL5/Experts/MA200_CandleTrail_EA.mq5` é um robô de **continuação de
tendência**: a média lenta (EMA 200) dá o sentimento, a média rápida (EMA 20)
confirma o candle, e **não há alvo** — o stop acompanha a mínima/máxima do
candle anterior para aproveitar o máximo do movimento.

## Lógica

| Etapa | Compra | Venda (espelho) |
|---|---|---|
| **Sentimento** | candle fecha **acima** da EMA 200 | candle fecha **abaixo** da EMA 200 |
| **Gatilho** | candle de **alta** que fecha **acima das duas** médias (EMA 20 e EMA 200) | candle de **baixa** que fecha **abaixo das duas** |
| **Entrada** | compra **a mercado** na abertura do candle seguinte | venda **a mercado** na abertura do candle seguinte |
| **Alvo** | nenhum | nenhum |
| **Stop inicial** | **mínima** do candle anterior (o candle do sinal) | **máxima** do candle anterior (+ spread, ver abaixo) |
| **Stop depois** | a cada candle novo vai para a mínima do candle que acabou de fechar; **só sobe** | a cada candle novo vai para a máxima do candle que acabou de fechar; **só desce** |

Pontos importantes:

- **Médias exponenciais por padrão** (`InpMAMethod = MODE_EMA`), 200 e 20,
  sobre o fechamento do timeframe do gráfico. Tipo e períodos são parâmetros.
- **O stop nunca se afasta do preço.** Com `InpTrailCandles = 1` isso equivale
  a "mínima do candle anterior": uma mínima menor que o stop vigente já teria
  disparado o stop. Com `InpTrailCandles = N` o stop usa a menor mínima (maior
  máxima) dos últimos N candles fechados, o que dá mais folga.
- **O stop é enviado ao servidor** (ordem real, protege mesmo sem o terminal)
  sempre que respeita a distância mínima da corretora (`stops level`) e o
  *freeze level*. Se o novo nível ficar colado demais no preço, o EA espera; se
  o preço o atravessar antes disso, o EA **fecha a mercado**.
- **Venda e spread:** os candles são de Bid, mas o stop da venda dispara no
  Ask. Com `InpSellStopAddSpread = true` (padrão) o EA soma o spread atual ao
  stop da venda, para que ele toque a máxima no gráfico, espelhando o da
  compra. Desligue para usar a máxima exata.
- **Uma posição por vez** por padrão (`InpMaxEntries = 1`): enquanto houver
  posição aberta num sentido, os novos sinais naquele sentido são ignorados;
  quando o stop pega, o próximo candle que cumprir o gatilho reentra. Com
  `InpMaxEntries > 1` o EA empilha uma entrada por sinal, todas com o mesmo
  stop compartilhado.
- **Nunca opera contra posição aberta:** se o preço cruzar a média com uma
  posição ainda aberta, o sentido contrário só começa depois que ela sair.
- **Lote:** `InpRiskPercent`% do saldo até o stop inicial (ou `InpFixedLot`).
  Se nem o lote mínimo couber no risco, a entrada é ignorada.
- **Contas NETTING/EXCHANGE:** as entradas se fundem numa posição só; o EA
  nunca deixa o stop da posição ficar mais frouxo ao acrescentar volume.
- **Reinício/troca de timeframe:** o EA recupera as posições abertas e **não**
  entra no meio de um candle só por ter sido anexado; a próxima entrada é no
  próximo candle.

## Instalação

1. Baixe `MQL5/Experts/MA200_CandleTrail_EA.mq5` (use o arquivo, não copie e
   cole o texto) e salve em `MQL5/Experts` do terminal MT5.
2. Compile no MetaEditor (F7) e arraste **MA200_CandleTrail_EA** para o gráfico.
3. Habilite o Auto Trading. O painel no canto do gráfico mostra o sentimento,
   os valores das médias, as posições e o stop em vigor.

## Parâmetros

| Grupo | Parâmetro | Descrição |
|---|---|---|
| Médias | `InpSlowMAPeriod` / `InpFastMAPeriod` | Média lenta (sentimento, padrão 200) e rápida (padrão 20). |
| Médias | `InpMAMethod` / `InpMAPrice` | Tipo (padrão exponencial) e preço aplicado. |
| Entradas | `InpAllowBuy` / `InpAllowSell` | Liga/desliga cada sentido. |
| Entradas | `InpMaxEntries` | Entradas abertas ao mesmo tempo por sentido (1 = uma por vez; 0 = sem limite). |
| Stop | `InpTrailCandles` | Stop na mínima/máxima dos últimos N candles fechados (1 = candle anterior). |
| Stop | `InpSLBufferPoints` | Folga em pontos além dessa mínima/máxima. |
| Stop | `InpSellStopAddSpread` | Soma o spread ao stop da venda (padrão ligado). |
| Risco | `InpRiskPercent` / `InpFixedLot` | Risco por entrada em % do saldo, ou lote fixo. |
| Risco | `InpMaxSpreadPoints` | Se > 0, ignora entradas com spread acima disso. |
| Risco | `InpEnableTrading` | `false` = só desenha/alerta (alerta em todo candle que cumpre o gatilho, mesmo os que não abririam por já haver posição). |
| Risco | `InpMagicNumber`, `InpSlippagePoints` | Como nos outros EAs (desvio padrão menor: 10 pontos, porque o stop é curto). |
| Visual | `InpDrawObjects`, `InpShowPanel`, `InpAlertOnTrade`, `InpPushNotification` | Setas/linha do stop, painel e alertas (alerta desligado por padrão: gera muitos avisos em M1). |

## Observações (leia antes de testar)

- **Em M1 de ouro o stop é curto e o custo do spread pesa muito.** Em testes
  com dados *sintéticos* (que **não** provam lucratividade, só mostram a
  mecânica) o stop mediano ficou em torno de 1 ATR (~4 spreads) e o custo de
  spread por operação em torno de 0,3R, com ~22% das velas virando operação.
  Isso cai para ~0,15R em M5 e ~0,08R em M15. Para reduzir custo: testar M5/M15,
  usar `InpMaxSpreadPoints`, `InpSLBufferPoints` maior que o spread e/ou
  `InpTrailCandles` 2–3.
- **Stop curto + 1% de risco = lote grande** (em M1, mediana de ~1,3 lote em
  conta de US$ 10 mil). Comece com risco menor (0,25–0,5%) ou lote fixo e
  confira se a margem comporta.
- **Reinício com posição aberta:** o EA recupera as posições e usa como nível
  o stop que elas já têm no servidor (não rebaseia o stop de repente, nem ao
  trocar de timeframe); o ajuste normal volta no próximo candle fechado. Em
  conta hedging, depois de um reinício `InpMaxEntries` limita as posições
  **abertas** (entradas já encerradas antes do reinício não contam). Em conta
  NETTING o lado é tratado como cheio até zerar.
- **Modo do testador:** use "Todos os ticks" ou "Ticks reais". Em "Somente
  preços de abertura" o EA só decide uma vez por candle, na abertura.
- **Validação feita:** compilado contra um *mock* da API do MT5 e comparado
  com um modelo de referência independente e com testes de invariantes em
  milhares de cenários sintéticos; **não substitui** compilar no MetaEditor e
  rodar o Strategy Tester (modo visual) e uma conta demo no seu ativo.
- Esta é uma ferramenta educacional de automação de uma estratégia
  discricionária; não constitui recomendação de investimento. Opere sempre
  com capital que pode perder.
