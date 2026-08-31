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
