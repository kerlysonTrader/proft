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
