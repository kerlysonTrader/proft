# 05 — Painel (dashboard) e integração robô ↔ painel

## O que é

Um app web (feito no **Lovable**, banco **Lovable Cloud/Supabase**) para
acompanhar o robô de qualquer lugar, inclusive no celular. **Já está criado**
no seu workspace Lovable com o nome "Bybit Trader View":

| Página | O que mostra |
|---|---|
| **Visão Geral** | Status do robô (ONLINE/OFFLINE pelo heartbeat), modo PAPER/DEMO/LIVE, regime de mercado, patrimônio, P&L dia/7d/30d/total, acerto, profit factor, expectância em R, drawdown, curva de patrimônio, **posições abertas com preço e P&L ao vivo**, feed de eventos, botão **Pausar/Retomar robô** |
| **Mercado ao Vivo** | Cotações em tempo real (WebSocket público da Bybit) de BTC, ETH, das 20 melhores do scanner, das posições abertas e da sua watchlist; gráfico de candles com entrada/stop/alvos |
| **Scanner** | Ranking das moedas com o score detalhado por componente e o veredito do Gemini |
| **Sinais** | Todos os sinais de entrada gerados e o que aconteceu com cada um |
| **Operações** | Histórico completo, filtros, estatísticas, P&L por trade/setup, exportar CSV |
| **Risco** | Perda diária vs limite, drawdown semanal, exposição por moeda, kill switch |
| **Logs** | Feed em tempo real dos logs do robô |
| **Integração** | URL da API, exemplos de JSON, botões para carregar/limpar dados de demonstração |

Links do projeto (preenchidos após a criação):
- Editor Lovable: https://lovable.dev/projects/2f34128e-4585-4e6d-9fa8-1a0c53ee3e9d
- Preview: https://id-preview--2f34128e-4585-4e6d-9fa8-1a0c53ee3e9d.lovable.app

### Segurança do painel
- Login obrigatório; o **primeiro usuário cadastrado vira o dono** — cadastre-se
  você mesmo logo após publicar. Outros cadastros não enxergam nada.
- O navegador **não escreve** nada, exceto os comandos de pausar/retomar.
- O painel **não tem chave da Bybit** e **não envia ordens**.
- O robô escreve pelo endpoint `/api/public/bot-ingest` do próprio app,
  autenticado pelo header `x-bot-token` (valor guardado como secret
  `BOT_INGEST_TOKEN` no Lovable e no Google Secret Manager).
- Verificado no banco: RLS ativo em todas as tabelas, leitura só para o dono
  (`is_owner()`), e o navegador só pode inserir comandos `pause`/`resume`.

### Primeiros passos no painel
1. **Cadastre-se primeiro** pelo link de preview (a primeira conta vira a
   dona; depois disso ninguém mais enxerga os dados) e confirme o e-mail.
2. No editor Lovable, em **Project Settings → Secrets**, crie o secret
   `BOT_INGEST_TOKEN` com um valor aleatório longo (ex.:
   `openssl rand -hex 32`). Guarde o mesmo valor no Google Secret Manager.
3. Clique em **Publish** no Lovable. O endpoint do robô só funciona no app
   publicado.
4. Em **Integração**, clique em **Carregar dados de demonstração** para ver o
   painel funcionando. Quando o robô começar a enviar dados reais, clique em
   **Limpar dados de demonstração**.

---

## Contrato da API `bot-ingest`

```
POST https://<seu-app>.lovable.app/api/public/bot-ingest
Content-Type: application/json
x-bot-token: <BOT_INGEST_TOKEN>

{ "type": "<tipo>", "payload": { ... } }
```

Respostas: `200 {"ok": true, "id": "..."}` · `400` (JSON/campos inválidos) ·
`401` (token inválido). A URL exata aparece na página **Integração** do painel
depois de publicado.

### Tipos e exemplos de payload

**heartbeat** (a cada 60 s)
```json
{"type": "heartbeat", "payload": {
  "mode": "paper", "version": "0.1.0", "market_regime": "risk_on",
  "btc_price": 64250.5, "equity_usdt": 1000.0, "free_usdt": 620.0,
  "open_positions": 2, "daily_pnl_usdt": 4.2, "daily_loss_limit_usdt": 30.0,
  "weekly_drawdown_pct": 1.1, "weekly_dd_limit_pct": 6.0, "max_open_positions": 4,
  "kill_switch": false, "paused": false, "message": "ok"}}
```

**scanner_run** (a cada execução do scanner)
```json
{"type": "scanner_run", "payload": {
  "run": {"run_at": "2026-10-11T13:00:00Z", "regime": "risk_on",
          "universe_size": 142, "candidates": 9, "duration_ms": 48210},
  "results": [{
    "symbol": "SOLUSDT", "price": 152.31, "change_24h_pct": 3.4,
    "turnover_24h_usdt": 185000000, "score": 78,
    "score_trend": 25, "score_relative_strength": 14, "score_volume": 14,
    "score_squeeze": 11, "score_derivatives": 7, "score_momentum": 10,
    "penalties": -3, "rsi_1h": 58.2, "rsi_4h": 61.0, "atr_pct": 2.1,
    "status": "watch", "gemini_verdict": "aprovado", "gemini_risk": "baixo",
    "gemini_summary": "Sem eventos de risco relevantes nos últimos 14 dias.",
    "gemini_events": [], "reasons": ["EMA50 4H acima da EMA200 (+7)"]}]}}
```

**signal**
```json
{"type": "signal", "payload": {
  "symbol": "SOLUSDT", "setup": "pullback_tendencia", "entry": 151.8,
  "stop": 147.9, "tp1": 157.65, "tp2": 163.5, "rr": 3.0, "score": 78,
  "status": "pendente", "reason": "Pullback na EMA20 1H com engolfo de alta",
  "order_link_id": "SOLUSDT-pullback_tendencia-202610111300"}}
```

**trade_open / trade_update / trade_close** (upsert por `order_link_id`)
```json
{"type": "trade_close", "payload": {
  "order_link_id": "SOLUSDT-pullback_tendencia-202610111300",
  "symbol": "SOLUSDT", "setup": "pullback_tendencia", "status": "closed",
  "opened_at": "2026-10-11T13:02:10Z", "closed_at": "2026-10-12T02:41:00Z",
  "entry_price": 151.8, "qty": 2.56, "qty_open": 0,
  "initial_stop": 147.9, "current_stop": 151.95, "tp1": 157.65, "tp2": 163.5,
  "tp1_hit": true, "exit_price": 160.2, "pnl_usdt": 18.4, "pnl_pct": 4.73,
  "r_multiple": 1.84, "fees_usdt": 0.79, "exit_reason": "trailing",
  "risk_usdt": 10.0, "gemini_summary": "aprovado — sem eventos"}}
```

**trade_event**
```json
{"type": "trade_event", "payload": {
  "order_link_id": "SOLUSDT-pullback_tendencia-202610111300",
  "ts": "2026-10-11T18:20:00Z", "type": "stop_movido", "price": 151.95,
  "qty": 1.28, "message": "TP1 atingido; stop movido para breakeven"}}
```

**equity** (a cada 15 min)
```json
{"type": "equity", "payload": {"ts": "2026-10-11T13:15:00Z",
  "equity_usdt": 1004.2, "free_usdt": 620.0, "exposure_usdt": 384.2}}
```

**log** (aceita um item ou uma lista `logs`)
```json
{"type": "log", "payload": {"logs": [
  {"ts": "2026-10-11T13:00:05Z", "level": "warn", "component": "bybit",
   "symbol": null, "message": "retCode 10006 (limite de requisições); aguardando 2s",
   "data": {"endpoint": "/v5/market/kline"}}]}}
```

**commands_pull**: retorna os comandos pendentes do painel (`pause`/`resume`)
```json
{"type": "commands_pull", "payload": {}}
```

**command_ack**
```json
{"type": "command_ack", "payload": {"id": "<uuid do comando>",
  "status": "done", "note": "Robô pausado: novas entradas bloqueadas"}}
```

### Cliente Python de referência (`reporting/dashboard_client.py`)

```python
import os
import time

import httpx


class DashboardClient:
    """Envia eventos ao painel. Nunca deixa uma falha do painel travar o robô."""

    def __init__(self, ingest_url: str, token: str, timeout: float = 10.0):
        self._url = ingest_url
        self._headers = {"x-bot-token": token, "Content-Type": "application/json"}
        self._http = httpx.Client(timeout=timeout)

    def send(self, type_: str, payload: dict, retries: int = 3) -> dict | None:
        for attempt in range(retries):
            try:
                r = self._http.post(self._url, headers=self._headers,
                                    json={"type": type_, "payload": payload})
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (400, 401):
                    # erro de contrato/token: não adianta repetir
                    return None
            except httpx.HTTPError:
                pass
            time.sleep(2 ** attempt)
        return None  # o robô deve enfileirar localmente e reenviar depois


# exemplo
# client = DashboardClient(os.environ["DASHBOARD_INGEST_URL"], os.environ["BOT_INGEST_TOKEN"])
# client.send("heartbeat", {"mode": "paper", "paused": False, "kill_switch": False})
```
