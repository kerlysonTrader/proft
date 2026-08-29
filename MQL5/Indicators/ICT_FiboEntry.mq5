//+------------------------------------------------------------------+
//|                                              ICT_FiboEntry.mq5   |
//|                                                                  |
//| Indicador de ENTRADA para MT5 baseado no fluxo:                  |
//|  1) Detecta a última perna de impulso (topo->fundo ou            |
//|     fundo->topo) usando fractais de estrutura.                   |
//|  2) Desenha o Fibonacci SEMPRE no sentido da tendência (a favor  |
//|     do impulso), com a zona OTE (Optimal Trade Entry, 61,8%-79%) |
//|     destacada - a "seviye" (nível) SNR/ICT do print 1.           |
//|  3) Localiza um Order Block (RBS/OB) dentro da perna: a última   |
//|     vela oposta antes da vela de deslocamento (print 2).         |
//|  4) Quando o preço entra na zona OTE + confluência com o OB e    |
//|     fecha em rejeição, plota o PONTO DE ENTRADA (print 3),       |
//|     o STOP (ponto definido) e 3 ALVOS (TP1/TP2/TP3), como no     |
//|     resultado final do print 5 ("Sonuç").                        |
//|                                                                  |
//| Uso: apenas educacional / apoio à decisão discricionária.        |
//| Nao constitui recomendacao de investimento. Faca backtest e      |
//| forward test antes de operar em conta real.                     |
//+------------------------------------------------------------------+
#property copyright "ICT_FiboEntry"
#property version   "1.00"
#property strict
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   0

double DummyBuffer[]; // o indicador nao plota linha, so objetos graficos

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

input group "== Gestao / Stop =="
input int    InpSLBufferPoints   = 50;     // Buffer do stop alem do OB/extremo (em pontos)

input group "== Visual =="
input color  InpColorBuy         = clrDodgerBlue;
input color  InpColorSell        = clrOrangeRed;
input color  InpColorOB          = clrKhaki;
input color  InpColorOTE         = clrPaleTurquoise;
input int    InpBoxExtendBars    = 150;    // Quantas velas as caixas/linhas se estendem p/ direita

input group "== Alertas =="
input bool   InpAlertOnSignal    = true;   // Alert() nativo do terminal
input bool   InpPushNotification = false;  // Notificacao push (celular)

//================= ESTRUTURAS / ESTADO ==========================
struct SwingPoint
  {
   datetime time;
   double   price;
   int      shift;   // indice na serie local (0 = vela mais recente) no momento do calculo
   bool     isHigh;
  };

enum SetupState
  {
   STATE_SEARCHING,    // procurando uma perna valida
   STATE_ZONE_READY,   // perna + fibo (+ OB) desenhados, aguardando preco entrar na zona
   STATE_SIGNAL_FIRED  // entrada ja confirmada e plotada para esta perna
  };

SwingPoint g_legStart, g_legEnd;
bool       g_haveLeg      = false;
bool       g_legIsBearish = false;   // true = perna de ALTA->BAIXA (topo->fundo => setup de VENDA)
SetupState g_state        = STATE_SEARCHING;
string     g_prefix       = "";
datetime   g_lastBarTime  = 0;
int        g_atrHandle    = INVALID_HANDLE;

double     g_obHigh = 0.0, g_obLow = 0.0;
bool       g_haveOB = false;

//+------------------------------------------------------------------+
int OnInit()
  {
   SetIndexBuffer(0, DummyBuffer, INDICATOR_DATA);
   ArraySetAsSeries(DummyBuffer, true);

   g_atrHandle = iATR(_Symbol, _Period, InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE)
     {
      Print("ICT_FiboEntry: falha ao criar handle do ATR");
      return(INIT_FAILED);
     }

   IndicatorSetString(INDICATOR_SHORTNAME, "ICT Fibo Entry");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   ObjectsDeleteAll(0, "ICTFE_");
  }

//================= FUNCOES AUXILIARES ============================

// preco em um "nivel" da perna. Convencao: 0% = extremo da perna (fim, mais
// recente), 100% = origem da perna (inicio). Assim 61,8%-79% cai perto da
// origem (zona "premium"/"discount" - a OTE), e niveis negativos estendem
// o movimento ALEM do extremo (para os alvos de continuacao).
double PriceAtLevel(double level)
  {
   return(g_legEnd.price + level * (g_legStart.price - g_legEnd.price));
  }

// localiza fractais de topo/fundo nos arrays locais (index 0 = vela atual)
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
   return(cnt); // out[] fica ordenado do mais recente para o mais antigo (i cresce = mais antigo)
  }

// converte a lista de fractais numa sequencia em "zig-zag" (alternando
// topo/fundo, mantendo sempre o mais extremo) e devolve a ULTIMA perna
bool GetLastLeg(const SwingPoint &sw[], int cnt, const double &atr, SwingPoint &legStart, SwingPoint &legEnd, bool &bearish)
  {
   if(cnt < 2) return(false);

   SwingPoint zz[]; int zc = 0;
   for(int i = cnt-1; i >= 0; i--) // percorre do mais antigo para o mais recente
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
         // mesmo tipo em sequencia: fica com o mais extremo
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
   bearish  = legStart.isHigh; // topo -> fundo = perna baixista

   double legSize = MathAbs(legEnd.price - legStart.price);
   if(atr <= 0 || legSize < InpMinLegATR * atr)
      return(false);

   return(true);
  }

// procura, dentro da perna, a vela de deslocamento mais proxima da ORIGEM
// e usa a ultima vela de cor oposta antes dela como Order Block (RBS/OB)
void FindOrderBlock(const datetime &tm[], const double &o[], const double &h[], const double &l[], const double &c[], double atr, datetime &obTime)
  {
   g_haveOB = false;
   obTime = 0;
   if(atr <= 0) return;

   int iOrigin = g_legStart.shift;              // mais antigo (origem da perna)
   int iEnd    = g_legEnd.shift;                 // mais recente (extremo da perna)
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
         return; // achou deslocamento mas nenhuma vela oposta antes -> sem OB
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
   // ancoras: preco1 = extremo da perna (nivel 0%), preco2 = origem (nivel 100%)
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

   // retangulo destacando a zona OTE (a "seviye"/nivel SNR-ICT do print 1)
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

   // linha RBS: borda do OB mais proxima do preco/extremo da perna
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

void DrawLevelLine(string name, double price, datetime fromTime, color clr, string text, ENUM_LINE_STYLE style)
  {
   ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_TREND, 0, fromTime, price, RightEdgeTime(), price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   string tname = name + "_TXT";
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

//================= SINAL DE ENTRADA ===============================
void CheckEntrySignal(const datetime &tm[], const double &o[], const double &h[], const double &l[], const double &c[])
  {
   double zTop = PriceAtLevel(MathMax(InpOTEStart, InpOTEEnd));
   double zBot = PriceAtLevel(MathMin(InpOTEStart, InpOTEEnd));

   double confTop = zTop, confBot = zBot;
   if(InpUseOB)
     {
      if(!g_haveOB) return; // exige OB e ainda nao foi encontrado nesta perna
      confTop = MathMin(zTop, MathMax(g_obHigh, g_obLow));
      confBot = MathMax(zBot, MathMin(g_obHigh, g_obLow));
      if(confBot > confTop) return; // OTE e OB nao se sobrepoem: sem confluencia
     }

   double curHigh = h[0], curLow = l[0], curOpen = o[0], curClose = c[0];

   bool touchedZone = (curLow <= confTop && curHigh >= confBot);
   if(!touchedZone) return;

   bool rejection;
   if(g_legIsBearish)
      rejection = (curClose < curOpen) && (curClose < confBot);   // fechou abaixo da zona = rejeicao de venda
   else
      rejection = (curClose > curOpen) && (curClose > confTop);   // fechou acima da zona = rejeicao de compra

   if(!rejection) return;

   FireSignal(tm[0], curClose);
  }

void FireSignal(datetime signalTime, double entryPrice)
  {
   g_state = STATE_SIGNAL_FIRED;

   double point = _Point;
   double slPrice, tp1, tp2, tp3;

   tp1 = PriceAtLevel(InpTP1Level);
   tp2 = PriceAtLevel(InpTP2Level);
   tp3 = PriceAtLevel(-(InpTP3Extension - 1.0));

   double structureEdge = g_legStart.price;
   if(g_haveOB)
      structureEdge = g_legIsBearish ? MathMax(g_obHigh, structureEdge) : MathMin(g_obLow, structureEdge);

   slPrice = g_legIsBearish ? structureEdge + InpSLBufferPoints*point
                             : structureEdge - InpSLBufferPoints*point;

   color clr = g_legIsBearish ? InpColorSell : InpColorBuy;

   string an = g_prefix + "ENTRY_ARROW";
   ObjectDelete(0, an);
   ObjectCreate(0, an, g_legIsBearish ? OBJ_ARROW_DOWN : OBJ_ARROW_UP, 0, signalTime, entryPrice);
   ObjectSetInteger(0, an, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, an, OBJPROP_WIDTH, 3);
   ObjectSetInteger(0, an, OBJPROP_SELECTABLE, false);

   DrawLevelLine(g_prefix+"ENTRY", entryPrice, signalTime, clr,
                 "ENTRADA " + DoubleToString(entryPrice,_Digits), STYLE_SOLID);
   DrawLevelLine(g_prefix+"SL", slPrice, signalTime, clrRed,
                 "STOP (ponto definido) " + DoubleToString(slPrice,_Digits), STYLE_DASH);
   DrawLevelLine(g_prefix+"TP1", tp1, signalTime, clrLimeGreen,
                 "ALVO 1  " + DoubleToString(tp1,_Digits), STYLE_DOT);
   DrawLevelLine(g_prefix+"TP2", tp2, signalTime, clrLimeGreen,
                 "ALVO 2  " + DoubleToString(tp2,_Digits), STYLE_DOT);
   DrawLevelLine(g_prefix+"TP3", tp3, signalTime, clrLimeGreen,
                 "ALVO 3  " + DoubleToString(tp3,_Digits), STYLE_DOT);

   string dir = g_legIsBearish ? "VENDA" : "COMPRA";
   string msg = StringFormat("%s %s | Sinal %s | Entrada %s | Stop %s | Alvos %s / %s / %s",
                              _Symbol, EnumToString((ENUM_TIMEFRAMES)_Period), dir,
                              DoubleToString(entryPrice,_Digits), DoubleToString(slPrice,_Digits),
                              DoubleToString(tp1,_Digits), DoubleToString(tp2,_Digits), DoubleToString(tp3,_Digits));

   if(InpAlertOnSignal) Alert(msg);
   if(InpPushNotification) SendNotification(msg);
  }

//================= OnCalculate ====================================
int OnCalculate(const int rates_total,
                 const int prev_calculated,
                 const datetime &time[],
                 const double &open[],
                 const double &high[],
                 const double &low[],
                 const double &close[],
                 const long &tick_volume[],
                 const long &volume[],
                 const int &spread[])
  {
   int minBars = InpSwingBars*2 + InpOBLookback + 10;
   if(rates_total < minBars) return(rates_total);

   // so recalcula no fechamento de uma nova vela (evita reprocessar a cada tick)
   datetime curBarTime = iTime(_Symbol, _Period, 0);
   if(curBarTime == g_lastBarTime) return(rates_total);
   g_lastBarTime = curBarTime;

   // exclui a vela ainda em formacao (indice rates_total-1): todo o calculo
   // deve enxergar apenas velas ja FECHADAS, com indice 0 = ultima fechada
   int copyCount = MathMin(rates_total-1, 3000);
   if(copyCount < minBars) return(rates_total);

   double t_atr[];
   ArraySetAsSeries(t_atr, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 5, t_atr) <= 0) return(rates_total);
   double atrVal = t_atr[0];

   datetime tm[]; double o[], h[], l[], c[];
   ArrayCopy(tm, time,  0, rates_total-1-copyCount, copyCount);
   ArrayCopy(o,  open,  0, rates_total-1-copyCount, copyCount);
   ArrayCopy(h,  high,  0, rates_total-1-copyCount, copyCount);
   ArrayCopy(l,  low,   0, rates_total-1-copyCount, copyCount);
   ArrayCopy(c,  close, 0, rates_total-1-copyCount, copyCount);
   ArraySetAsSeries(tm, true);
   ArraySetAsSeries(o,  true);
   ArraySetAsSeries(h,  true);
   ArraySetAsSeries(l,  true);
   ArraySetAsSeries(c,  true);

   SwingPoint swings[];
   int sc = FindFractals(copyCount, h, l, swings, tm);

   SwingPoint legStart, legEnd;
   bool bearish;
   if(!GetLastLeg(swings, sc, atrVal, legStart, legEnd, bearish))
     {
      InvalidateSetup();
      return(rates_total);
     }

   bool isNewLeg = (!g_haveLeg || legStart.time != g_legStart.time || legEnd.time != g_legEnd.time);
   if(isNewLeg)
     {
      InvalidateSetup();
      g_legStart = legStart;
      g_legEnd   = legEnd;
      g_legIsBearish = bearish;
      g_haveLeg  = true;
      g_prefix   = "ICTFE_" + IntegerToString((long)legEnd.time) + "_";

      DrawFibo();

      datetime obTime;
      FindOrderBlock(tm, o, h, l, c, atrVal, obTime);
      if(g_haveOB)
         DrawOB(obTime);

      g_state = STATE_ZONE_READY;
     }

   // invalidacao: preco fechou alem da origem da perna (rompeu a estrutura)
   if(g_haveLeg)
     {
      if(g_legIsBearish && c[0] > g_legStart.price) { InvalidateSetup(); return(rates_total); }
      if(!g_legIsBearish && c[0] < g_legStart.price) { InvalidateSetup(); return(rates_total); }
     }

   if(g_state == STATE_ZONE_READY)
      CheckEntrySignal(tm, o, h, l, c);

   return(rates_total);
  }
//+------------------------------------------------------------------+
