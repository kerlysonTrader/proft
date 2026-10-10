//+------------------------------------------------------------------+
//|                                        MA200_CandleTrail_EA.mq5  |
//|                                                                  |
//| Expert Advisor de continuacao de tendencia, SEM ALVO e com stop  |
//| que acompanha o preco (maximo aproveitamento do movimento).      |
//|                                                                  |
//|  MEDIAS     : EXPONENCIAIS (EMA) de 200 e 20 periodos (ajustavel)|
//|  SENTIMENTO : candle fechando ACIMA da media lenta (padrao 200)  |
//|               -> so COMPRAS; ABAIXO da media lenta -> so VENDAS. |
//|  ENTRADA    : a mercado, sempre que um candle de ALTA fechar     |
//|               acima das DUAS medias (rapida 20 e lenta 200) =    |
//|               compra; um candle de BAIXA que fechar abaixo das   |
//|               duas = venda.                                      |
//|  SAIDA      : nao ha alvo. O stop fica na MINIMA (compra) ou     |
//|               MAXIMA (venda) do candle anterior e e reposicionado|
//|               a cada candle novo. Ele so se aproxima do preco,   |
//|               nunca se afasta. O stop vai ao servidor assim que  |
//|               respeita a distancia minima da corretora; ate la   |
//|               (ou se o preco o atravessar antes) o EA fecha a    |
//|               mercado.                                           |
//|                                                                  |
//| Uso por conta e risco do usuario. Nao constitui recomendacao de  |
//| investimento. Teste sempre em conta demo/Strategy Tester antes   |
//| de operar em conta real.                                        |
//+------------------------------------------------------------------+
#property copyright "MA200_CandleTrail_EA"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//================= INPUTS =====================================
input group "== Medias moveis =="
input int                InpSlowMAPeriod     = 200;           // Media lenta (sentimento): acima = so compra, abaixo = so venda
input int                InpFastMAPeriod     = 20;            // Media rapida: o candle tambem precisa fechar alem dela
input ENUM_MA_METHOD     InpMAMethod         = MODE_EMA;      // Tipo das medias (padrao: exponencial)
input ENUM_APPLIED_PRICE InpMAPrice          = PRICE_CLOSE;   // Preco aplicado nas medias

input group "== Entradas =="
input bool   InpAllowBuy         = true;   // Permite compras (candle de alta acima das medias)
input bool   InpAllowSell        = true;   // Permite vendas (candle de baixa abaixo das medias)
input int    InpMaxEntries       = 1;      // Entradas abertas ao mesmo tempo por sentido (1 = uma por vez; >1 = empilha a cada novo sinal)

input group "== Stop inteligente (sem alvo) =="
input int    InpTrailCandles     = 1;      // Stop na minima (compra) / maxima (venda) das ultimas N velas FECHADAS (1 = vela anterior)
input int    InpSLBufferPoints   = 0;      // Folga (pontos) alem dessa minima/maxima
input bool   InpSellStopAddSpread = true;  // Venda: soma o spread ao stop (o stop de venda dispara no ASK; assim fica simetrico ao da compra)
input int    InpATRPeriod        = 14;     // ATR: usado so como piso da distancia do stop no calculo do lote

input group "== Risco / Execucao =="
input bool   InpEnableTrading    = true;   // false = so desenha/alerta, nao envia ordens (modo teste visual)
input double InpRiskPercent      = 1.0;    // % do saldo arriscado por entrada (ate o stop inicial)
input double InpFixedLot         = 0.0;    // > 0 = lote fixo por entrada (ignora o % de risco)
input int    InpMagicNumber      = 20261011;
input int    InpSlippagePoints   = 10;     // Desvio maximo permitido no preenchimento (pontos); o stop e curto, nao aceite muito
input int    InpMaxSpreadPoints  = 0;      // 0 = nao filtra; caso contrario ignora entradas com spread acima disso

input group "== Visual / Alertas =="
input color  InpColorBuy         = clrDodgerBlue;
input color  InpColorSell        = clrOrangeRed;
input bool   InpDrawObjects      = true;   // Desenha entradas e a linha do stop no grafico
input bool   InpShowPanel        = true;   // Mostra o resumo do estado no canto do grafico
input bool   InpAlertOnTrade     = false;  // Alert() a cada entrada/encerramento (gera muitos alertas em M1)
input bool   InpPushNotification = false;  // Notificacao push a cada entrada/encerramento

//================= ESTADO ======================================
// indice 0 = lado VENDA, indice 1 = lado COMPRA
double     g_trail[2];              // stop alvo em vigor (0 = sem posicoes)
datetime   g_trailTime[2];          // vela a partir da qual a linha do stop e desenhada
int        g_entries[2];            // entradas abertas nesse sentido desde que o lado estava zerado
datetime   g_openTime[2];           // hora da ultima abertura (evita "falso encerramento" logo apos abrir)

bool       g_seeded      = false;       // estado inicial (posicoes ja abertas) recuperado
bool       g_isNetting   = false;       // conta NETTING/EXCHANGE (1 posicao por simbolo)
datetime   g_lastModFail = 0;           // hora da ultima falha de PositionModify (evita insistir a cada tick)
int        g_entrySeq    = 0;

int        g_fastHandle  = INVALID_HANDLE;
int        g_slowHandle  = INVALID_HANDLE;
int        g_atrHandle   = INVALID_HANDLE;
datetime   g_lastBarTime = 0;
string     g_prefix      = "MACT_";

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpSlowMAPeriod < 1 || InpFastMAPeriod < 1 || InpTrailCandles < 1 || InpATRPeriod < 1)
     {
      Print("MA200_CandleTrail_EA: parametros invalidos (periodos das medias, InpTrailCandles e InpATRPeriod devem ser >= 1)");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_slowHandle = iMA(_Symbol, _Period, InpSlowMAPeriod, 0, InpMAMethod, InpMAPrice);
   g_fastHandle = iMA(_Symbol, _Period, InpFastMAPeriod, 0, InpMAMethod, InpMAPrice);
   g_atrHandle  = iATR(_Symbol, _Period, InpATRPeriod);
   if(g_slowHandle == INVALID_HANDLE || g_fastHandle == INVALID_HANDLE || g_atrHandle == INVALID_HANDLE)
     {
      Print("MA200_CandleTrail_EA: falha ao criar handle das medias/ATR");
      return(INIT_FAILED);
     }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   // em conta NETTING/EXCHANGE todas as entradas se fundem numa unica posicao
   // (o volume apenas acumula). A logica funciona igual: o stop e aplicado
   // sobre a posicao inteira
   ENUM_ACCOUNT_MARGIN_MODE marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   g_isNetting = (marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   if(g_isNetting)
      Print("MA200_CandleTrail_EA: conta NETTING/EXCHANGE detectada - as entradas serao somadas numa unica posicao");

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   if(g_slowHandle != INVALID_HANDLE) IndicatorRelease(g_slowHandle);
   if(g_fastHandle != INVALID_HANDLE) IndicatorRelease(g_fastHandle);
   if(g_atrHandle  != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   ObjectsDeleteAll(0, g_prefix);
   Comment("");
  }

//================= AUXILIARES ======================================
int Side(bool isBuy)
  {
   return(isBuy ? 1 : 0);
  }

double GetATR()
  {
   double b[1];
   if(CopyBuffer(g_atrHandle, 0, 1, 1, b) != 1) return(0.0);
   return(b[0]);
  }

bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == 0 || t == g_lastBarTime) return(false);     // 0 = serie ainda nao sincronizada
   g_lastBarTime = t;
   return(true);
  }

// preco alinhado ao tick do simbolo (indices/cripto com tick maior que _Point)
double NormalizePrice(double p)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick > 0.0) p = MathRound(p / tick) * tick;
   return(NormalizeDouble(p, _Digits));
  }

void Notify(string msg)
  {
   Print(msg);
   if(InpAlertOnTrade) Alert(msg);
   if(InpPushNotification) SendNotification(msg);
  }

//================= DESENHO =========================================
void DrawEntry(bool isBuy, double price)
  {
   if(!InpDrawObjects) return;
   string name = g_prefix + "ENT_" + IntegerToString(g_entrySeq % 300);   // buffer circular: nunca passa de 300 setas
   g_entrySeq++;
   ObjectDelete(0, name);
   ObjectCreate(0, name, isBuy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, TimeCurrent(), price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, isBuy ? InpColorBuy : InpColorSell);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

// linha do stop em vigor (recriada a cada vela)
void DrawTrail(bool isBuy)
  {
   if(!InpDrawObjects) return;
   int    s     = Side(isBuy);
   string name  = g_prefix + (isBuy ? "STOP_BUY" : "STOP_SELL");
   string tname = name + "_TXT";
   ObjectDelete(0, name);
   ObjectDelete(0, tname);
   if(g_trail[s] <= 0.0)
     {
      ChartRedraw(0);
      return;
     }

   color clr = isBuy ? InpColorBuy : InpColorSell;
   ObjectCreate(0, name, OBJ_TREND, 0, g_trailTime[s], g_trail[s], TimeCurrent(), g_trail[s]);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   string txt = isBuy ? "STOP compra (minima anterior): " : "STOP venda (maxima anterior): ";
   ObjectCreate(0, tname, OBJ_TEXT, 0, g_trailTime[s], g_trail[s]);
   ObjectSetString(0, tname, OBJPROP_TEXT, txt + DoubleToString(g_trail[s], _Digits));
   ObjectSetInteger(0, tname, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, tname, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, tname, OBJPROP_ANCHOR, isBuy ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, tname, OBJPROP_SELECTABLE, false);
   ChartRedraw(0);
  }

//================= POSICOES ========================================
int CountPositions(bool isBuy)
  {
   ENUM_POSITION_TYPE want = isBuy ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != want) continue;
      n++;
     }
   return(n);
  }

// stop mais apertado entre as posicoes do lado (0 = nenhuma tem stop)
double TightestSL(bool isBuy)
  {
   ENUM_POSITION_TYPE want = isBuy ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   double best = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != want) continue;

      double cur = PositionGetDouble(POSITION_SL);
      if(cur <= 0.0) continue;
      if(best <= 0.0 || (isBuy ? cur > best : cur < best)) best = cur;
     }
   return(best);
  }

void ResetSide(bool isBuy)
  {
   int s = Side(isBuy);
   if(g_trail[s] <= 0.0 && g_entries[s] == 0) return;
   g_trail[s]     = 0.0;
   g_trailTime[s] = 0;
   g_entries[s]   = 0;
   DrawTrail(isBuy);
  }

// fecha todas as posicoes do lado (uso: o preco ja passou do stop e o servidor
// ainda nao conseguiu receber o stop novo)
void CloseSide(bool isBuy)
  {
   ENUM_POSITION_TYPE want = isBuy ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   int closed = 0, failed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != want) continue;

      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      if(trade.PositionClose(ticket))
         closed++;
      else
        {
         failed++;
         Print("MA200_CandleTrail_EA: falha ao fechar a posicao #", ticket, " -> ", trade.ResultRetcodeDescription());
        }
     }

   if(closed > 0 && failed == 0)
     {
      string dir = isBuy ? "COMPRAS" : "VENDAS";
      Notify(_Symbol + " | Stop rompido - " + dir + " fechadas a mercado (" + IntegerToString(closed) + " posicao(oes))");
      ResetSide(isBuy);
     }
  }

//================= SINAL E STOP ====================================
// +1 = ultima vela fechada e de ALTA e fechou acima das duas medias
// -1 = ultima vela fechada e de BAIXA e fechou abaixo das duas medias
//  0 = sem sinal (ou dados ainda indisponiveis)
int GetSignal()
  {
   double f[1], sl[1];
   if(CopyBuffer(g_fastHandle, 0, 1, 1, f)  != 1) return(0);
   if(CopyBuffer(g_slowHandle, 0, 1, 1, sl) != 1) return(0);

   MqlRates r[];
   ArraySetAsSeries(r, true);                      // r[0] = ultima vela FECHADA
   if(CopyRates(_Symbol, _Period, 1, 1, r) != 1) return(0);

   if(r[0].close > r[0].open && r[0].close > f[0] && r[0].close > sl[0]) return(1);
   if(r[0].close < r[0].open && r[0].close < f[0] && r[0].close < sl[0]) return(-1);
   return(0);
  }

// stop "da vela anterior": minima (compra) ou maxima (venda) das ultimas
// InpTrailCandles velas FECHADAS, mais/menos a folga
bool GetTrailLevel(bool isBuy, double &level)
  {
   const int n = InpTrailCandles;
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, _Period, 1, n, r) != n) return(false);

   double buf = InpSLBufferPoints * _Point;
   if(isBuy)
     {
      double lo = r[0].low;
      for(int i = 1; i < n; i++) lo = MathMin(lo, r[i].low);
      level = NormalizePrice(lo - buf);
     }
   else
     {
      // as velas sao de BID, mas o stop de venda dispara no ASK: somar o spread
      // faz o stop de venda tocar a maxima no grafico, espelhando o da compra
      double hi = r[0].high;
      for(int i = 1; i < n; i++) hi = MathMax(hi, r[i].high);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double spreadPrice = (InpSellStopAddSpread && bid > 0.0 && ask > bid) ? ask - bid : 0.0;
      level = NormalizePrice(hi + buf + spreadPrice);
     }
   return(true);
  }

//================= LOTE ============================================
// arredonda PARA BAIXO ao step do simbolo, sem forcar o lote minimo: se o
// risco pedido nao comportar nem o minimo, a entrada e ignorada em vez de
// arriscar mais do que InpRiskPercent
double FloorLotToStep(double lot)
  {
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0) step = 0.01;
   lot = MathFloor(lot / step + 1e-9) * step;
   lot = MathMin(maxLot, lot);
   int digits = (int)MathMax(0.0, MathCeil(-MathLog10(step) - 1e-9));
   return(NormalizeDouble(lot, digits));
  }

double CalcRiskLot(double slDistance)
  {
   if(slDistance <= 0.0) return(0.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);   // valor do tick numa PERDA
   if(tickValue <= 0.0) tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0.0 || tickValue <= 0.0) return(0.0);

   double lossPerLot = (slDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0) return(0.0);

   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   return(FloorLotToStep(riskMoney / lossPerLot));
  }

//================= ENTRADA =========================================
void TryEntry(bool isBuy, double trailLevel)
  {
   int    s   = Side(isBuy);
   string dir = isBuy ? "COMPRA" : "VENDA";

   if(isBuy ? !InpAllowBuy : !InpAllowSell) return;
   if(CountPositions(!isBuy) > 0) return;                       // nunca opera contra posicao aberta
   if(InpMaxEntries > 0 && g_entries[s] >= InpMaxEntries) return; // ja ha entradas demais nesse sentido

   if(InpMaxSpreadPoints > 0)
     {
      long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spread > InpMaxSpreadPoints)
        {
         Print("MA200_CandleTrail_EA: spread (", spread, ") acima do maximo permitido, ", dir, " ignorada");
         return;
        }
     }

   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(bid <= 0.0 || ask <= 0.0)
     {
      Print("MA200_CandleTrail_EA: sem cotacao (bid/ask), ", dir, " ignorada");
      return;
     }
   double price = isBuy ? ask : bid;

   // com posicoes ja abertas, as novas entradas usam o mesmo stop (o mais apertado ate agora)
   double stopWanted = trailLevel;
   if(g_trail[s] > 0.0 && CountPositions(isBuy) > 0)
      stopWanted = g_trail[s];

   // o preco ja passou do stop? entao nao ha entrada com esse stop
   if(isBuy ? (bid <= stopWanted) : (ask >= stopWanted))
     {
      Print("MA200_CandleTrail_EA: preco ja alem do stop (", DoubleToString(stopWanted, _Digits), "), ", dir, " ignorada");
      return;
     }

   double atr = GetATR();
   if(atr <= 0.0)
     {
      Print("MA200_CandleTrail_EA: ATR indisponivel, ", dir, " ignorada");
      return;
     }

   // o servidor recusa stop mais perto do preco que o nivel minimo; nesse caso
   // o stop inicial fica no minimo permitido e o EA o leva ate o nivel certo assim que possivel
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double sl  = stopWanted;
   double pad = 2.0 * _Point;      // folga p/ o preco andar entre a leitura e o servidor receber a ordem
   if(isBuy  && sl > bid - stopLevel) sl = NormalizePrice(bid - stopLevel - pad);
   if(!isBuy && sl < ask + stopLevel) sl = NormalizePrice(ask + stopLevel + pad);

   // NETTING: a nova ordem se funde na posicao existente e o SL dela SUBSTITUI o da posicao;
   // nunca deixa esse SL ficar mais frouxo do que o que a posicao ja tinha
   if(g_isNetting && CountPositions(isBuy) > 0)
     {
      double cur = TightestSL(isBuy);
      if(cur > 0.0)
         sl = isBuy ? MathMax(sl, cur) : MathMin(sl, cur);
     }

   double dist   = MathMax(MathAbs(price - sl), MathMax(0.25 * atr, stopLevel));
   double lot    = (InpFixedLot > 0.0) ? FloorLotToStep(InpFixedLot) : CalcRiskLot(dist);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   if(lot < minLot)
     {
      Print("MA200_CandleTrail_EA: lote calculado (", DoubleToString(lot, 2), ") abaixo do minimo do simbolo, ", dir, " ignorada");
      return;
     }

   string msg = _Symbol + " | " + dir + " a mercado em " + DoubleToString(price, _Digits) +
                " | stop " + DoubleToString(sl, _Digits) + " (" + (isBuy ? "minima" : "maxima") + " anterior)" +
                " | sem alvo | lote " + DoubleToString(lot, 2);

   if(!InpEnableTrading)
     {
      Notify("[SINAL - trading desligado] " + msg);
      DrawEntry(isBuy, price);
      return;
     }

   double margin = 0.0;
   if(OrderCalcMargin(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, lot, price, margin) &&
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      Print("MA200_CandleTrail_EA: margem livre insuficiente para ", DoubleToString(lot, 2), " lote(s), ", dir, " ignorada");
      return;
     }

   string comment = isBuy ? "MACT COMPRA" : "MACT VENDA";
   bool ok = isBuy ? trade.Buy(lot, _Symbol, price, sl, 0.0, comment)
                   : trade.Sell(lot, _Symbol, price, sl, 0.0, comment);
   if(!ok)
     {
      Print("MA200_CandleTrail_EA: falha ao abrir ", dir, " -> ", trade.ResultRetcodeDescription());
      return;
     }

   g_entries[s]++;
   g_openTime[s] = TimeCurrent();
   if(g_trail[s] <= 0.0)
     {
      g_trail[s]     = stopWanted;
      g_trailTime[s] = iTime(_Symbol, _Period, 1);
     }
   DrawEntry(isBuy, price);
   DrawTrail(isBuy);
   Notify(msg);
  }

// Roda a cada tick (barata quando nao ha posicao): leva o stop das posicoes ate o
// nivel em vigor (so aproxima, nunca afasta) e, se o preco ja passou desse nivel
// antes do servidor aceitar o stop, fecha a mercado
void ManageStops(bool isBuy)
  {
   int s = Side(isBuy);

   if(CountPositions(isBuy) == 0)
     {
      // so zera o lado se ele realmente teve entradas e ja deu tempo da posicao aparecer na lista
      if((g_trail[s] > 0.0 || g_entries[s] > 0) && TimeCurrent() - g_openTime[s] >= 3)
        {
         if(g_entries[s] > 0)
            Notify(_Symbol + " | " + (isBuy ? "COMPRAS" : "VENDAS") + " encerradas (stop atingido)");
         ResetSide(isBuy);
        }
      return;
     }
   if(g_trail[s] <= 0.0) return;      // reiniciou com posicao aberta: o nivel e refeito na proxima vela

   double target = g_trail[s];
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0) return;            // sem cotacao: nao decide nada

   if(isBuy ? (bid <= target) : (ask >= target))
     {
      CloseSide(isBuy);
      return;
     }

   // stop colado demais no preco para o servidor: espera o preco se afastar
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(isBuy  && target > bid - stopLevel) return;
   if(!isBuy && target < ask + stopLevel) return;

   if(g_lastModFail > 0 && TimeCurrent() - g_lastModFail < 1) return;   // apos uma falha, espera 1 s

   double freeze = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
   ENUM_POSITION_TYPE want = isBuy ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != want) continue;

      ulong  ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);
      double half   = _Point / 2.0;
      bool   closer = (curSL <= 0.0) || (isBuy ? target > curSL + half : target < curSL - half);
      if(!closer) continue;

      // nivel de congelamento: o servidor nao deixa mexer no stop quando o preco esta colado nele
      if(curSL > 0.0 && (isBuy ? (bid - curSL) <= freeze : (curSL - ask) <= freeze)) continue;

      if(!trade.PositionModify(ticket, target, curTP))
        {
         g_lastModFail = TimeCurrent();
         Print("MA200_CandleTrail_EA: falha ao mover o stop da posicao #", ticket, " -> ", trade.ResultRetcodeDescription());
        }
     }
  }

//================= CICLO PRINCIPAL ==================================
void UpdatePanel()
  {
   if(!InpShowPanel) return;

   double f[1], sl[1];
   string txt = "MA200_CandleTrail_EA | " + _Symbol + "\n";
   if(CopyBuffer(g_fastHandle, 0, 1, 1, f) == 1 && CopyBuffer(g_slowHandle, 0, 1, 1, sl) == 1)
     {
      double c1 = iClose(_Symbol, _Period, 1);
      string bias;
      if(c1 > sl[0])      bias = "ALTA (fechou acima da media " + IntegerToString(InpSlowMAPeriod) + ") -> so COMPRAS";
      else if(c1 < sl[0]) bias = "BAIXA (fechou abaixo da media " + IntegerToString(InpSlowMAPeriod) + ") -> so VENDAS";
      else                bias = "neutro";
      txt += "Sentimento: " + bias + "\n";
      txt += "Media " + IntegerToString(InpSlowMAPeriod) + ": " + DoubleToString(sl[0], _Digits) +
             " | Media " + IntegerToString(InpFastMAPeriod) + ": " + DoubleToString(f[0], _Digits) + "\n";
     }
   txt += "Compras: " + IntegerToString(CountPositions(true));
   if(g_trail[1] > 0.0) txt += " | stop " + DoubleToString(g_trail[1], _Digits);
   txt += "\n";
   txt += "Vendas: " + IntegerToString(CountPositions(false));
   if(g_trail[0] > 0.0) txt += " | stop " + DoubleToString(g_trail[0], _Digits);
   txt += "\n";
   Comment(txt);
  }

// uma vez por vela fechada: reposiciona o stop das posicoes abertas e procura entrada
void ProcessNewBar()
  {
   if(Bars(_Symbol, _Period) < MathMax(InpSlowMAPeriod, InpFastMAPeriod) + InpTrailCandles + 3) return;

   // 1) stop acompanha a vela anterior (so aproxima do preco)
   for(int s = 0; s < 2; s++)
     {
      bool isBuy = (s == 1);
      if(CountPositions(isBuy) == 0) continue;

      double lvl;
      if(!GetTrailLevel(isBuy, lvl)) continue;
      if(g_trail[s] <= 0.0 || (isBuy ? lvl > g_trail[s] : lvl < g_trail[s]))
        {
         g_trail[s]     = lvl;
         g_trailTime[s] = iTime(_Symbol, _Period, 1);
         DrawTrail(isBuy);
        }
     }

   // 2) aplica ja o stop novo (e fecha o lado cujo alvo o preco ja atravessou), para que
   //    um sinal contrario nesta mesma vela nao seja bloqueado por uma posicao que acabou de ser encerrada
   ManageStops(false);
   ManageStops(true);

   // 3) sinal de entrada na vela que acabou de fechar
   int sig = GetSignal();
   if(sig != 0)
     {
      bool wantBuy = (sig > 0);
      double lvl;
      if(GetTrailLevel(wantBuy, lvl))
         TryEntry(wantBuy, lvl);
     }

   UpdatePanel();
  }

// Primeiro contato com o grafico (ou reinicio/troca de timeframe/parametro): recupera o numero de
// entradas e o nivel do stop de posicoes ja abertas e NAO trata a vela em andamento como "vela nova"
// (o EA nao entra no meio de uma vela so porque foi anexado)
bool SeedState()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == 0) return(false);                       // serie ainda nao sincronizada: tenta no proximo tick

   g_lastBarTime = t0;
   for(int s = 0; s < 2; s++)
     {
      bool isBuy = (s == 1);
      int  n     = CountPositions(isBuy);
      if(n == 0) continue;

      g_entries[s] = n;
      double lvl;
      if(GetTrailLevel(isBuy, lvl))
        {
         g_trail[s]     = lvl;
         g_trailTime[s] = iTime(_Symbol, _Period, 1);
         DrawTrail(isBuy);
        }
     }
   g_seeded = true;
   return(true);
  }

void OnTick()
  {
   if(!g_seeded && !SeedState()) return;

   ManageStops(false);
   ManageStops(true);

   if(!IsNewBar()) return;
   ProcessNewBar();

   // envia o stop novo ao servidor ja neste tick, sem esperar o proximo
   ManageStops(false);
   ManageStops(true);
  }
//+------------------------------------------------------------------+
