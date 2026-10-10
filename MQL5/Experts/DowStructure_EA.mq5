//+------------------------------------------------------------------+
//|                                             DowStructure_EA.mq5  |
//|                                                                  |
//| Expert Advisor de ESTRUTURA DE MERCADO (Teoria de Dow).          |
//|                                                                  |
//|  FILTRO   : preco ABAIXO da media movel (padrao 178) -> so       |
//|             VENDAS; preco ACIMA da media -> so COMPRAS.          |
//|  ENTRADA  : a cada NOVO TOPO confirmado (venda) ou NOVO FUNDO    |
//|             confirmado (compra), a favor da tendencia, abre uma  |
//|             operacao A MERCADO. Os topos/fundos sao fractais     |
//|             (N velas de cada lado) e, por padrao, o novo topo    |
//|             precisa ser MENOR que o anterior (e o novo fundo     |
//|             MAIOR que o anterior), ou seja, a estrutura de Dow   |
//|             (topos e fundos descendentes / ascendentes).         |
//|  SAIDA    : QUEBRA DE ESTRUTURA. Vendas fecham quando o mercado  |
//|             rompe o ultimo topo; compras fecham quando rompe o   |
//|             ultimo fundo. O nivel acompanha a estrutura: a cada  |
//|             novo topo mais baixo (venda) / novo fundo mais alto  |
//|             (compra) ele se aproxima do preco, nunca se afasta.  |
//|                                                                  |
//| Uso por conta e risco do usuario. Nao constitui recomendacao de  |
//| investimento. Teste sempre em conta demo/Strategy Tester antes   |
//| de operar em conta real.                                        |
//+------------------------------------------------------------------+
#property copyright "DowStructure_EA"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//================= INPUTS =====================================
input group "== Filtro de tendencia (media movel) =="
input int                InpMAPeriod         = 178;             // Periodo da media movel
input ENUM_MA_METHOD     InpMAMethod         = MODE_SMA;        // Tipo da media movel
input ENUM_APPLIED_PRICE InpMAPrice          = PRICE_CLOSE;     // Preco aplicado na media
input ENUM_TIMEFRAMES    InpMATimeframe      = PERIOD_CURRENT;  // Timeframe da media (CURRENT = o do grafico)

input group "== Estrutura de Dow (topos e fundos) =="
input int    InpSwingBars         = 3;      // Velas de cada lado p/ confirmar um topo/fundo (fractal)
input bool   InpRequireStructure  = true;   // Venda so em topo MENOR que o anterior / compra so em fundo MAIOR que o anterior
input int    InpScanBars          = 300;    // Velas analisadas p/ localizar os ultimos topos/fundos

input group "== Entradas =="
input bool   InpAllowSell         = true;   // Permite vendas (preco abaixo da media)
input bool   InpAllowBuy          = true;   // Permite compras (preco acima da media)
input int    InpMaxEntries        = 10;     // Maximo de entradas acumuladas por sentido (0 = sem limite)

input group "== Saida (quebra de estrutura) =="
input bool   InpBreakByClose      = true;   // true = vela FECHA alem do topo/fundo; false = preco toca o nivel (por tick)
input int    InpBOSBufferPoints   = 0;      // Folga (pontos) alem do topo/fundo p/ considerar a estrutura quebrada
input bool   InpUseHardSL         = true;   // SL de emergencia no servidor (nivel da estrutura + folga em ATR)
input double InpHardSLATRMult     = 3.0;    // Folga do SL de emergencia alem do nivel, em multiplos do ATR (so p/ gaps/picos)
input int    InpATRPeriod         = 14;     // Periodo do ATR

input group "== Risco / Execucao =="
input bool   InpEnableTrading     = true;   // false = so desenha/alerta, nao envia ordens (modo teste visual)
input double InpRiskPercent       = 1.0;    // % do saldo arriscado por entrada (ate o SL de emergencia)
input double InpFixedLot          = 0.0;    // > 0 = lote fixo por entrada (ignora o % de risco)
input int    InpMagicNumber       = 20261010;
input int    InpSlippagePoints    = 30;     // Desvio maximo permitido no preenchimento (pontos)
input int    InpMaxSpreadPoints   = 0;      // 0 = nao filtra; caso contrario ignora entradas com spread acima disso

input group "== Visual / Alertas =="
input color  InpColorBuy          = clrDodgerBlue;
input color  InpColorSell         = clrOrangeRed;
input bool   InpDrawObjects       = true;   // Desenha topos/fundos, entradas e o nivel de saida no grafico
input bool   InpShowPanel         = true;   // Mostra o resumo do estado no canto do grafico
input bool   InpAlertOnTrade      = true;   // Alert() a cada entrada/saida
input bool   InpPushNotification  = false;  // Notificacao push a cada entrada/saida

//================= ESTADO ======================================
struct SwingPoint
  {
   datetime time;
   double   price;
  };

SwingPoint g_hi[2];                 // ultimos topos confirmados  (0 = mais recente)
SwingPoint g_lo[2];                 // ultimos fundos confirmados (0 = mais recente)
int        g_hiCount     = 0;
int        g_loCount     = 0;
datetime   g_lastHiTime  = 0;       // ultimo topo ja tratado
datetime   g_lastLoTime  = 0;       // ultimo fundo ja tratado
bool       g_seeded      = false;

// indice 0 = lado VENDA (nivel = ultimo topo), indice 1 = lado COMPRA (nivel = ultimo fundo)
double     g_level[2];              // nivel de quebra de estrutura em vigor (0 = sem posicoes)
datetime   g_levelTime[2];
int        g_entries[2];            // entradas acumuladas desde que o lado estava zerado

int        g_atrHandle   = INVALID_HANDLE;
int        g_maHandle    = INVALID_HANDLE;
datetime   g_lastBarTime = 0;
int        g_swingSeq    = 0;
string     g_prefix      = "DOWEA_";

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpSwingBars < 1 || InpMAPeriod < 1 || InpATRPeriod < 1)
     {
      Print("DowStructure_EA: parametros invalidos (InpSwingBars, InpMAPeriod e InpATRPeriod devem ser >= 1)");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_atrHandle = iATR(_Symbol, _Period, InpATRPeriod);
   g_maHandle  = iMA(_Symbol, InpMATimeframe, InpMAPeriod, 0, InpMAMethod, InpMAPrice);
   if(g_atrHandle == INVALID_HANDLE || g_maHandle == INVALID_HANDLE)
     {
      Print("DowStructure_EA: falha ao criar handle do ATR/media movel");
      return(INIT_FAILED);
     }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   // em conta NETTING/EXCHANGE todas as entradas se fundem numa unica posicao
   // (o volume apenas acumula). A logica funciona igual: o SL e o fechamento
   // por quebra de estrutura sao aplicados sobre a posicao inteira
   ENUM_ACCOUNT_MARGIN_MODE marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      Print("DowStructure_EA: conta NETTING/EXCHANGE detectada - as entradas serao somadas numa unica posicao");

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   if(g_maHandle  != INVALID_HANDLE) IndicatorRelease(g_maHandle);
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

// +1 = ultimo fechamento ACIMA da media (procura compras)
// -1 = ultimo fechamento ABAIXO da media (procura vendas)
//  0 = indefinido (media ainda nao calculada)
int TrendDirection()
  {
   double ma[1];
   if(CopyBuffer(g_maHandle, 0, 1, 1, ma) != 1) return(0);
   double c1 = iClose(_Symbol, _Period, 1);
   if(c1 <= 0.0) return(0);
   if(c1 < ma[0]) return(-1);
   if(c1 > ma[0]) return(1);
   return(0);
  }

bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == g_lastBarTime) return(false);
   g_lastBarTime = t;
   return(true);
  }

void Notify(string msg)
  {
   Print(msg);
   if(InpAlertOnTrade) Alert(msg);
   if(InpPushNotification) SendNotification(msg);
  }

//================= DESENHO =========================================
void DrawSwing(const SwingPoint &sw, bool isLow)
  {
   if(!InpDrawObjects) return;
   string name = g_prefix + "SW_" + IntegerToString(g_swingSeq % 200);   // buffer circular: nunca passa de 200 marcas
   g_swingSeq++;
   ObjectDelete(0, name);
   ObjectCreate(0, name, isLow ? OBJ_ARROW_UP : OBJ_ARROW_DOWN, 0, sw.time, sw.price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrSilver);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, isLow ? ANCHOR_TOP : ANCHOR_BOTTOM);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void DrawEntry(bool isBuy, double price)
  {
   if(!InpDrawObjects) return;
   string name = g_prefix + "ENT_" + IntegerToString((long)TimeCurrent()) + (isBuy ? "_B" : "_S");
   ObjectDelete(0, name);
   ObjectCreate(0, name, isBuy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, TimeCurrent(), price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, isBuy ? InpColorBuy : InpColorSell);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void DrawExit(bool isBuy)
  {
   if(!InpDrawObjects) return;
   double price = SymbolInfoDouble(_Symbol, isBuy ? SYMBOL_BID : SYMBOL_ASK);
   string name = g_prefix + "EXIT_" + IntegerToString((long)TimeCurrent()) + (isBuy ? "_B" : "_S");
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_ARROW_STOP, 0, TimeCurrent(), price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrGold);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

// linha do nivel de quebra de estrutura (= nivel de saida) em vigor
void DrawBOS(bool isBuy)
  {
   if(!InpDrawObjects) return;
   int    s    = Side(isBuy);
   string name = g_prefix + (isBuy ? "BOS_BUY" : "BOS_SELL");
   string tname = name + "_TXT";
   ObjectDelete(0, name);
   ObjectDelete(0, tname);
   if(g_level[s] <= 0.0)
     {
      ChartRedraw(0);
      return;
     }

   color clr = isBuy ? InpColorBuy : InpColorSell;
   ObjectCreate(0, name, OBJ_TREND, 0, g_levelTime[s], g_level[s], TimeCurrent(), g_level[s]);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   string txt = isBuy ? "SAIDA compras: quebra do fundo " : "SAIDA vendas: quebra do topo ";
   ObjectCreate(0, tname, OBJ_TEXT, 0, g_levelTime[s], g_level[s]);
   ObjectSetString(0, tname, OBJPROP_TEXT, txt + DoubleToString(g_level[s], _Digits));
   ObjectSetInteger(0, tname, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, tname, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, tname, OBJPROP_ANCHOR, isBuy ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, tname, OBJPROP_SELECTABLE, false);
   ChartRedraw(0);
  }

//================= ESTRUTURA (topos e fundos) =======================
// Procura, nas ultimas InpScanBars velas FECHADAS, os 2 topos e os 2 fundos
// confirmados mais recentes. Um topo (fundo) so e confirmado depois que
// InpSwingBars velas fecham abaixo (acima) dele, entao ele nunca "repinta".
// Empate de maximas/minimas: vale a vela MAIS NOVA do par (assim um topo
// duplo nao e ignorado).
bool ScanSwings()
  {
   const int n = InpSwingBars;
   int avail = Bars(_Symbol, _Period) - 1;                  // sem a vela em formacao
   int cnt   = MathMin(MathMax(InpScanBars, 6 * n + 10), avail);
   if(cnt < 2 * n + 2) return(false);

   MqlRates r[];
   ArraySetAsSeries(r, true);                               // r[0] = ultima vela FECHADA
   if(CopyRates(_Symbol, _Period, 1, cnt, r) != cnt) return(false);

   g_hiCount = 0;
   g_loCount = 0;
   for(int i = n; i < cnt - n && (g_hiCount < 2 || g_loCount < 2); i++)
     {
      bool isHigh = true, isLow = true;
      for(int k = 1; k <= n && (isHigh || isLow); k++)
        {
         // r[i-k] = velas mais NOVAS (confirmacao); r[i+k] = velas mais ANTIGAS
         if(r[i].high <= r[i-k].high || r[i].high < r[i+k].high) isHigh = false;
         if(r[i].low  >= r[i-k].low  || r[i].low  > r[i+k].low)  isLow  = false;
        }
      if(isHigh && g_hiCount < 2)
        {
         g_hi[g_hiCount].time  = r[i].time;
         g_hi[g_hiCount].price = r[i].high;
         g_hiCount++;
        }
      if(isLow && g_loCount < 2)
        {
         g_lo[g_loCount].time  = r[i].time;
         g_lo[g_loCount].price = r[i].low;
         g_loCount++;
        }
     }
   return(true);
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

// SL de emergencia (servidor): nivel da estrutura + folga + ATR, do lado oposto ao trade
double HardSLPrice(bool isBuy, double level, double atr)
  {
   double d  = InpBOSBufferPoints * _Point + InpHardSLATRMult * atr;
   double sl = isBuy ? level - d : level + d;
   return(NormalizeDouble(sl, _Digits));
  }

// aproxima o SL de todas as posicoes do lado (nunca afasta)
void TightenStops(bool isBuy, double newSL)
  {
   if(!InpUseHardSL || newSL <= 0.0) return;

   ENUM_POSITION_TYPE want = isBuy ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // o servidor recusa SL colado demais no preco; nesse caso mantem o SL
   // anterior (a saida por quebra de estrutura continua valendo)
   if(isBuy  && newSL > bid - stopLevel) return;
   if(!isBuy && newSL < ask + stopLevel) return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != want) continue;

      ulong  ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      double curSL  = PositionGetDouble(POSITION_SL);
      double curTP  = PositionGetDouble(POSITION_TP);
      bool   closer = (curSL <= 0.0) || (isBuy ? newSL > curSL : newSL < curSL);
      if(!closer) continue;

      if(!trade.PositionModify(ticket, newSL, curTP))
         Print("DowStructure_EA: falha ao mover o SL da posicao #", ticket, " -> ", trade.ResultRetcodeDescription());
     }
  }

void ResetSide(bool isBuy)
  {
   int s = Side(isBuy);
   if(g_level[s] <= 0.0 && g_entries[s] == 0) return;
   g_level[s]     = 0.0;
   g_levelTime[s] = 0;
   g_entries[s]   = 0;
   DrawBOS(isBuy);
  }

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
         Print("DowStructure_EA: falha ao fechar a posicao #", ticket, " -> ", trade.ResultRetcodeDescription());
        }
     }

   if(closed > 0 && failed == 0)
     {
      string dir = isBuy ? "COMPRAS" : "VENDAS";
      string lvl = isBuy ? "fundo" : "topo";
      Notify(_Symbol + " | Estrutura quebrada - " + dir + " fechadas (" + IntegerToString(closed) +
             " posicao(oes)) | rompeu o " + lvl + " " + DoubleToString(g_level[Side(isBuy)], _Digits));
      DrawExit(isBuy);
      ResetSide(isBuy);
     }
  }

// reconstroi o nivel de quebra a partir do ultimo topo/fundo confirmado
// (EA reiniciado com posicoes abertas, ou posicao que ainda nao apareceu na lista)
void RecoverLevel(bool isBuy)
  {
   int s = Side(isBuy);
   if(isBuy)
     {
      if(g_loCount <= 0) return;
      g_level[s]     = g_lo[0].price;
      g_levelTime[s] = g_lo[0].time;
     }
   else
     {
      if(g_hiCount <= 0) return;
      g_level[s]     = g_hi[0].price;
      g_levelTime[s] = g_hi[0].time;
     }
   g_entries[s] = MathMax(g_entries[s], CountPositions(isBuy));
   DrawBOS(isBuy);
  }

//================= SAIDA: QUEBRA DE ESTRUTURA =======================
// Roda a cada tick (barata quando nao ha posicao).
//  - VENDAS : fecham quando o mercado rompe PARA CIMA o ultimo topo
//  - COMPRAS: fecham quando o mercado rompe PARA BAIXO o ultimo fundo
// "Rompe" = fechamento da ultima vela alem do nivel (InpBreakByClose=true)
// ou preco atual alem do nivel (InpBreakByClose=false), mais a folga.
void CheckStructureExit(bool isBuy)
  {
   int s = Side(isBuy);

   if(CountPositions(isBuy) == 0)
     {
      ResetSide(isBuy);
      return;
     }
   if(g_level[s] <= 0.0)
     {
      RecoverLevel(isBuy);
      if(g_level[s] <= 0.0) return;
     }

   double buf   = InpBOSBufferPoints * _Point;
   double level = g_level[s];
   bool   broken;

   if(isBuy)
     {
      double ref = InpBreakByClose ? iClose(_Symbol, _Period, 1) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      broken = (ref < level - buf);
     }
   else
     {
      double ref = InpBreakByClose ? iClose(_Symbol, _Period, 1) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      broken = (ref > level + buf);
     }

   if(broken)
      CloseSide(isBuy);
  }

//================= ENTRADA =========================================
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

// lote para arriscar InpRiskPercent% do saldo ate o SL. Pode devolver menos
// que o lote minimo de proposito: o chamador ignora a entrada em vez de
// arriscar mais do que o configurado
double CalcRiskLot(double slDistance)
  {
   if(slDistance <= 0.0) return(0.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0.0 || tickValue <= 0.0) return(0.0);

   double lossPerLot = (slDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0) return(0.0);

   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   return(FloorLotToStep(riskMoney / lossPerLot));
  }

void OpenStructureTrade(bool isBuy, const SwingPoint &sw)
  {
   int    s   = Side(isBuy);
   string dir = isBuy ? "COMPRA" : "VENDA";
   string src = isBuy ? "novo fundo " : "novo topo ";

   if(InpMaxEntries > 0 && g_entries[s] >= InpMaxEntries)
     {
      Print("DowStructure_EA: limite de ", InpMaxEntries, " entradas acumuladas atingido, ", dir, " ignorada");
      return;
     }

   if(InpMaxSpreadPoints > 0)
     {
      long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spread > InpMaxSpreadPoints)
        {
         Print("DowStructure_EA: spread (", spread, ") acima do maximo permitido, ", dir, " ignorada");
         return;
        }
     }

   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = isBuy ? ask : bid;

   // o preco ja passou do topo/fundo? entao a estrutura ja esta quebrada
   if(isBuy ? (bid <= sw.price) : (ask >= sw.price))
     {
      Print("DowStructure_EA: preco ja alem do ", src, DoubleToString(sw.price, _Digits), ", ", dir, " ignorada");
      return;
     }

   double atr = GetATR();
   if(atr <= 0.0)
     {
      Print("DowStructure_EA: ATR indisponivel, ", dir, " ignorada");
      return;
     }

   // ---- stop de emergencia e distancia usada no calculo do risco ----
   double buf       = InpBOSBufferPoints * _Point;
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double slHard    = 0.0;
   double slRef     = isBuy ? sw.price - buf : sw.price + buf;

   if(InpUseHardSL)
     {
      slHard = HardSLPrice(isBuy, sw.price, atr);
      if(isBuy  && slHard > bid - stopLevel) slHard = NormalizeDouble(bid - stopLevel, _Digits);
      if(!isBuy && slHard < ask + stopLevel) slHard = NormalizeDouble(ask + stopLevel, _Digits);
      slRef = slHard;
     }
   double dist = MathMax(MathAbs(price - slRef), MathMax(0.25 * atr, stopLevel));

   double lot = (InpFixedLot > 0.0) ? FloorLotToStep(InpFixedLot) : CalcRiskLot(dist);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   if(lot < minLot)
     {
      Print("DowStructure_EA: lote calculado (", DoubleToString(lot, 2), ") abaixo do minimo do simbolo, ", dir, " ignorada");
      return;
     }

   string msg = _Symbol + " | " + dir + " a mercado em " + DoubleToString(price, _Digits) + " | " + src +
                DoubleToString(sw.price, _Digits) + " | saida: quebra de " + (isBuy ? "fundo" : "topo") +
                " | SL emergencia " + (InpUseHardSL ? DoubleToString(slHard, _Digits) : "nenhum") +
                " | lote " + DoubleToString(lot, 2);

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
      Print("DowStructure_EA: margem livre insuficiente para ", DoubleToString(lot, 2), " lote(s), ", dir, " ignorada");
      return;
     }

   string comment = isBuy ? "DOW COMPRA" : "DOW VENDA";
   bool ok = isBuy ? trade.Buy(lot, _Symbol, price, slHard, 0.0, comment)
                   : trade.Sell(lot, _Symbol, price, slHard, 0.0, comment);
   if(!ok)
     {
      Print("DowStructure_EA: falha ao abrir ", dir, " -> ", trade.ResultRetcodeDescription());
      return;
     }

   g_entries[s]++;
   g_level[s]     = sw.price;
   g_levelTime[s] = sw.time;
   DrawEntry(isBuy, price);
   DrawBOS(isBuy);
   Notify(msg);
  }

// Chamada UMA vez para cada novo topo (isBuy=false) ou novo fundo (isBuy=true) confirmado
void HandleNewSwing(bool isBuy)
  {
   int        s   = Side(isBuy);
   SwingPoint sw;
   double     prev = 0.0;
   int        cnt;

   if(isBuy)
     {
      sw  = g_lo[0];
      cnt = g_loCount;
      if(cnt >= 2) prev = g_lo[1].price;
     }
   else
     {
      sw  = g_hi[0];
      cnt = g_hiCount;
      if(cnt >= 2) prev = g_hi[1].price;
     }

   DrawSwing(sw, isBuy);

   bool haveOpen  = (CountPositions(isBuy) > 0);
   bool tightened = false;

   // 1) ja ha posicoes nesse sentido: um topo mais BAIXO (venda) / fundo mais
   //    ALTO (compra) aproxima o nivel de quebra do preco. Nunca afasta.
   if(haveOpen && g_level[s] > 0.0 && (isBuy ? sw.price > g_level[s] : sw.price < g_level[s]))
     {
      g_level[s]     = sw.price;
      g_levelTime[s] = sw.time;
      double atr = GetATR();
      if(atr > 0.0)
         TightenStops(isBuy, HardSLPrice(isBuy, sw.price, atr));
      DrawBOS(isBuy);
      tightened = true;
     }

   // 2) filtros de entrada
   if(isBuy ? !InpAllowBuy : !InpAllowSell) return;
   if(TrendDirection() != (isBuy ? 1 : -1)) return;   // vende abaixo da media, compra acima
   if(CountPositions(!isBuy) > 0) return;             // nunca opera contra posicao aberta
   if(haveOpen && !tightened) return;                 // acumula so quando a estrutura continua valida e mais "apertada"

   if(InpRequireStructure)
     {
      if(cnt < 2) return;
      // venda: topo MENOR que o anterior (topos descendentes)
      // compra: fundo MAIOR que o anterior (fundos ascendentes)
      if(isBuy ? !(sw.price > prev) : !(sw.price < prev)) return;
     }

   OpenStructureTrade(isBuy, sw);
  }

//================= CICLO PRINCIPAL ==================================
void UpdatePanel()
  {
   if(!InpShowPanel) return;

   int trend = TrendDirection();
   string t;
   if(trend < 0)      t = "BAIXA (fechou abaixo da media) -> procura VENDAS em novo topo";
   else if(trend > 0) t = "ALTA (fechou acima da media) -> procura COMPRAS em novo fundo";
   else               t = "indefinida";

   string txt = "DowStructure_EA | " + _Symbol + "\n";
   txt += "Tendencia: " + t + "\n";
   if(g_hiCount > 0)
      txt += "Ultimo topo: " + DoubleToString(g_hi[0].price, _Digits) +
             (g_hiCount > 1 ? "  (anterior " + DoubleToString(g_hi[1].price, _Digits) + ")" : "") + "\n";
   if(g_loCount > 0)
      txt += "Ultimo fundo: " + DoubleToString(g_lo[0].price, _Digits) +
             (g_loCount > 1 ? "  (anterior " + DoubleToString(g_lo[1].price, _Digits) + ")" : "") + "\n";
   txt += "Vendas: " + IntegerToString(CountPositions(false));
   if(g_level[0] > 0.0) txt += " | sai se romper o topo " + DoubleToString(g_level[0], _Digits);
   txt += "\n";
   txt += "Compras: " + IntegerToString(CountPositions(true));
   if(g_level[1] > 0.0) txt += " | sai se romper o fundo " + DoubleToString(g_level[1], _Digits);
   txt += "\n";
   Comment(txt);
  }

// Primeiro contato com o grafico: registra o ultimo topo/fundo SEM operar
// (nao entra num topo antigo) e recupera o nivel de saida de posicoes ja abertas
bool SeedState()
  {
   if(!ScanSwings()) return(false);

   g_lastHiTime = (g_hiCount > 0) ? g_hi[0].time : 0;
   g_lastLoTime = (g_loCount > 0) ? g_lo[0].time : 0;

   for(int s = 0; s < 2; s++)
     {
      bool isBuy = (s == 1);
      if(CountPositions(isBuy) > 0)
         RecoverLevel(isBuy);
     }

   g_seeded = true;
   return(true);
  }

// uma vez por vela fechada: procura topo/fundo recem confirmado
void ProcessNewBar()
  {
   if(!ScanSwings()) return;

   if(g_hiCount > 0 && g_hi[0].time != g_lastHiTime)
     {
      g_lastHiTime = g_hi[0].time;
      HandleNewSwing(false);       // novo topo  -> venda (se abaixo da media)
     }
   if(g_loCount > 0 && g_lo[0].time != g_lastLoTime)
     {
      g_lastLoTime = g_lo[0].time;
      HandleNewSwing(true);        // novo fundo -> compra (se acima da media)
     }

   UpdatePanel();
  }

void OnTick()
  {
   if(!g_seeded && !SeedState()) return;

   // saida por quebra de estrutura: a cada tick (a checagem por fechamento
   // de vela usa a ultima vela fechada, entao so "dispara" na vela seguinte)
   CheckStructureExit(false);
   CheckStructureExit(true);

   if(!IsNewBar()) return;
   ProcessNewBar();
  }
//+------------------------------------------------------------------+
