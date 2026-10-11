# 01 — Checklist completo: tudo o que precisa ser feito

Marque cada item conforme for concluindo. A ordem segue o
[plano de execução](02_PLANO_DE_EXECUCAO.md).

## A. Contas e segurança (antes de qualquer código)

### Bybit
- [ ] Conta Bybit com **KYC** concluído e **2FA** (Google Authenticator) ativo.
- [ ] Criar uma **subconta exclusiva para o robô** (isola o capital: o robô nunca enxerga o resto do seu dinheiro).
- [ ] Transferir para a subconta **só o capital que você aceita perder** na fase de testes.
- [ ] Ativar o **Demo Trading** da Bybit e criar uma chave de API da conta demo (para as Fases 1–8).
- [ ] Criar a chave de API **real** da subconta somente na Fase 9, com:
  - [ ] Permissões: **Leitura** + **Negociação Spot**. **Nunca** marcar *Saque/Withdraw* nem *Transferência*.
  - [ ] **Restrição de IP** = IP estático da VM do Google Cloud (chaves sem IP fixo expiram em ~90 dias e são mais perigosas).
- [ ] Guardar as chaves **somente** no Google Secret Manager (nunca em código, prompt, chat, planilha ou print).
- [ ] Chave **separada e somente leitura** caso algum dia o painel precise consultar saldo diretamente.

### Google
- [ ] Projeto no **Google Cloud** com faturamento ativo.
- [ ] **Alerta de orçamento** (ex.: US$ 30/mês) para não ter surpresa na fatura.
- [ ] Acesso ao **Gemini**: Vertex AI habilitado no projeto (recomendado) **ou** chave do Google AI Studio.
- [ ] Ferramenta onde o Gemini vai **escrever o código**: Gemini CLI, Gemini Code Assist (VS Code), Google AI Studio ou Antigravity — use os prompts de [04_PROMPTS_GOOGLE.md](04_PROMPTS_GOOGLE.md).
- [ ] Conta de serviço da VM com papéis mínimos: `Secret Manager Secret Accessor`, `Logs Writer`, `Vertex AI User`.

### Painel e alertas
- [ ] Painel Lovable criado (ver [05_DASHBOARD_E_INTEGRACAO.md](05_DASHBOARD_E_INTEGRACAO.md)) e **você** cadastrado como primeiro usuário (dono).
- [ ] Secret `BOT_INGEST_TOKEN` criado no Lovable Cloud (gere um valor aleatório longo) e o **mesmo** valor salvo no Google Secret Manager.
- [ ] Bot do **Telegram** criado no @BotFather + `chat_id` anotado (alertas no celular).

## B. Infraestrutura (Google Cloud)

- [ ] VM **Compute Engine** `e2-small`, Ubuntu LTS, em região **fora dos EUA** — `southamerica-east1` (São Paulo) ou `asia-southeast1` (Singapura, mais perto dos servidores da Bybit). **A Bybit bloqueia IPs dos EUA (erro 403).**
- [ ] **IP externo estático** reservado e anexado à VM.
- [ ] Teste de conectividade da VM: `curl https://api.bybit.com/v5/market/time` deve responder **200**.
- [ ] Firewall: nenhuma porta de entrada aberta além de SSH via **IAP**.
- [ ] Docker + `docker compose` com `restart: always` (ou serviço `systemd`).
- [ ] **Ops Agent** instalado (logs no Cloud Logging) + alerta se a VM parar.
- [ ] Backup diário do banco local (SQLite) para um bucket do **Cloud Storage**.
- [ ] Relógio sincronizado (NTP) — a Bybit rejeita requisições com timestamp fora da janela.

## C. Código do robô (gerado pelo Gemini, revisado por você)

- [ ] Estrutura do projeto em Python 3.12 (ver prompt mestre).
- [ ] Configuração via `config.yaml` + validação (pydantic) — nada de número mágico no código.
- [ ] **Conector Bybit V5**: assinatura HMAC, `recv_window`, sincronização de horário, retries com backoff, respeito aos limites de requisição, tratamento de `retCode`.
- [ ] Regras do instrumento (`tickSize`, `basePrecision`, `minOrderQty`, `minOrderAmt`).
- [ ] Coleta de dados: tickers, klines (1D/4H/1H/15m), orderbook, open interest, funding, long/short ratio — com cache.
- [ ] Indicadores (EMA, RSI, ATR, ADX/DI, MACD, Bollinger + largura, OBV, CMF) com **testes** contra valores de referência.
- [ ] Filtro de universo, regime de mercado e **score 0–100** (ver [03_ESTRATEGIA.md](03_ESTRATEGIA.md)).
- [ ] Gatilhos de entrada: `pullback_tendencia`, `rompimento_compressao`, `ote_fibo`.
- [ ] **Analista Gemini** com saída JSON validada, cache, timeout e regra de falha.
- [ ] **Motor de risco** (tamanho de posição, limites diários/semanais, kill switch, setores).
- [ ] **Executor**: ordem limite com `orderLinkId` idempotente, stop no servidor logo após o fill, TP1 parcial, breakeven, trailing, stop de tempo, invalidação.
- [ ] **Broker simulado** (paper) com a mesma interface do broker real.
- [ ] **Reconciliação** ao iniciar: ler ordens abertas, saldos e execuções na Bybit e reconstruir o estado (o robô pode reiniciar a qualquer momento sem duplicar ordens).
- [ ] Comandos do painel (`pause`/`resume`) lidos periodicamente.
- [ ] Envio de dados ao painel (`bot-ingest`) + alertas no Telegram.
- [ ] Logs estruturados (JSON) com nível, componente e símbolo.
- [ ] Testes automatizados (`pytest`) para indicadores, score, setups, risco e executor (com Bybit simulada).

## D. Validação (nada vai para conta real sem passar aqui)

- [ ] **Backtest** de ≥ 12 meses, incluindo período de queda, com taxas e slippage.
- [ ] **Walk-forward** (otimiza em um período, testa no seguinte) — resultado positivo fora da amostra.
- [ ] Critérios mínimos: ≥ 150 trades, profit factor ≥ 1,3, expectância ≥ 0,15 R, drawdown máx. ≤ 20 %, nenhum trade responsável por > 25 % do lucro.
- [ ] **Paper trading** interno por ≥ 2 semanas.
- [ ] **Bybit Demo Trading** por ≥ 4 semanas e ≥ 30 trades, com métricas dentro de ±30 % do backtest.
- [ ] Testes de falha na conta demo: derrubar o robô com posição aberta, cortar a internet, reiniciar a VM, chave inválida, saldo insuficiente, par deslistado.
- [ ] **Zero** operações sem stop no servidor durante todo o forward test.

## E. Conta real (Fase 9)

- [ ] Chave real com IP fixo e sem permissão de saque (item A).
- [ ] Começar com **risco de 0,25–0,5 %** por trade e capital pequeno.
- [ ] Aumentar capital no máximo **+50 % por mês**, e só se os números continuarem consistentes.
- [ ] Planilha/registro de todas as operações para a **declaração à Receita Federal** (consulte um contador sobre a tributação de cripto vigente).

## F. Rotina de operação

- [ ] Diário: olhar o painel (status ONLINE, posições, alertas).
- [ ] Semanal: relatório (acerto, R médio, drawdown, resultado por setup/score/veredito do Gemini).
- [ ] Mensal: revisão de parâmetros — **uma** mudança por vez, sempre validada em backtest + demo antes de ir para o real.
- [ ] Trimestral: trocar as chaves de API, revisar permissões e custos do Google Cloud.
