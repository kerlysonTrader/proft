# Robô Scanner Bybit + Google (Gemini / Google Cloud)

Estrutura completa para criar uma automação que roda na sua conta da **Bybit**
e busca continuamente as moedas com maior probabilidade de alta, avalia cada
uma com critério e procura o melhor ponto de entrada — usando o **Google**
como robô: o **Gemini** escreve o código e atua como analista de risco, e o
**Google Cloud** executa o robô 24/7.

> ⚠️ **Aviso**: nenhuma automação garante lucro. Este projeto busca uma
> vantagem estatística com risco controlado e só deve operar dinheiro real
> depois de passar pelos portões de validação do plano. Opere apenas capital
> que você aceita perder. Não é recomendação de investimento.

## Documentos (leia nesta ordem)

| # | Arquivo | Para quê |
|---|---|---|
| 1 | [01_CHECKLIST.md](01_CHECKLIST.md) | Tudo o que precisa ser feito (contas, segurança, infra, código, validação, operação) |
| 2 | [02_PLANO_DE_EXECUCAO.md](02_PLANO_DE_EXECUCAO.md) | Fases, prazos, portões de aprovação, custos e riscos |
| 3 | [03_ESTRATEGIA.md](03_ESTRATEGIA.md) | Especificação da estratégia: universo, regime, score 0–100, setups de entrada, veto do Gemini, risco e saídas |
| 4 | [04_PROMPTS_GOOGLE.md](04_PROMPTS_GOOGLE.md) | **Prompt mestre** + prompts de cada fase para o Gemini construir o robô + prompt do analista Gemini em tempo real + prompt de revisão semanal |
| 5 | [05_DASHBOARD_E_INTEGRACAO.md](05_DASHBOARD_E_INTEGRACAO.md) | Painel de acompanhamento (Lovable) e contrato da API robô → painel |
| 6 | [06_DADOS_ONCHAIN.md](06_DADOS_ONCHAIN.md) | Camada on-chain opcional (Coinversa/Hyperliquid + Liquid): regras, API, validação em modo sombra |
| — | [config.example.yaml](config.example.yaml) | Todos os parâmetros ajustáveis |

## Onde acompanhar

- **Painel (dashboard) em tempo real**: https://bybit-trader-view.lovable.app
  (editor: https://lovable.dev/projects/2f34128e-4585-4e6d-9fa8-1a0c53ee3e9d)
  (detalhes e primeiros passos em [05_DASHBOARD_E_INTEGRACAO.md](05_DASHBOARD_E_INTEGRACAO.md)).
- **Central do projeto no Notion** (tarefas por fase, status e critérios de
  pronto): página privada "Robô Scanner Bybit + Google — Central do Projeto".

## Arquitetura

```
┌────────────────────── Google Cloud (região fora dos EUA, IP estático) ───────────────────────┐
│ VM Compute Engine (Docker, reinício automático)                                               │
│                                                                                               │
│  Conector Bybit V5 ──► Scanner (universo → regime BTC → score 0-100) ──► Gatilhos de entrada  │
│     ▲   (REST + WS)                                                           │               │
│     │                                                                         ▼               │
│     │                                         Analista Gemini (Vertex AI + Google Search)     │
│     │                                         → só pode VETAR ou REDUZIR o risco              │
│     │                                                                         │               │
│     └──── Executor (ordem limite, stop no servidor, TP1, breakeven, trailing) ◄── Motor de risco │
│                                                                                               │
│  Secret Manager (chaves) · SQLite + backup Cloud Storage · Cloud Logging                      │
└───────────────────────────────┬──────────────────────────────────────┬────────────────────────┘
                                │ HTTPS (bot-ingest)                   │
                                ▼                                      ▼
              Painel Lovable/Supabase (tempo real)              Telegram (alertas)
              + cotações ao vivo direto do WebSocket da Bybit
```

## Decisões principais

- **Spot, só compra, sem alavancagem** no início (sem risco de liquidação).
- **Código decide, IA opina**: entrada, stop e tamanho são regras
  determinísticas e testáveis; o Gemini só veta ou reduz.
- **Stop sempre no servidor da Bybit**: a posição fica protegida mesmo se o
  robô cair.
- **Subconta exclusiva**, chave **sem permissão de saque**, **IP fixo** da VM.
- **VM fora dos EUA**: a Bybit retorna 403 para IPs americanos.
- **Dados on-chain da Hyperliquid (Coinversa)** como camada opcional que só
  reduz risco, começa em modo sombra e nunca impede o robô de funcionar.
- **Validação em 3 etapas** antes do dinheiro real: backtest + walk-forward →
  paper → Bybit Demo Trading.
- Reaproveita a lógica OTE/Fibonacci + Order Block do EA MQL5 deste
  repositório (`MQL5/Experts/ICT_FiboEntry_EA.mq5`) como um dos setups.
