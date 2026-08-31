//+------------------------------------------------------------------+
//|                                           ICT_FiboEntry_EA.mq5   |
//|                                                                  |
//| Expert Advisor baseado na mesma logica do indicador              |
//| ICT_FiboEntry: detecta a ultima perna de estrutura, desenha o    |
//| Fibonacci a favor da tendencia com a zona OTE, localiza um       |
//| Order Block (RBS/OB) de confluencia e, ao confirmar rejeicao     |
//| dentro da zona, ABRE ORDENS reais (3 pernas: TP1/TP2/TP3), com   |
//| lote calculado por % de risco do saldo e mesmo Stop Loss.        |
//|                                                                  |
//| Uso por conta e risco do usuario. Nao constitui recomendacao de  |
//| investimento. Teste sempre em conta demo/Strategy Tester antes   |
//| de operar em conta real.                                        |
//+------------------------------------------------------------------+
#property copyright "ICT_FiboEntry_EA"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//================= INPUTS =====================================
input group "== Estrutura (Swings) =="
input int    InpSwingBars        = 5;      // Velas de cada lado p/ validar topo/fundo (fractal)
input int    InpATRPeriod        = 14;     // Periodo do ATR (filtros de tamanho/deslocamento)
input double InpMinLegATR        = 3.0;    // Tamanho minimo da perna, em multiplos do ATR

input group "== Fibonacci / Zona OTE =="
input double InpOTEStart         = 0.618;  // Inicio da zona OTE (retracao)
input double InpOTEEnd           = 0.79;   // Fim da zona OTE (retracao)
input double InpTP1Level         = 0.5;    // Nivel fib do Alvo 1 (parcial)
input double InpTP2Level         = 0.0;    // Nivel fib do Alvo 2 (extremo/estrutura)
input double InpTP3Extension     = 1.618;  // Extensao (alem do extremo) para o Alvo 3

input group "== Order Block (RBS/OB) =="
input bool   InpUseOB            = true;   // Exigir confluencia com Order Block p/ entrar
input double InpDisplacementATR  = 1.5;    // Vela de "deslocamento" = corpo >= X * ATR
input int    InpOBLookback        = 40;     // Velas (a partir da origem) analisadas p/ achar o OB

input group "== Risco / Execucao =="
input bool   InpEnableTrading    = true;   // false = so desenha/alerta, nao envia ordens (modo teste visual)
input double InpRiskPercent      = 1.0;    // % do saldo arriscado por sinal (dividido entre as pernas abertas)
input int    InpSLBufferPoints   = 50;     // Buffer do stop alem do OB/extremo (em pontos)
input int    InpMagicNumber      = 20260831;
input int    InpSlippagePoints   = 30;     // Desvio maximo permitido no preenchimento (pontos)
input int    InpMaxSpreadPoints  = 0;      // 0 = nao filtra; caso contrario ignora sinais com spread acima disso
input bool   InpOneSetupAtATime  = true;   // impede novo conjunto de ordens enquanto houver posicoes abertas deste EA/simbolo

input group "== Visual =="
input color  InpColorBuy         = clrDodgerBlue;
input color  InpColorSell        = clrOrangeRed;
input color  InpColorOB          = clrKhaki;
input color  InpColorOTE         = clrPaleTurquoise;
input int    InpBoxExtendBars    = 150;    // Quantas velas as caixas/linhas se estendem p/ direita

input group "== Alertas =="
input bool   InpAlertOnSignal    = true;
input bool   InpPushNotification = false;

//================= ESTRUTURAS / ESTADO ==========================
struct SwingPoint
  {
   datetime time;
   double   price;
   int      shift;
   bool     isHigh;
  };

struct TradeLeg
  {
   double tp;
   double lot;
   string label;
  };

enum SetupState
  {
   STATE_SEARCHING,
   STATE_ZONE_READY,
   STATE_SIGNAL_FIRED
  };

SwingPoint g_legStart, g_legEnd;
bool       g_haveLeg      = false;
bool       g_legIsBearish = false;
SetupState g_state        = STATE_SEARCHING;
string     g_prefix       = "";     // objetos da busca (fibo/OTE/OB) - refeitos a cada nova perna
string     g_activePrefix = "";     // objetos de uma entrada ja executada - so somem quando as posicoes fecharem
datetime   g_lastBarTime  = 0;
int        g_atrHandle    = INVALID_HANDLE;

double     g_obHigh = 0.0, g_obLow = 0.0;
bool       g_haveOB = false;

bool       g_allowMultiplePositions = true; // false em conta/simbolo NETTING (1 posicao por simbolo)

//+------------------------------------------------------------------+
int OnInit()
  {
   g_atrHandle = iATR(_Symbol, _Period, InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE)
     {
      Print("ICT_FiboEntry_EA: falha ao criar handle do ATR");
      return(INIT_FAILED);
     }
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);

   // em conta NETTING (ou exchange), so existe 1 posicao por simbolo: varias
   // chamadas Buy()/Sell() em sequencia nao abririam 3 posicoes separadas,
   // elas se fundiriam numa unica posicao e a ULTIMA chamada sobrescreveria
   // o SL/TP das anteriores - por isso, nesse tipo de conta, o EA usa
   // sempre 1 unica entrada (com o alvo intermediario TP2), nunca 3
   ENUM_ACCOUNT_MARGIN_MODE marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   g_allowMultiplePositions = (marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   if(!g_allowMultiplePositions)
      Print("ICT_FiboEntry_EA: conta em modo NETTING/EXCHANGE detectada - usando 1 entrada por sinal (sem dividir em 3 pernas)");

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   ObjectsDeleteAll(0, "ICTFEEA_");
  }

//================= FUNCOES AUXILIARES (estrutura) =================
double PriceAtLevel(double level)
  {
   return(g_legEnd.price + level * (g_legStart.price - g_legEnd.price));
  }

int FindFractals(int total, const double &h[], const double &l[], SwingPoint &out[], const datetime &tm[])
  {
   ArrayResize(out, 0);
   int cnt = 0;
   for(int i = InpSwingBars; i < total - InpSwingBars; i++)
     {
      bool isHigh = true, isLow = true;
      for(int k = 1; k <= InpSwingBars && (isHigh || isLow); k++)
        {
         if(h[i] <= h[i-k] || h[i] <= h[i+k]) isHigh = false;
         if(l[i] >= l[i-k] || l[i] >= l[i+k]) isLow  = false;
        }
      if(isHigh)
        {
         ArrayResize(out, cnt+1);
         out[cnt].time = tm[i]; out[cnt].price = h[i]; out[cnt].shift = i; out[cnt].isHigh = true;
         cnt++;
        }
      if(isLow)
        {
         ArrayResize(out, cnt+1);
         out[cnt].time = tm[i]; out[cnt].price = l[i]; out[cnt].shift = i; out[cnt].isHigh = false;
         cnt++;
        }
     }
   return(cnt);
  }

bool GetLastLeg(const SwingPoint &sw[], int cnt, double atr, SwingPoint &legStart, SwingPoint &legEnd, bool &bearish)
  {
   if(cnt < 2) return(false);

   SwingPoint zz[]; int zc = 0;
   for(int i = cnt-1; i >= 0; i--)
     {
      SwingPoint s = sw[i];
      if(zc == 0)
        {
         ArrayResize(zz, 1);
         zz[0] = s;
         zc = 1;
         continue;
        }
      SwingPoint last = zz[zc-1];
      if(s.isHigh == last.isHigh)
        {
         if(s.isHigh  && s.price >= last.price) zz[zc-1] = s;
         if(!s.isHigh && s.price <= last.price) zz[zc-1] = s;
        }
      else
        {
         ArrayResize(zz, zc+1);
         zz[zc] = s;
         zc++;
        }
     }

   if(zc < 2) return(false);

   legStart = zz[zc-2];
   legEnd   = zz[zc-1];
   bearish  = legStart.isHigh;

   double legSize = MathAbs(legEnd.price - legStart.price);
   if(atr <= 0 || legSize < InpMinLegATR * atr)
      return(false);

   return(true);
  }

void FindOrderBlock(const datetime &tm[], const double &o[], const double &h[], const double &l[], const double &c[], double atr, datetime &obTime)
  {
   g_haveOB = false;
   obTime = 0;
   if(atr <= 0) return;

   int iOrigin = g_legStart.shift;
   int iEnd    = g_legEnd.shift;
   int iLimit  = MathMin(iOrigin, iEnd + InpOBLookback);

   for(int i = iLimit; i > iEnd; i--)
     {
      double bodyRange = MathAbs(c[i] - o[i]);
      bool   displacement = (bodyRange >= InpDisplacementATR * atr);
      bool   dirMatches   = g_legIsBearish ? (c[i] < o[i]) : (c[i] > o[i]);

      if(displacement && dirMatches)
        {
         for(int j = i+1; j <= iLimit; j++)
           {
            bool oppositeColor = g_legIsBearish ? (c[j] > o[j]) : (c[j] < o[j]);
            if(oppositeColor)
              {
               g_obHigh = h[j];
               g_obLow  = l[j];
               g_haveOB = true;
               obTime   = tm[j];
               return;
              }
           }
         return;
        }
     }
  }

//================= DESENHO =======================================
datetime RightEdgeTime()
  {
   return((datetime)(g_legEnd.time + (long)PeriodSeconds() * InpBoxExtendBars));
  }

void DrawFibo()
  {
   string name = g_prefix + "FIBO";
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_FIBO, 0, g_legEnd.time, g_legEnd.price, g_legStart.time, g_legStart.price);

   double levels[] = {0.0, InpTP1Level, InpOTEStart, InpOTEEnd, 1.0, -(InpTP3Extension-1.0)};
   string texts[]  = {"0% - extremo (ALVO2)", "TP1", "OTE inicio", "OTE fim", "100% - origem", "ALVO3 (ext.)"};

   int lvlCount = ArraySize(levels);
   ObjectSetInteger(0, name, OBJPROP_LEVELS, lvlCount);
   for(int i = 0; i < lvlCount; i++)
     {
      ObjectSetDouble(0, name, OBJPROP_LEVELVALUE, i, levels[i]);
      ObjectSetString(0, name, OBJPROP_LEVELTEXT, i, texts[i] + " %$");
      bool inOTE = (levels[i] >= MathMin(InpOTEStart,InpOTEEnd) && levels[i] <= MathMax(InpOTEStart,InpOTEEnd));
      ObjectSetInteger(0, name, OBJPROP_LEVELCOLOR, i, inOTE ? InpColorOTE : clrSilver);
     }
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrSilver);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);

   double top = PriceAtLevel(MathMax(InpOTEStart, InpOTEEnd));
   double bot = PriceAtLevel(MathMin(InpOTEStart, InpOTEEnd));
   string rname = g_prefix + "OTEZONE";
   ObjectDelete(0, rname);
   ObjectCreate(0, rname, OBJ_RECTANGLE, 0, g_legEnd.time, top, RightEdgeTime(), bot);
   ObjectSetInteger(0, rname, OBJPROP_COLOR, InpColorOTE);
   ObjectSetInteger(0, rname, OBJPROP_FILL, true);
   ObjectSetInteger(0, rname, OBJPROP_BACK, true);
   ObjectSetInteger(0, rname, OBJPROP_SELECTABLE, false);
  }

void DrawOB(datetime obTime)
  {
   string rname = g_prefix + "OB";
   ObjectDelete(0, rname);
   ObjectCreate(0, rname, OBJ_RECTANGLE, 0, obTime, g_obHigh, RightEdgeTime(), g_obLow);
   ObjectSetInteger(0, rname, OBJPROP_COLOR, InpColorOB);
   ObjectSetInteger(0, rname, OBJPROP_FILL, true);
   ObjectSetInteger(0, rname, OBJPROP_BACK, true);
   ObjectSetInteger(0, rname, OBJPROP_SELECTABLE, false);

   string lname = g_prefix + "RBS";
   double rbsPrice = g_legIsBearish ? g_obHigh : g_obLow;
   ObjectDelete(0, lname);
   ObjectCreate(0, lname, OBJ_TREND, 0, obTime, rbsPrice, RightEdgeTime(), rbsPrice);
   ObjectSetInteger(0, lname, OBJPROP_COLOR, clrDarkGoldenrod);
   ObjectSetInteger(0, lname, OBJPROP_STYLE, STYLE_DASHDOT);
   ObjectSetInteger(0, lname, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, lname, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, lname, OBJPROP_SELECTABLE, false);

   string tname = lname + "_TXT";
   ObjectDelete(0, tname);
   ObjectCreate(0, tname, OBJ_TEXT, 0, obTime, rbsPrice);
   ObjectSetString(0, tname, OBJPROP_TEXT, "RBS / OB");
   ObjectSetInteger(0, tname, OBJPROP_COLOR, clrDarkGoldenrod);
   ObjectSetInteger(0, tname, OBJPROP_FONTSIZE, 8);
  }

void DrawLevelLine(string prefix, string name, double price, datetime fromTime, color clr, string text, ENUM_LINE_STYLE style)
  {
   string full = prefix + name;
   ObjectDelete(0, full);
   ObjectCreate(0, full, OBJ_TREND, 0, fromTime, price, RightEdgeTime(), price);
   ObjectSetInteger(0, full, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, full, OBJPROP_STYLE, style);
   ObjectSetInteger(0, full, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, full, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);

   string tname = full + "_TXT";
   ObjectDelete(0, tname);
   ObjectCreate(0, tname, OBJ_TEXT, 0, fromTime, price);
   ObjectSetString(0, tname, OBJPROP_TEXT, text);
   ObjectSetInteger(0, tname, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, tname, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, tname, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
  }

void InvalidateSetup()
  {
   if(g_prefix != "")
      ObjectsDeleteAll(0, g_prefix);
   g_haveLeg = false;
   g_haveOB  = false;
   g_state   = STATE_SEARCHING;
   g_prefix  = "";
  }

//================= GESTAO DE RISCO / EXECUCAO =====================
bool HasOpenPositions()
  {
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      string sym = PositionGetSymbol(i);
      if(sym == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         return(true);
     }
   return(false);
  }

// trava de seguranca: enquanto o setup estiver "congelado" com uma posicao
// aberta, verifica se o preco atual ja passou do Stop registrado na propria
// posicao. Isso NUNCA deveria acontecer (a corretora deveria ter fechado
// pelo SL), mas serve de rede de seguranca contra corrupcao de SL/TP (ex.:
// contas NETTING fundindo varias ordens) ou qualquer outra falha de
// execucao - sem isso, o EA ficaria travado indefinidamente numa posicao
// que nunca fecha sozinha, como visto no teste
void ManageOpenPositions()
  {
   for(int i = PositionsTotal()-1; i >= 0; i--)
     {
      string sym = PositionGetSymbol(i);
      if(sym != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      double posSL = PositionGetDouble(POSITION_SL);
      if(posSL <= 0) continue; // sem SL definido, nada a verificar aqui

      long   type   = PositionGetInteger(POSITION_TYPE);
      ulong  ticket = PositionGetInteger(POSITION_TICKET);
      double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      bool breached = (type == POSITION_TYPE_BUY  && bid <= posSL) ||
                      (type == POSITION_TYPE_SELL && ask >= posSL);

      if(breached)
        {
         Print("ICT_FiboEntry_EA: preco ja passou do Stop (", posSL,
               ") e a posicao #", ticket, " continua aberta - fechando manualmente");
         trade.PositionClose(ticket);
        }
     }
  }

// arredonda PARA BAIXO ao step do simbolo, sem forcar o lote minimo -
// se o risco calculado for menor que o minimo negociavel, o resultado
// fica abaixo de SYMBOL_VOLUME_MIN de proposito, para que BuildLegs()
// possa detectar isso e reduzir o numero de pernas (ou nao entrar),
// em vez de silenciosamente arriscar mais do que InpRiskPercent pede
double FloorLotToStep(double lot)
  {
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = 0.01;
   lot = MathFloor(lot/step) * step;
   lot = MathMin(maxLot, lot);
   return(NormalizeDouble(lot, 2));
  }

// lote TOTAL (soma das pernas) para arriscar InpRiskPercent% do saldo,
// dada a distancia entre entrada e stop
double CalcTotalLot(double entryPrice, double slPrice)
  {
   double slDistance = MathAbs(entryPrice - slPrice);
   if(slDistance <= 0) return(0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0 || tickValue <= 0) return(0);

   double lossPerLot = (slDistance/tickSize) * tickValue;
   if(lossPerLot <= 0) return(0);

   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   return(riskMoney / lossPerLot);
  }

// divide o lote total em ate 3 pernas (TP1/TP2/TP3); se o lote minimo do
// simbolo nao permitir 3 pernas, reduz para 2 e depois para 1 (usando o
// alvo intermediario TP2 nesse ultimo caso). Em conta NETTING/EXCHANGE
// (g_allowMultiplePositions=false), sempre usa 1 unica entrada, porque
// varias posicoes no mesmo simbolo se fundiriam automaticamente
int BuildLegs(double totalLot, double tp1, double tp2, double tp3, TradeLeg &legs[])
  {
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   if(!g_allowMultiplePositions)
     {
      double soloLot = FloorLotToStep(totalLot);
      if(soloLot >= minLot)
        {
         ArrayResize(legs, 1);
         legs[0].tp = tp2; legs[0].lot = soloLot; legs[0].label = "TP2";
         return(1);
        }
      ArrayResize(legs, 0);
      return(0);
     }

   double perLeg3 = FloorLotToStep(totalLot/3.0);
   if(perLeg3 >= minLot)
     {
      ArrayResize(legs, 3);
      legs[0].tp = tp1; legs[0].lot = perLeg3; legs[0].label = "TP1";
      legs[1].tp = tp2; legs[1].lot = perLeg3; legs[1].label = "TP2";
      legs[2].tp = tp3; legs[2].lot = perLeg3; legs[2].label = "TP3";
      return(3);
     }

   double perLeg2 = FloorLotToStep(totalLot/2.0);
   if(perLeg2 >= minLot)
     {
      ArrayResize(legs, 2);
      legs[0].tp = tp1; legs[0].lot = perLeg2; legs[0].label = "TP1";
      legs[1].tp = tp2; legs[1].lot = perLeg2; legs[1].label = "TP2";
      return(2);
     }

   double full = FloorLotToStep(totalLot);
   if(full >= minLot)
     {
      ArrayResize(legs, 1);
      legs[0].tp = tp2; legs[0].lot = full; legs[0].label = "TP2";
      return(1);
     }

   ArrayResize(legs, 0);
   return(0);
  }

void OpenTradeSet(bool isBuy, double slPrice, double tp1, double tp2, double tp3, string activePrefix)
  {
   if(InpOneSetupAtATime && HasOpenPositions())
     {
      Print("ICT_FiboEntry_EA: ja existe posicao aberta deste EA no simbolo, sinal ignorado");
      return;
     }

   if(InpMaxSpreadPoints > 0)
     {
      long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spread > InpMaxSpreadPoints)
        {
         Print("ICT_FiboEntry_EA: spread (", spread, ") acima do maximo permitido, sinal ignorado");
         return;
        }
     }

   double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double totalLot = CalcTotalLot(price, slPrice);
   if(totalLot <= 0)
     {
      Print("ICT_FiboEntry_EA: nao foi possivel calcular o lote (SL invalido?), sinal ignorado");
      return;
     }

   TradeLeg legs[];
   int n = BuildLegs(totalLot, tp1, tp2, tp3, legs);
   if(n == 0)
     {
      Print("ICT_FiboEntry_EA: lote calculado abaixo do minimo do simbolo, sinal ignorado");
      return;
     }

   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   int opened = 0;

   for(int i = 0; i < n; i++)
     {
      double sl  = slPrice;
      double tp  = legs[i].tp;

      if(isBuy)
        {
         if(price - sl < stopLevel) sl = price - stopLevel;
         if(tp - price < stopLevel) tp = price + stopLevel;
        }
      else
        {
         if(sl - price < stopLevel) sl = price + stopLevel;
         if(price - tp < stopLevel) tp = price - stopLevel;
        }

      bool ok = isBuy ? trade.Buy(legs[i].lot, _Symbol, price, sl, tp, "ICTFE " + legs[i].label)
                       : trade.Sell(legs[i].lot, _Symbol, price, sl, tp, "ICTFE " + legs[i].label);
      if(ok)
        {
         opened++;
         DrawLevelLine(activePrefix, "TP_"+legs[i].label, tp, TimeCurrent(),
                       clrLimeGreen, "ALVO " + legs[i].label + "  " + DoubleToString(tp,_Digits), STYLE_DOT);
        }
      else
         Print("ICT_FiboEntry_EA: falha ao abrir perna ", legs[i].label, " -> ", trade.ResultRetcodeDescription());
     }

   if(opened > 0)
     {
      color clr = isBuy ? InpColorBuy : InpColorSell;

      string an = activePrefix + "ENTRY_ARROW";
      ObjectDelete(0, an);
      ObjectCreate(0, an, isBuy ? OBJ_ARROW_UP : OBJ_ARROW_DOWN, 0, TimeCurrent(), price);
      ObjectSetInteger(0, an, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, an, OBJPROP_WIDTH, 3);
      ObjectSetInteger(0, an, OBJPROP_ANCHOR, isBuy ? ANCHOR_TOP : ANCHOR_BOTTOM);
      ObjectSetInteger(0, an, OBJPROP_SELECTABLE, false);

      DrawLevelLine(activePrefix, "ENTRY", price, TimeCurrent(), clr,
                    "ENTRADA " + DoubleToString(price,_Digits), STYLE_SOLID);
      DrawLevelLine(activePrefix, "SL", slPrice, TimeCurrent(), clrRed,
                    "STOP (ponto definido) " + DoubleToString(slPrice,_Digits), STYLE_DASH);
      g_activePrefix = activePrefix;
      ChartRedraw(0);
     }
  }

//================= SINAL DE ENTRADA ===============================
void CheckEntrySignal(const datetime &tm[], const double &o[], const double &h[], const double &l[], const double &c[])
  {
   double zTop = PriceAtLevel(MathMax(InpOTEStart, InpOTEEnd));
   double zBot = PriceAtLevel(MathMin(InpOTEStart, InpOTEEnd));

   double confTop = zTop, confBot = zBot;
   if(InpUseOB)
     {
      if(!g_haveOB) return;
      confTop = MathMin(zTop, MathMax(g_obHigh, g_obLow));
      confBot = MathMax(zBot, MathMin(g_obHigh, g_obLow));
      if(confBot > confTop) return;
     }

   double curHigh = h[0], curLow = l[0], curOpen = o[0], curClose = c[0];

   bool touchedZone = (curLow <= confTop && curHigh >= confBot);
   if(!touchedZone) return;

   bool rejection;
   if(g_legIsBearish)
      rejection = (curClose < curOpen) && (curClose < confBot);
   else
      rejection = (curClose > curOpen) && (curClose > confTop);

   if(!rejection) return;

   FireSignal(tm[0], curClose);
  }

void FireSignal(datetime signalTime, double entryPrice)
  {
   g_state = STATE_SIGNAL_FIRED;

   double point = _Point;
   double tp1 = PriceAtLevel(InpTP1Level);
   double tp2 = PriceAtLevel(InpTP2Level);
   double tp3 = PriceAtLevel(-(InpTP3Extension - 1.0));

   double structureEdge = g_legStart.price;
   if(g_haveOB)
      structureEdge = g_legIsBearish ? MathMax(g_obHigh, structureEdge) : MathMin(g_obLow, structureEdge);

   double slPrice = g_legIsBearish ? structureEdge + InpSLBufferPoints*point
                                    : structureEdge - InpSLBufferPoints*point;

   string dir = g_legIsBearish ? "VENDA" : "COMPRA";
   string msg = StringFormat("%s %s | Sinal %s | Entrada ~%s | Stop %s | Alvos %s / %s / %s",
                              _Symbol, EnumToString(_Period), dir,
                              DoubleToString(entryPrice,_Digits), DoubleToString(slPrice,_Digits),
                              DoubleToString(tp1,_Digits), DoubleToString(tp2,_Digits), DoubleToString(tp3,_Digits));

   if(InpAlertOnSignal) Alert(msg);
   if(InpPushNotification) SendNotification(msg);
   Print(msg);

   if(InpEnableTrading)
     {
      string activePrefix = "ICTFEEA_ACTIVE_" + IntegerToString((long)signalTime) + "_";
      OpenTradeSet(!g_legIsBearish, slPrice, tp1, tp2, tp3, activePrefix);
     }
  }

//================= NOVA VELA =======================================
bool IsNewBar()
  {
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == g_lastBarTime) return(false);
   g_lastBarTime = t;
   return(true);
  }

bool GetRecentData(int copyCount, datetime &tm[], double &o[], double &h[], double &l[], double &c[])
  {
   if(CopyTime(_Symbol, _Period, 1, copyCount, tm)  <= 0) return(false);
   if(CopyOpen(_Symbol, _Period, 1, copyCount, o)   <= 0) return(false);
   if(CopyHigh(_Symbol, _Period, 1, copyCount, h)   <= 0) return(false);
   if(CopyLow(_Symbol, _Period, 1, copyCount, l)    <= 0) return(false);
   if(CopyClose(_Symbol, _Period, 1, copyCount, c)  <= 0) return(false);
   return(true);
  }

//================= OnTick =========================================
void OnTick()
  {
   // libera os objetos de uma entrada ja executada assim que as posicoes fecharem
   if(g_activePrefix != "" && !HasOpenPositions())
     {
      ObjectsDeleteAll(0, g_activePrefix);
      g_activePrefix = "";
     }

   // roda a cada tick (nao so a cada vela nova) para reagir rapido caso o
   // preco passe do Stop e a corretora nao tenha fechado a posicao
   if(HasOpenPositions())
      ManageOpenPositions();

   if(!IsNewBar()) return;

   // enquanto houver posicao aberta deste EA (e InpOneSetupAtATime=true), congela
   // a busca por uma nova perna: sem isso, o Fibo/OTE/OB da tela era redesenhado
   // para a perna mais recente a cada nova vela, mesmo com uma operacao ja aberta
   // baseada numa perna anterior - fazendo a zona "pular" para longe do preco
   // atual e sem relacao nenhuma com a operacao em andamento
   if(InpOneSetupAtATime && HasOpenPositions()) return;

   int minBars = InpSwingBars*2 + InpOBLookback + 10;
   int totalBars = Bars(_Symbol, _Period);
   if(totalBars-1 < minBars) return;

   int copyCount = MathMin(totalBars-1, 3000);

   double atrBuf[];
   ArraySetAsSeries(atrBuf, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 5, atrBuf) <= 0) return;
   double atrVal = atrBuf[0];

   datetime tm[]; double o[], h[], l[], c[];
   if(!GetRecentData(copyCount, tm, o, h, l, c)) return;

   SwingPoint swings[];
   int sc = FindFractals(copyCount, h, l, swings, tm);

   SwingPoint legStart, legEnd;
   bool bearish;
   if(!GetLastLeg(swings, sc, atrVal, legStart, legEnd, bearish))
     {
      InvalidateSetup();
      return;
     }

   bool isNewLeg = (!g_haveLeg || legStart.time != g_legStart.time || legEnd.time != g_legEnd.time);
   if(isNewLeg)
     {
      InvalidateSetup();
      g_legStart = legStart;
      g_legEnd   = legEnd;
      g_legIsBearish = bearish;
      g_haveLeg  = true;
      g_prefix   = "ICTFEEA_" + IntegerToString((long)legEnd.time) + "_";

      DrawFibo();

      datetime obTime;
      FindOrderBlock(tm, o, h, l, c, atrVal, obTime);
      if(g_haveOB)
         DrawOB(obTime);

      ChartRedraw(0);
      g_state = STATE_ZONE_READY;
     }

   if(g_haveLeg)
     {
      if(g_legIsBearish && c[0] > g_legStart.price) { InvalidateSetup(); return; }
      if(!g_legIsBearish && c[0] < g_legStart.price) { InvalidateSetup(); return; }
     }

   if(g_state == STATE_ZONE_READY)
      CheckEntrySignal(tm, o, h, l, c);
  }
//+------------------------------------------------------------------+
