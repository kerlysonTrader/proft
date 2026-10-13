# Estudo: moedas recém-lançadas e memecoins realmente multiplicam o capital?

**Data:** 12/10/2026 · **Tipo:** estudo com dados públicos reais (sem chave de API, sem ordens, sem custo) · **Script:** `src/bot/tools/estudo_lancamentos.py` · **Dados brutos:** `data/estudo_lancamentos/`

> Tudo que está marcado como **medição própria** foi calculado por este script com dados baixados na hora. O que está marcado como **citação** vem de estudos de terceiros (com link) e não foi refeito aqui.

---

## 1. Resposta curta

**Não: no conjunto, quem compra lançamentos perde dinheiro. A chance de multiplicar existe, mas é pequena e quase sempre passageira.** O que a sensação "dá para multiplicar pouco capital" capta é real, só que é a ponta de uma distribuição muito assimétrica: poucas moedas sobem muito, a maioria perde metade ou mais.

Números principais (medição própria, 369 perpétuos e 200 pares spot lançados na Bybit entre out/2024 e out/2026; entrada realista = fechamento das primeiras 24 h):

- **Mediana do resultado: −29% em 30 dias, −51% em 90 dias, −61% em 180 dias.** Em 180 dias, 87% das moedas estavam abaixo do preço de entrada e 63% tinham perdido 50% ou mais.
- **Só 6% estavam em 2× ou mais ao fim de 30 dias** (4% aos 90 dias, 5% aos 180 dias).
- **Mas 21% "tocaram" 2× em algum momento dos primeiros 30 dias** (36% em 180 dias; 5× em 10% e 10× em 4,6%). A diferença entre "tocou" e "estava lá no fim" é o ponto central: quase tudo que sobe devolve a alta. Quem não vende exatamente perto do topo fica sem o ganho.
- **US$ 100 em cada lançamento** (com taxas) e segurar: **−US$ 12 por lançamento em 30 dias (−12%) e −US$ 29,50 em 90 dias**; soma de **−US$ 4.358** em 364 operações. Mesmo com alvo de +100% automático, o resultado médio continua negativo (−US$ 6,60 em 30 dias).
- **Memecoins (56 perpétuos, 23 spot) não foram melhores:** mediana pior (−41% em 30 dias contra −27% das demais) e média parecida (−11% × −12%). A amostra é pequena demais para afirmar que sejam diferentes.
- **Com alavancagem a história piora:** comprando 5×, 84% das moedas teriam liquidado a posição nos primeiros 30 dias.
- **O espelho vendido (short) rendeu em média +US$ 6,40 por US$ 100 em 30 dias (+US$ 4,20 depois do funding), mas o ganho veio quase todo de um único semestre (2025-S1).** Fora dele ficou perto de zero. Não é uma vantagem comprovada.
- **Memecoins de launchpad (pump.fun etc.) são muito piores que a Bybit:** ver seção 4. Nas fontes citadas, ~98,6% dos tokens da pump.fun colapsam e só ~0,6% "graduam"; na medição própria, na coleta-piloto (20 pools novos com cerca de 1 h de vida), 89% dos tokens da pump.fun avaliados pararam de negociar em minutos (amostra pequena demais para medir retorno).

---

## 2. O que foi medido (em linguagem simples)

**Amostra da Bybit (medição própria).** API pública V5, sem chave.
- **Perpétuos USDT** (`instruments-info`, categoria `linear`): todos que estrearam entre 12/10/2024 e 12/10/2026, **inclusive os já deslistados** (`status=Closed`), para reduzir o viés de sobrevivência. Excluí 274 contratos que são ações, ETFs, commodities ou forex (campo `symbolType`) e 1 contrato (LAYER) que foi cancelado 4 h depois de abrir, sem negociação.
- **Spot USDT:** a Bybit não informa a data de lançamento do spot, então usei a **primeira vela diária disponível**. Varri 889 pares candidatos (390 ativos hoje + as moedas de todos os perpétuos, para recuperar spots deslistados que ainda têm histórico). Spots deslistados de moedas que **não** tiveram perpétuo não aparecem na API, e por isso estão faltando.
- **Velas de 1 hora** de cada símbolo, de 1 h antes do lançamento até 190 dias depois, mais o **histórico de funding** dos perpétuos.

**Três formas de entrar.** Foram usadas porque a primeira vela dos lançamentos é enganosa:
- **A — abertura da 1ª vela:** o primeiro preço negociado. É o que você pediu como referência, mas é praticamente inalcançável (volume mediano da 1ª hora nos perpétuos: US$ 0,5 milhão, e US$ 29 mil no pior decil).
- **H — fechamento da 1ª hora** (usado no spot): no spot da Bybit o "preço de abertura" da 1ª vela é um preço-âncora do leilão de listagem (ex.: o IP abriu a US$ 0,10 e fechou a 1ª hora a US$ 2,28). Comprar na abertura é impossível, e as contas com ela mostram +174% de mediana em 1 dia, só por esse artefato (tabela na seção 3.5).
- **B — fechamento das primeiras 24 h:** o que um trader que viu o lançamento e decidiu comprar no dia seguinte realmente consegue. **É a entrada de referência deste relatório.**

**Resultados.** Para cada moeda: retorno em 1, 7, 30, 90 e 180 dias, maior alta e maior queda no período e se tocou 2×, 5× e 10×. Moeda que foi deslistada antes do fim da janela "sai" no último preço negociado. Janela que ainda não terminou para uma moeda viva fica de fora (por isso o `n` diminui nas janelas longas).

**Simulações.** US$ 100 por lançamento, sem alavancagem, taxa de 0,1% por lado no spot e 0,055% por lado no perpétuo. O short usa US$ 100 de margem para US$ 100 de posição (1×); "com stop" sai se o preço subir 50% (na abertura da vela, se houver gap). Sem stop, a posição é liquidada se o preço quase dobrar (+99,5%). Ordens executadas ao preço exato do alvo ou do stop, sem derrapagem (otimista).

**Estatística.** `IC95%` é a faixa em que a média verdadeira provavelmente está (bootstrap com 3.000 sorteios); para proporções usei o intervalo de Wilson. Intervalos que incluem zero significam que **não dá para distinguir de "nada"**.

**Memecoins.** Marquei pelo símbolo cruzado com a categoria "meme-token" da CoinGecko (API pública, ~6.600 moedas), aceitando só moedas com ranking ≤ 5.000 (símbolos repetem entre projetos), com revisão manual de colisões conhecidas e inclusão manual de memes que a CoinGecko não tem. É aproximado; a lista final está no apêndice.

**"Lançamento aparente".** Um perpétuo novo na Bybit nem sempre é moeda nova (a Bybit também lista moedas antigas). Marquei como **"já negociava antes"** as moedas com primeira negociação na Binance (spot) ou no spot da Bybit mais de 30 dias antes: 46 perpétuos e 17 pares spot. As outras são "lançamento aparente" (não verifiquei outras corretoras nem DEX, então pode haver moedas antigas ali).

### 2.1 Amostra

| Amostra | Moedas | Ainda negociando | Deslistadas/encerradas | Memecoins | Não memes | Lançamento aparente | Já negociava antes (>30 d) |
|---|---|---|---|---|---|---|---|
| Perpétuos USDT | 369 | 273 | 96 | 56 | 313 | 323 | 46 |
| Spot USDT | 200 | 169 | 31 | 23 | 177 | 183 | 17 |

---

## 3. Bybit: resultados (medição própria)

### 3.1 Perpétuos — comprando no fechamento das primeiras 24 h (entrada B)

`n` = nº de moedas com a janela completa. As moedas deslistadas entram com o último preço.

| Janela | n | Mediana | Média [IC95%] | P10 | P25 | P75 | P90 | % abaixo da entrada | % perdeu 50% ou mais | % em 2× ou mais no fim | % saiu por deslistagem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 d | 369 | -14% | -1% [-9%; +12%] | -44% | -30% | +4% | +39% | 70% | 5% | 3% | 1% |
| 30 d | 364 | -29% | -12% [-18%; -4%] | -68% | -54% | +7% | +68% | 72% | 28% | 6% | 2% |
| 90 d | 350 | -51% | -29% [-39%; -19%] | -84% | -73% | -16% | +33% | 82% | 52% | 4% | 7% |
| 180 d | 327 | -61% | -38% [-47%; -28%] | -89% | -80% | -29% | +18% | 87% | 63% | 5% | 12% |

**Leitura:** o resultado típico é perda em todas as janelas e ela só aumenta com o tempo. A média (−12% em 30 dias, −38% em 180 dias) é menos ruim que a mediana porque poucas moedas sobem muito, mas mesmo assim o intervalo de confiança da média fica abaixo de zero. Só 3% a 6% das moedas estavam em 2× ou mais no fim de qualquer janela.

### 3.2 Perpétuos — comprando na abertura da 1ª vela (entrada A, só referência)

| Janela | n | Mediana | Média [IC95%] | P10 | P25 | P75 | P90 | % abaixo da entrada | % perdeu 50% ou mais | % em 2× ou mais no fim | % saiu por deslistagem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 d | 369 | -3% | +1% [-2%; +4%] | -29% | -15% | +12% | +36% | 58% | 1% | 1% | 0% |
| 7 d | 369 | -13% | +1% [-7%; +10%] | -49% | -35% | +13% | +53% | 64% | 10% | 5% | 1% |
| 30 d | 364 | -33% | -12% [-18%; -5%] | -71% | -56% | +11% | +74% | 69% | 32% | 6% | 2% |
| 90 d | 350 | -53% | -27% [-37%; -15%] | -86% | -76% | -11% | +38% | 79% | 53% | 5% | 7% |
| 180 d | 327 | -63% | -38% [-47%; -28%] | -90% | -82% | -28% | +20% | 85% | 60% | 5% | 12% |

Nos perpétuos a abertura não é muito diferente da entrada B (a mediana de B sobre A é −3%), então a conclusão não muda. Para o spot ela é enganosa — ver 3.5.

### 3.3 Quanto chegou a 2×, 5× e 10× "em algum momento"

Entre colchetes, o intervalo de confiança (Wilson) da proporção; entre parênteses, o número de moedas.

**Entrada B (24 h):**

| Dentro de | n | Tocou 2× | Tocou 5× | Tocou 10× |
|---|---|---|---|---|
| 30 d | 364 | 20.9% (76) [17%-25%] | 3.8% (14) [2%-6%] | 1.1% (4) [0%-3%] |
| 90 d | 350 | 31.7% (111) [27%-37%] | 7.1% (25) [5%-10%] | 3.1% (11) [2%-6%] |
| 180 d | 327 | 36.1% (118) [31%-41%] | 10.1% (33) [7%-14%] | 4.6% (15) [3%-7%] |

**Entrada A (abertura):**

| Dentro de | n | Tocou 2× | Tocou 5× | Tocou 10× |
|---|---|---|---|---|
| 30 d | 364 | 24.7% (90) [21%-29%] | 4.1% (15) [3%-7%] | 1.1% (4) [0%-3%] |
| 90 d | 350 | 35.1% (123) [30%-40%] | 7.4% (26) [5%-11%] | 2.9% (10) [2%-5%] |
| 180 d | 327 | 40.1% (131) [35%-45%] | 9.5% (31) [7%-13%] | 4.9% (16) [3%-8%] |

**Leitura:** a multiplicação existe: uma em cada cinco moedas tocou 2× nos primeiros 30 dias e cerca de 1 em 20 tocou 10× em seis meses (RAVE, COAI e AIA chegaram a mais de 45×). Só que ao fim da mesma janela apenas 4% a 6% ainda estavam em 2× ou mais. Quem comprou e segurou capturou muito pouco desse "tocou".

### 3.4 Maior alta e maior queda nos primeiros 30 dias (entrada B)

| Primeiros 30 dias | n | P10 | P25 | Mediana | P75 | P90 |
|---|---|---|---|---|---|---|
| Máxima alta (high/entrada − 1) | 364 | +3% | +9% | +27% | +81% | +206% |
| Máxima queda (low/entrada − 1) | 364 | -76% | -64% | -47% | -29% | -13% |

A moeda mediana subiu no máximo +27% e, em algum momento, já estava 47% abaixo da entrada. Por isso a alavancagem é tão perigosa (seção 3.8).

### 3.5 Pares spot

A "abertura" do spot é artefato. Esta é a tabela que mostra o problema (entrada A, **não usar**):

| Janela | n | Mediana | Média [IC95%] | P10 | P25 | P75 | P90 | % abaixo da entrada | % perdeu 50% ou mais | % em 2× ou mais no fim | % saiu por deslistagem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 d | 200 | +174% | +410% [+322%; +512%] | +6% | +46% | +476% | +1009% | 4% | 0% | 60% | 0% |
| 7 d | 200 | +148% | +380% [+298%; +475%] | -0% | +27% | +428% | +915% | 12% | 0% | 58% | 0% |
| 30 d | 199 | +76% | +332% [+247%; +426%] | -25% | +9% | +377% | +917% | 18% | 4% | 46% | 0% |
| 90 d | 194 | +38% | +242% [+168%; +321%] | -58% | -24% | +245% | +737% | 34% | 13% | 38% | 1% |
| 180 d | 176 | +18% | +257% [+131%; +416%] | -64% | -38% | +212% | +551% | 40% | 22% | 34% | 3% |

Entrada realista no spot, **H** (fechamento da 1ª hora):

| Janela | n | Mediana | Média [IC95%] | P10 | P25 | P75 | P90 | % abaixo da entrada | % perdeu 50% ou mais | % em 2× ou mais no fim | % saiu por deslistagem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 d | 200 | -1% | +7% [+1%; +14%] | -30% | -15% | +9% | +48% | 55% | 1% | 3% | 0% |
| 7 d | 200 | -8% | +4% [-4%; +14%] | -48% | -28% | +10% | +49% | 64% | 9% | 6% | 0% |
| 30 d | 199 | -25% | -4% [-16%; +9%] | -64% | -52% | +4% | +58% | 70% | 28% | 7% | 0% |
| 90 d | 194 | -44% | -23% [-35%; -8%] | -85% | -74% | -0% | +44% | 75% | 46% | 6% | 1% |
| 180 d | 176 | -63% | -33% [-44%; -19%] | -87% | -79% | -9% | +34% | 79% | 58% | 5% | 3% |

Entrada **B** (24 h):

| Janela | n | Mediana | Média [IC95%] | P10 | P25 | P75 | P90 | % abaixo da entrada | % perdeu 50% ou mais | % em 2× ou mais no fim | % saiu por deslistagem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 d | 200 | -12% | -2% [-9%; +4%] | -42% | -29% | +4% | +42% | 68% | 4% | 5% | 0% |
| 30 d | 199 | -26% | -11% [-19%; -2%] | -67% | -47% | +2% | +63% | 71% | 23% | 6% | 0% |
| 90 d | 194 | -45% | -30% [-38%; -22%] | -84% | -73% | -2% | +45% | 78% | 45% | 2% | 1% |
| 180 d | 176 | -63% | -35% [-45%; -22%] | -88% | -79% | -18% | +38% | 80% | 60% | 4% | 3% |

Tocou 2×/5×/10× (entrada H):

| Dentro de | n | Tocou 2× | Tocou 5× | Tocou 10× |
|---|---|---|---|---|
| 30 d | 199 | 22.1% (44) [17%-28%] | 7.5% (15) [5%-12%] | 3.0% (6) [1%-6%] |
| 90 d | 194 | 29.9% (58) [24%-37%] | 8.8% (17) [6%-14%] | 4.1% (8) [2%-8%] |
| 180 d | 176 | 32.4% (57) [26%-40%] | 11.4% (20) [7%-17%] | 5.7% (10) [3%-10%] |

Tocou 2×/5×/10× (entrada B):

| Dentro de | n | Tocou 2× | Tocou 5× | Tocou 10× |
|---|---|---|---|---|
| 30 d | 199 | 16.1% (32) [12%-22%] | 3.5% (7) [2%-7%] | 0.0% (0) [0%-2%] |
| 90 d | 194 | 22.7% (44) [17%-29%] | 5.2% (10) [3%-9%] | 0.5% (1) [0%-3%] |
| 180 d | 176 | 25.6% (45) [20%-32%] | 7.4% (13) [4%-12%] | 2.3% (4) [1%-6%] |

**Leitura:** igual aos perpétuos. Mediana de −25% em 30 dias e −63% em 180 dias; entre 22% e 32% tocam 2×, mas só 5% a 7% estão em 2× ou mais no fim.

### 3.6 Memecoins × não memes, e lançamentos novos × moedas que já existiam

Perpétuos, 30 dias (entrada B):

| Grupo | n | Mediana | Média [IC95%] | % abaixo da entrada | % em 2×+ no fim | % tocou 2× | % tocou 5× |
|---|---|---|---|---|---|---|---|
| Todas | 364 | -29% | -12% [-18%; -4%] | 72% | 6% | 21% | 4% |
| Memecoins | 56 | -41% | -11% [-29%; +10%] | 70% | 9% | 27% | 5% |
| Não memes | 308 | -27% | -12% [-19%; -4%] | 72% | 5% | 20% | 4% |
| Lançamento aparente (sem negociação prévia conhecida) | 319 | -31% | -13% [-20%; -5%] | 72% | 6% | 23% | 4% |
| Já negociava antes | 45 | -22% | -6% [-21%; +12%] | 69% | 4% | 9% | 4% |
| Memecoins + lançamento aparente | 54 | -41% | -14% [-32%; +4%] | 70% | 7% | 26% | 4% |
| Não memes + lançamento aparente | 265 | -30% | -12% [-21%; -3%] | 73% | 6% | 22% | 4% |

Perpétuos, 90 dias (entrada B):

| Grupo | n | Mediana | Média [IC95%] | % abaixo da entrada | % em 2×+ no fim | % tocou 2× | % tocou 5× |
|---|---|---|---|---|---|---|---|
| Todas | 350 | -51% | -29% [-39%; -19%] | 82% | 4% | 32% | 7% |
| Memecoins | 53 | -64% | -30% [-56%; +9%] | 81% | 4% | 34% | 9% |
| Não memes | 297 | -49% | -29% [-38%; -19%] | 82% | 4% | 31% | 7% |
| Lançamento aparente (sem negociação prévia conhecida) | 306 | -53% | -30% [-39%; -18%] | 82% | 4% | 34% | 7% |
| Já negociava antes | 44 | -44% | -28% [-43%; -12%] | 84% | 5% | 18% | 7% |
| Memecoins + lançamento aparente | 51 | -64% | -34% [-59%; +4%] | 82% | 2% | 33% | 8% |
| Não memes + lançamento aparente | 255 | -51% | -29% [-38%; -17%] | 82% | 4% | 34% | 7% |

Spot, 30 dias (entrada H):

| Grupo | n | Mediana | Média [IC95%] | % abaixo da entrada | % em 2×+ no fim | % tocou 2× | % tocou 5× |
|---|---|---|---|---|---|---|---|
| Todas | 199 | -25% | -4% [-16%; +9%] | 70% | 7% | 22% | 8% |
| Memecoins | 23 | -43% | -18% [-48%; +27%] | 87% | 4% | 17% | 4% |
| Não memes | 176 | -23% | -2% [-14%; +12%] | 68% | 7% | 23% | 8% |
| Lançamento aparente (sem negociação prévia conhecida) | 182 | -31% | -4% [-16%; +10%] | 71% | 8% | 24% | 8% |
| Já negociava antes | 17 | -9% | -9% [-19%; +2%] | 59% | 0% | 0% | 0% |
| Memecoins + lançamento aparente | 21 | -46% | -17% [-49%; +34%] | 86% | 5% | 19% | 5% |
| Não memes + lançamento aparente | 161 | -25% | -2% [-16%; +13%] | 69% | 8% | 25% | 9% |

**Leitura:** as memecoins têm mediana pior (−41% contra −27% em 30 dias nos perpétuos; −43% contra −23% no spot) e uma cauda um pouco maior (27% tocam 2× contra 20%), mas as médias são praticamente iguais e **os intervalos são enormes** (56 memes nos perpétuos, 23 no spot). Não há base para dizer que memecoins "multiplicam mais". Os lançamentos aparentes também não foram melhores que as moedas que já existiam: o que existiu foi mais variância, não mais retorno.

### 3.7 Simulação: US$ 100 em cada lançamento, com taxas

Perpétuos (taxa 0,055%/lado; "A" = abertura, "B" = fech. 24 h):

| Cenário | n | Soma US$ | Média US$/trade [IC95%] | Mediana | % lucrativos | Melhor | Pior | Média sem os 3 melhores |
|---|---|---|---|---|---|---|---|---|
| Comprar na abertura da 1ª vela, segurar 30 d | 364 | -4,326 | -11.9 [-18.5; -4.6] | -33.0 | 31% | +359 | -94 | -14.4 |
| VENDER a descoberto na abertura da 1ª vela, 30 d, SEM stop | 364 | +897 | +2.5 [-4.3; +9.0] | +28.1 | 63% | +94 | -100 | +1.7 |
| VENDER a descoberto na abertura da 1ª vela, 30 d, stop +50% | 364 | +1,185 | +3.3 [-1.9; +8.4] | +12.6 | 52% | +94 | -50 | +2.5 |
| Comprar na abertura da 1ª vela, segurar 90 d | 350 | -9,430 | -26.9 [-36.9; -15.0] | -53.5 | 21% | +1,048 | -98 | -34.4 |
| VENDER a descoberto na abertura da 1ª vela, 90 d, SEM stop | 350 | +423 | +1.2 [-7.3; +9.2] | +36.2 | 59% | +98 | -100 | +0.4 |
| VENDER a descoberto na abertura da 1ª vela, 90 d, stop +50% | 350 | +1,580 | +4.5 [-1.7; +10.5] | -50.1 | 47% | +98 | -50 | +3.7 |
| Comprar no fech. de 24 h, segurar 30 d | 364 | -4,358 | -12.0 [-18.6; -4.3] | -29.1 | 27% | +471 | -94 | -15.4 |
| Comprar no fech. de 24 h, alvo +100% ou até 30 d | 364 | -2,404 | -6.6 [-12.9; -0.3] | -27.0 | 31% | +100 | -94 | -7.5 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 30 d | 364 | -2,489 | -6.8 [-12.4; -1.1] | -32.3 | 29% | +100 | -50 | -7.7 |
| VENDER a descoberto no fech. de 24 h, 30 d, SEM stop | 364 | +2,340 | +6.4 [+0.1; +12.7] | +26.8 | 68% | +93 | -100 | +5.7 |
| VENDER a descoberto no fech. de 24 h, 30 d, stop +50% | 364 | +2,830 | +7.8 [+2.9; +12.6] | +23.1 | 60% | +93 | -50 | +7.1 |
| Comprar no fech. de 24 h, segurar 90 d | 350 | -10,323 | -29.5 [-38.6; -19.1] | -51.2 | 18% | +906 | -98 | -35.8 |
| Comprar no fech. de 24 h, alvo +100% ou até 90 d | 350 | -1,775 | -5.1 [-12.8; +2.8] | -41.3 | 36% | +100 | -98 | -6.0 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 90 d | 350 | -2,234 | -6.4 [-12.7; +0.3] | -50.1 | 29% | +100 | -50 | -7.3 |
| VENDER a descoberto no fech. de 24 h, 90 d, SEM stop | 350 | +1,719 | +4.9 [-3.0; +12.6] | +41.2 | 63% | +98 | -100 | +4.1 |
| VENDER a descoberto no fech. de 24 h, 90 d, stop +50% | 350 | +3,293 | +9.4 [+3.6; +15.5] | +20.4 | 53% | +98 | -50 | +8.7 |

Perpétuos só memecoins:

| Cenário | n | Soma US$ | Média US$/trade [IC95%] | Mediana | % lucrativos | Melhor | Pior | Média sem os 3 melhores |
|---|---|---|---|---|---|---|---|---|
| Comprar na abertura da 1ª vela, segurar 30 d | 56 | -390 | -7.0 [-26.9; +14.3] | -36.0 | 32% | +193 | -94 | -17.8 |
| VENDER a descoberto na abertura da 1ª vela, 30 d, SEM stop | 56 | -161 | -2.9 [-22.6; +16.8] | +33.3 | 61% | +94 | -100 | -8.1 |
| VENDER a descoberto na abertura da 1ª vela, 30 d, stop +50% | 56 | +139 | +2.5 [-11.2; +16.5] | +1.9 | 50% | +94 | -50 | -2.5 |
| Comprar na abertura da 1ª vela, segurar 90 d | 53 | -1,251 | -23.6 [-54.7; +27.0] | -63.8 | 23% | +983 | -96 | -52.0 |
| VENDER a descoberto na abertura da 1ª vela, 90 d, SEM stop | 53 | -154 | -2.9 [-26.7; +19.5] | +35.7 | 53% | +96 | -100 | -8.8 |
| VENDER a descoberto na abertura da 1ª vela, 90 d, stop +50% | 53 | +69 | +1.3 [-15.4; +19.0] | -50.1 | 42% | +96 | -50 | -4.3 |
| Comprar no fech. de 24 h, segurar 30 d | 56 | -596 | -10.7 [-29.3; +9.9] | -41.2 | 30% | +238 | -86 | -22.4 |
| Comprar no fech. de 24 h, alvo +100% ou até 30 d | 56 | -318 | -5.7 [-23.7; +12.8] | -38.8 | 34% | +100 | -86 | -11.7 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 30 d | 56 | -205 | -3.7 [-19.7; +13.9] | -47.8 | 32% | +100 | -50 | -9.5 |
| VENDER a descoberto no fech. de 24 h, 30 d, SEM stop | 56 | +309 | +5.5 [-13.0; +23.5] | +38.6 | 66% | +86 | -100 | +1.0 |
| VENDER a descoberto no fech. de 24 h, 30 d, stop +50% | 56 | +262 | +4.7 [-9.6; +19.0] | +7.2 | 54% | +86 | -50 | +0.2 |
| Comprar no fech. de 24 h, segurar 90 d | 53 | -1,605 | -30.3 [-56.5; +9.3] | -64.0 | 19% | +760 | -95 | -53.2 |
| Comprar no fech. de 24 h, alvo +100% ou até 90 d | 53 | -424 | -8.0 [-29.6; +14.5] | -53.8 | 38% | +100 | -95 | -14.5 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 90 d | 53 | -273 | -5.2 [-22.1; +14.3] | -50.1 | 30% | +100 | -50 | -11.5 |
| VENDER a descoberto no fech. de 24 h, 90 d, SEM stop | 53 | +416 | +7.9 [-14.7; +29.4] | +53.6 | 62% | +95 | -100 | +2.7 |
| VENDER a descoberto no fech. de 24 h, 90 d, stop +50% | 53 | +275 | +5.2 [-11.2; +21.7] | -50.1 | 47% | +95 | -50 | -0.1 |

Spot (taxa 0,1%/lado; "H" = fech. da 1ª hora, "B" = fech. 24 h):

| Cenário | n | Soma US$ | Média US$/trade [IC95%] | Mediana | % lucrativos | Melhor | Pior | Média sem os 3 melhores |
|---|---|---|---|---|---|---|---|---|
| Comprar no fech. da 1ª hora, segurar 30 d | 199 | -868 | -4.4 [-15.7; +9.0] | -25.4 | 28% | +494 | -87 | -11.4 |
| Comprar no fech. da 1ª hora, segurar 90 d | 194 | -4,573 | -23.6 [-35.3; -8.2] | -43.8 | 23% | +1,058 | -95 | -31.6 |
| Comprar no fech. de 24 h, segurar 30 d | 199 | -2,253 | -11.3 [-19.5; -1.9] | -26.3 | 28% | +389 | -86 | -15.7 |
| Comprar no fech. de 24 h, alvo +100% ou até 30 d | 199 | -2,007 | -10.1 [-17.1; -2.2] | -23.8 | 30% | +100 | -86 | -11.8 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 30 d | 199 | -1,847 | -9.3 [-16.0; -2.0] | -27.8 | 29% | +100 | -50 | -11.0 |
| Comprar no fech. de 24 h, segurar 90 d | 194 | -5,864 | -30.2 [-37.8; -21.7] | -45.4 | 20% | +357 | -96 | -33.9 |
| Comprar no fech. de 24 h, alvo +100% ou até 90 d | 194 | -2,551 | -13.1 [-22.8; -2.9] | -35.6 | 29% | +100 | -96 | -14.9 |
| Comprar no fech. de 24 h, alvo +100% / stop −50% / até 90 d | 194 | -1,997 | -10.3 [-18.3; -1.7] | -50.1 | 25% | +100 | -50 | -12.0 |

**Leitura:**
- **Comprar e segurar perde em todos os cenários realistas** (−12% em 30 dias e −29,5% em 90 dias nos perpétuos pela entrada B; −11% e −30% no spot). Só 18% a 28% das operações dão lucro. O "melhor" caso (+US$ 471 em 30 dias) é um em 364; sem os 3 melhores o prejuízo médio é ainda maior.
- **Alvo de +100% ajuda mas não vira o jogo:** reduz a perda média para −US$ 6,60 (30 dias) e −US$ 5,10 (90 dias), com intervalo ainda majoritariamente abaixo de zero. Adicionar stop de −50% não melhora.
- **Short (espelho vendido) no fechamento de 24 h:** +US$ 6,40 por operação em 30 dias sem stop (IC95% +0,1 a +12,7; 68% das operações lucrativas) e +US$ 7,80 com stop de 50% (IC +2,9 a +12,6; 60% lucrativas). Em 90 dias: +US$ 4,90 (IC −3,0 a +12,6) sem stop e +US$ 9,40 (IC +3,6 a +15,5) com stop. Parece vantagem, mas veja as ressalvas abaixo.
- **O short não é espelho perfeito do long:** quando o preço sobe 50% ou dobra, o short é parado ou liquidado antes de a moeda voltar a cair, e a perda de uma operação pode chegar a −100% da margem.

**Sensibilidade ao funding** (taxa paga entre comprados e vendidos a cada 1 a 8 h; no perpétuo é custo ou receita real). Aproximação: aplicada sobre os US$ 100 iniciais de posição, o que **superestima** o funding pago por quem está vendido enquanto o preço cai:

| Entrada e prazo | n | Funding acumulado (mediana) | Funding acumulado (média) | Comprado: US$/trade sem → com funding | Vendido sem stop: sem → com funding | Vendido com stop 50%: sem → com funding |
|---|---|---|---|---|---|---|
| na abertura da 1ª vela, 30 d | 364 | -0.20% | -4.78% | -11.9 → -7.1 | +2.5 → +0.3 | +3.3 → +1.3 |
| na abertura da 1ª vela, 90 d | 350 | -0.77% | -9.08% | -26.9 → -17.9 | +1.2 → -1.6 | +4.5 → +1.4 |
| no fech. de 24 h, 30 d | 364 | +0.02% | -4.20% | -12.0 → -7.8 | +6.4 → +4.2 | +7.8 → +5.7 |
| no fech. de 24 h, 90 d | 350 | -0.30% | -8.38% | -29.5 → -21.1 | +4.9 → +1.8 | +9.4 → +6.0 |

Com funding o short cai de +6,40 para +4,20 (30 dias, sem stop) e de +4,90 para +1,80 (90 dias, sem stop); com stop de 50% fica em +5,70 e +6,00. O funding médio foi **negativo** (vendidos pagam compradores), porque moedas que despencam costumam ter funding muito negativo.

**O short é estável ao longo do tempo? Não.** Resultado médio por semestre de lançamento (entrada B, 30 dias):

| Semestre de lançamento | n | Comprado (US$/trade) | Vendido sem stop (US$/trade) | % lucrativos (sem stop) | Vendido com stop 50% (US$/trade) | % lucrativos (com stop) |
|---|---|---|---|---|---|---|
| 2024-S2 | 61 | +17.1 | -7.4 | 57% | -1.0 | 54% |
| 2025-S1 | 114 | -30.7 | +25.1 | 79% | +20.6 | 70% |
| 2025-S2 | 129 | -12.5 | +0.5 | 66% | +3.7 | 56% |
| 2026-S1 | 46 | -4.0 | -2.7 | 63% | -1.0 | 52% |
| 2026-S2 | 14 | -7.4 | -0.3 | 64% | +7.8 | 57% |
| Todos | 364 | -12.0 | +6.4 | 68% | +7.8 | 60% |

O ganho do short se concentra nas moedas lançadas no 1º semestre de 2025 (+US$ 25 sem stop e +US$ 21 com stop por operação), período em que o mercado de altcoins e memes desabou. Em 2024-S2 o short **perdeu** e nos demais semestres ficou perto de zero. É uma hipótese interessante para acompanhar, mas **não está comprovada como vantagem recorrente**.

Resultado do comprado por semestre (mediana/média da entrada B, 30 dias):

| Semestre de lançamento | n | Mediana | Média [IC95%] | % abaixo da entrada | % em 2×+ no fim | % tocou 2× | % tocou 5× |
|---|---|---|---|---|---|---|---|
| 2024-S2 | 61 | -10% | +17% [-6%; +43%] | 59% | 15% | 28% | 7% |
| 2025-S1 | 114 | -35% | -31% [-38%; -22%] | 81% | 1% | 10% | 1% |
| 2025-S2 | 129 | -31% | -12% [-23%; -0%] | 74% | 6% | 25% | 5% |
| 2026-S1 | 46 | -24% | -4% [-20%; +17%] | 63% | 4% | 26% | 4% |
| 2026-S2 | 14 | -26% | -7% [-36%; +26%] | 64% | 7% | 29% | 0% |

### 3.8 Risco de liquidação com alavancagem (perpétuos, 30 dias, entrada B)

Liquidação estimada: perda ≥ (1/alavancagem − 0,5%) em algum candle de 1 h. Preço de último negócio, não de marcação (a Bybit liquida por preço de marcação, que suaviza pavios; o resultado real pode diferir um pouco).

| Lado | Alavancagem | % liquidado em 30 d | Média US$/trade | Mediana | % lucrativos | Soma US$ (n=364) |
|---|---|---|---|---|---|---|
| comprado | 2× | 46% | -24.6 | -78.0 | 25% | -8,947 |
| comprado | 3× | 72% | -30.5 | -100.0 | 20% | -11,087 |
| comprado | 5× | 84% | -28.7 | -100.0 | 14% | -10,433 |
| comprado | 10× | 93% | -46.9 | -100.0 | 6% | -17,059 |
| comprado | 20× | 97% | -76.8 | -100.0 | 2% | -27,972 |
| vendido | 2× | 36% | +15.2 | +46.0 | 59% | +5,548 |
| vendido | 3× | 46% | +23.6 | +18.4 | 52% | +8,591 |
| vendido | 5× | 57% | +36.5 | -100.0 | 41% | +13,290 |
| vendido | 10× | 75% | +43.7 | -100.0 | 25% | +15,922 |
| vendido | 20× | 86% | +48.6 | -100.0 | 13% | +17,696 |

**Leitura:** com 3× comprado, 72% das posições teriam sido liquidadas em 30 dias; com 5×, 84%; com 10×, 93%. A mediana de queda máxima é −47%, então só alavancagem de 2× sobrevive a metade das moedas. As médias positivas do lado vendido com 10× ou mais vêm de poucas operações que não encostaram no stop; **a mediana é −100%** (liquidado) em 5× ou mais. Não é uma estratégia.

### 3.9 Liquidez e "spread" nos primeiros dias

Perpétuos:

| Métrica | P10 | P25 | Mediana | P75 | P90 |
|---|---|---|---|---|---|
| Volume negociado na 1ª hora (US$) | 28,859 | 128,613 | 501,944 | 2,113,852 | 5,133,318 |
| Volume nas primeiras 24 h (US$) | 4,057,588 | 9,020,677 | 28,594,502 | 83,325,013 | 197,555,969 |
| Volume nos primeiros 7 dias (US$) | 17,479,842 | 48,091,192 | 151,866,135 | 401,732,844 | 964,521,761 |
| Alta máx. do 1º dia sobre a abertura | +3% | +6% | +16% | +34% | +63% |
| Queda máx. do 1º dia sobre a abertura | -37% | -24% | -14% | -6% | -2% |
| Fechamento de 24 h sobre abertura | -29% | -15% | -3% | +12% | +36% |

Spot:

| Métrica | P10 | P25 | Mediana | P75 | P90 |
|---|---|---|---|---|---|
| Volume negociado na 1ª hora (US$) | 148,464 | 617,670 | 2,313,674 | 5,148,599 | 12,368,957 |
| Volume nas primeiras 24 h (US$) | 821,619 | 4,653,967 | 17,864,519 | 37,146,213 | 79,104,943 |
| Volume nos primeiros 7 dias (US$) | 4,192,124 | 25,664,185 | 87,154,449 | 189,239,179 | 370,913,527 |
| Fechamento da 1ª hora sobre a abertura da 1ª vela (artefato do leilão) | +6% | +49% | +203% | +437% | +878% |
| Alta máx. do 1º dia (após a 1ª hora) sobre o fech. da 1ª hora | +1% | +3% | +12% | +44% | +92% |
| Queda máx. do 1º dia (após a 1ª hora) sobre o fech. da 1ª hora | -36% | -25% | -14% | -5% | -1% |
| Fechamento de 24 h sobre fechamento da 1ª hora | -30% | -15% | -1% | +9% | +48% |

**Leitura:** o volume do primeiro dia costuma ser alto (mediana de US$ 28,6 milhões nos perpétuos), mas a **primeira hora é fina em 1 de cada 4 moedas** (volume abaixo de US$ 129 mil). Em US$ 100 o spread importa pouco; em valores maiores, importa. O preço de fechamento de 24 h costuma ser bem diferente da abertura (mediana −3%; −29% no pior decil), por isso a entrada pela abertura é irreal. Com derrapagem extra de 1% por lado, o comprado em 30 dias passa de −US$ 12,0 para −US$ 13,7.

### 3.10 Os maiores acertos e erros (perpétuos, 30 dias, entrada B)

Melhores:

| Símbolo | Meme? | Já existia? | Lançada em | Retorno 30 d (B) | Máxima alta | Máxima queda | Volume 24 h (US$) |
|---|---|---|---|---|---|---|---|
| USUALUSDT | não | não | 2024-11-19 | +472% | +529% | -19% | 8,590,790 |
| BEATUSDT | não | não | 2025-11-21 | +414% | +456% | -19% | 29,027,463 |
| COAIUSDT | não | não | 2025-10-02 | +299% | +6554% | -10% | 54,398,262 |
| BSBUSDT | não | não | 2026-03-26 | +288% | +382% | -6% | 32,360,681 |
| MEMEFIUSDT | sim | sim | 2025-04-09 | +238% | +983% | -5% | 1,235,525 |
| 1000XUSDT | não | não | 2024-10-25 | +235% | +862% | -48% | 20,074,668 |
| VIRTUALUSDT | não | não | 2024-11-01 | +205% | +351% | -28% | 37,663,942 |
| FARTCOINUSDT | sim | não | 2024-12-20 | +180% | +225% | -32% | 88,300,764 |
| AVNTUSDT | não | não | 2025-09-09 | +176% | +751% | -14% | 147,463,620 |
| PNUTUSDT | sim | não | 2024-11-11 | +171% | +430% | -19% | 238,003,903 |
| GRASSUSDT | não | não | 2024-10-17 | +168% | +285% | -48% | 1,638,407 |
| MORPHOUSDT | não | não | 2024-11-22 | +163% | +275% | -18% | 27,641,442 |

Piores:

| Símbolo | Meme? | Já existia? | Lançada em | Retorno 30 d (B) | Máxima alta | Máxima queda | Volume 24 h (US$) |
|---|---|---|---|---|---|---|---|
| SWARMSUSDT | não | não | 2025-01-06 | -94% | +9% | -94% | 144,279,878 |
| TMXUSDT | não | não | 2026-08-26 | -93% | +3% | -93% | 9,077,511 |
| JELLYJELLYUSDT | sim | não | 2025-01-30 | -86% | +5% | -94% | 315,275,849 |
| MUBARAKUSDT | sim | não | 2025-03-17 | -86% | +10% | -88% | 268,332,998 |
| BUZZUSDT | não | não | 2025-01-22 | -86% | +26% | -87% | 25,496,256 |
| ALCHUSDT | não | não | 2025-01-07 | -84% | +6% | -89% | 83,325,013 |
| 4STOCKUSDT | não | não | 2026-09-09 | -84% | +11% | -86% | 11,057,406 |
| ZEREBROUSDT | sim | não | 2024-12-30 | -82% | +44% | -85% | 97,506,558 |

---

## 4. Memecoins de launchpad (pump.fun, Four.meme etc.)

### 4.1 Medição própria — pools novos da GeckoTerminal

**Coleta-piloto, não é medição de retorno.** Foram registrados 3.656 pools novos pela GeckoTerminal (Solana e BSC) em cerca de 2 horas, mas só **20** já tinham a idade mínima para avaliação (cerca de 0,9 h de vida) quando a coleta parou. A amostra é pequena e jovem demais para medir quanto esses tokens rendem; ela só ilustra a velocidade com que morrem:

| Tipo de pool | Pools avaliados | % sem nenhuma negociação nos primeiros 30 min | % com ≤ 3 velas de 5 min em toda a vida (≈ morreu em minutos) | % sem negociação há mais de 1 h | Idade mediana na avaliação |
|---|---|---|---|---|---|
| pump.fun (Solana) | 9 | 0% | 89% | 0% | 0.9 h |
| Four.meme (BSC) | 3 | 0% | 100% | 0% | 0.9 h |
| Outros launchpads (Meteora DBC, LaunchLab, letsbonk, ...) | 1 | 0% | 100% | 0% | 0.9 h |
| Pools de AMM (Uniswap, Pancake, PumpSwap, Meteora DAMM, ...) | 7 | 0% | 29% | 14% | 0.9 h |

Dos 9 tokens da pump.fun avaliados, **89% tiveram no máximo 3 velas de 5 minutos em toda a vida** (a negociação acabou em minutos) e o valor de mercado (FDV) de pico mediano foi de **US$ 6,6 mil**; nenhum chegou a US$ 50 mil. As tabelas de retorno depois de 15 minutos ficaram vazias porque nenhum pool tinha 1 hora completa de histórico. Para medir retorno seria preciso acompanhar milhares de pools por dias; os estudos citados em 4.2 fazem isso em escala muito maior.

### 4.2 Estudos e dados publicados

### Estudos e dados publicados (CITAÇÕES — não são medição própria)

Todos os números abaixo foram lidos nas páginas originais indicadas (acesso em 12/10/2026), exceto onde marcado.

| Fonte | O que mediu | Número principal | Ressalva do próprio estudo |
|---|---|---|---|
| [Solidus Labs — "2025 Rug Pull Report: Rug Pulls and Pump-and-Dumps on Solana"](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance) (mai/2025) | tokens criados na pump.fun entre jan/2024 e mar/2025 | **98,6%** colapsaram (liquidez abaixo de US$ 1.000 em SOL); mais de 7 milhões de tokens com ≥ 5 negociações, só ~97 mil mantêm liquidez acima de US$ 1.000. Nos pools da Raydium V4, ~93% de 388 mil mostraram "soft rug pull" (liquidez retirada de uma vez) | são heurísticas on-chain, não fraude comprovada; o próprio relatório mostra 98,6% no corpo e 98,7% no resumo; tokens que "graduaram" ficam fora da conta |
| [Marino, Naviglio, Tarantelli, Lillo — "Predicting the success of new crypto-tokens: the Pump.fun case" (arXiv:2602.14860)](https://arxiv.org/html/2602.14860v1) (fev/2026) | 655.770 tokens criados na pump.fun de 1/set a 1/out de 2025 | só **~0,6%** graduam (completam a curva); mediana de ~4,4 minutos até graduar; dos 184.282 tokens com ≥ 30 negociações, **92,2%** tiveram pelo menos um "dump" (queda brusca) | os números de graduação (0,63% × 0,66% × 2,55%) variam um pouco dentro do próprio artigo; é pré-publicação (arXiv), sem revisão por pares |
| [CoinGecko Research — "Dead Coins: Over 50% of Cryptocurrencies Have Failed"](https://www.coingecko.com/research/publications/how-many-cryptocurrencies-failed) (Shaun Paul Lee; atualizado em 17/04/2026) | tokens listados na GeckoTerminal de jul/2021 a dez/2025 | **53,2%** de todos os tokens já listados estão "mortos" (sem negociação ativa); só em 2025 foram 11,6 milhões (86,3% de todas as falências). O estudo só conta tokens com ≥ 1 negociação e, na pump.fun, só os que graduaram | como só entram os que graduaram na pump.fun, o número **subestima** a mortalidade dos lançamentos de launchpad |
| [Decrypt — "Just 0.4% of Pump.fun Traders Have Made More Than $10,000"](https://decrypt.co/300403/pump-fun-traders-millionaires) (jan/2025; dados do analista Adam Tehc na Dune) | carteiras da pump.fun | **0,4%** das carteiras (55.012 de > 13,4 milhões) lucraram mais de US$ 10 mil; 294 carteiras (~0,002%) passaram de US$ 1 milhão | o painel ignora compras feitas depois da graduação e pode ser distorcido por bots; os cofundadores da pump.fun contestam ("a verdadeira quantidade é uma ordem de grandeza maior") |
| [Blockmedia — "Key Takeaways from Upbit's New KRW Listings in 2025"](https://www.blockmedia.co.kr/research-english/1064579) | 59 tokens novos na Upbit e 144 na Bithumb em 2025: US$ 100 comprados no **fechamento do dia da listagem** e mantidos até 11/03/2026 | mediana **−80,9%** (Upbit) e **−82,1%** (Bithumb); só 2 de 59 (Upbit) e 8 de 144 (Bithumb) terminaram no lucro; 33 tokens da Bithumb perderam > 90% | câmbio KRW/USD não foi considerado; é metodologia quase idêntica à "entrada B" deste estudo, por isso serve de comparação |
| [Yellow — resumo do conjunto de dados da Memento Research (20/12/2025)](https://yellow.com/news/the-great-2025-token-crash-100-out-of-118-launches-in-the-red-%E2%80%93-what-went-wrong) | 118 TGEs (lançamentos de tokens "sérios") de 2025 | **84,7%** (100 de 118) negociavam abaixo do FDV de abertura | fonte secundária; o critério de inclusão e a data de corte não são informados na reportagem; compara FDV (valor total diluído), não preço por unidade |

**Leitura honesta dessas fontes:** todas apontam para a mesma direção (a esmagadora maioria dos lançamentos perde valor; os poucos que multiplicam são exceção e o dinheiro fica concentrado em pouquíssimas carteiras), mas **nenhuma é uma medição com o rigor de um estudo revisado por pares**: são relatórios de empresas, painéis comunitários e uma pré-publicação. Os números exatos variam conforme a definição de "falhou" (liquidez < US$ 1.000, sem negociação, abaixo do FDV de abertura, etc.).

---

## 5. Ressalvas obrigatórias

1. **Viés de sobrevivência (otimista).**
   - Os perpétuos deslistados **estão** na amostra (96 de 369, ou 26%), o que é bom. Mas os spots deslistados de moedas que nunca tiveram perpétuo **somem** da API da Bybit; só 31 spots deslistados foram recuperados.
   - Mais importante: **só entram moedas que a Bybit escolheu listar.** Milhares de tokens nascem sem chegar a nenhuma corretora grande, e esses não estão aqui. Na pump.fun, por exemplo, só ~0,6% chegam a graduar. Logo, **o resultado da Bybit é o cenário bom**: o resultado das moedas lançadas "por aí" é pior.
2. **Tamanho da amostra.** 369 perpétuos e 200 spots, sendo 56 e 23 memecoins, de um período específico e **não independentes** (as moedas sobem e caem juntas com o mercado). Os intervalos de confiança estão nas tabelas; vários incluem zero.
3. **Regime de mercado.** A amostra cobre uma alta de fim de 2024, um colapso de altcoins em 2025 (incluindo a liquidação de 10/10/2025) e um mercado fraco depois. Resultados por semestre mostram diferenças grandes. Não dá para extrapolar para uma alta forte.
4. **Liquidez e spread nos primeiros dias.** A abertura (entrada A) e, no spot, a primeira vela são irreais. A 1ª hora é fina em parte das moedas. As simulações assumem execução no preço de fechamento, sem derrapagem (teste com 1% por lado piora cerca de US$ 1,70 por operação).
5. **Liquidação com alavancagem.** Estimada com velas de 1 h e preço de último negócio; liquidações reais acontecem com preço de marcação e podem ser mais cedo ou mais tarde. O short sem alavancagem pode perder 100% da margem.
6. **Funding.** Foi incluído só como sensibilidade e de forma aproximada (sobre o valor inicial da posição).
7. **Marcação de memecoins e de "lançamento aparente" é aproximada** (símbolos repetem entre projetos; não verifiquei corretoras além da Binance e do spot da Bybit). A lista usada está no apêndice.
8. **Granularidade de 1 hora.** Stops, alvos e liquidações dentro da mesma vela são resolvidos de forma conservadora, mas não são exatos.
9. **Não incluído:** impostos, custos de saque e transferência, tokens que nunca foram listados na Bybit, lançamentos só em DEX (exceto a amostra do item 4.1).

---

## 6. Conclusão e o que fazer com isso

**Em linguagem simples:** "lançamentos multiplicam pouco capital" é um **viés de sobrevivência**. Enxergamos as poucas moedas que subiram 10× e 50× (RAVE, COAI, AIA, VIRTUAL...) e esquecemos as dezenas que perderam 60% a 90%. Nos números reais da Bybit, o resultado típico do lançamento é **perder cerca de metade em três meses**, a **chance de estar acima de 2× depois de um mês é de ~6%** e a **de tocar 10× em seis meses é de ~5%** (e quase sempre devolve). Memecoins não mostraram nenhuma vantagem estatística. Comprar com alavancagem quase garante liquidação. Fora da Bybit, nos launchpads, a situação é pior: a esmagadora maioria dos tokens morre em minutos e quase ninguém lucra, segundo medições próprias e estudos citados.

**Para o projeto:**
- **Comprar lançamentos não é uma estratégia com vantagem** nesses dados. O scanner deve tratar "moeda nova (< 90 dias)" como **fator de risco/filtro**, não como oportunidade.
- A única hipótese que merece acompanhamento é o **short após o 1º dia** (+US$ 4 a +8 por US$ 100 em 30 dias), mas ela depende de um único semestre, tem perdas de até −50% a −100% por operação, exige perpétuo e funding, e **não deve ser tratada como vantagem** antes de um teste prospectivo (paper) por vários meses.
- Se o usuário quiser "bilhetes de loteria", o tamanho certo é o de uma perda total aceitável (US$ 100 a US$ 200 por moeda), sem alavancagem, sem esperar média positiva, e sabendo que o ganho exige vender na alta (quase ninguém vende).

---

## 7. Apêndice

**Como reproduzir** (tudo em `bybit_bot`, com `.venv\Scripts\python.exe -X utf8`):

```
src/bot/tools/estudo_lancamentos.py bybit-coletar        # instrumentos + velas 1h (cache em data/estudo_lancamentos/bybit)
src/bot/tools/estudo_lancamentos.py bybit-funding        # histórico de funding
src/bot/tools/estudo_lancamentos.py memes                # categoria meme da CoinGecko
src/bot/tools/estudo_lancamentos.py bybit-analisar       # métricas, tabelas.json, moedas_metricas.csv
src/bot/tools/estudo_lancamentos.py launchpad-coletar --horas 2   # pools novos (GeckoTerminal)
src/bot/tools/estudo_lancamentos.py launchpad-avaliar --idade-min-h 3
src/bot/tools/estudo_lancamentos.py relatorio
```

**Arquivos gerados** em `data/estudo_lancamentos/`: `bybit/` (instrumentos, perpétuos e spots selecionados, velas de 1 h, funding, idade Binance, lista CoinGecko), `moedas_metricas.csv` (todas as métricas por moeda), `tabelas.json`, `launchpad_pools.jsonl` (pools coletados), `launchpad_ohlcv/` (velas de 5 min), `launchpad_metricas.csv`.

**Memecoins marcadas** (por símbolo da Bybit; revisão manual, aproximada): 4, ACT, AI16Z, AIXBT, ANIME, BAN, BANANAS31, BILLY, BIRB, BOBBOB, BROCCOLI, BSU, CASHCAT, CAT, CHEEMS, CHILLGUY, DOOD, ELON, FARTCOIN, FIGHT, FWOG, GIGA, GIGGLE, GOAT, GORK, GRIFFAIN, HAJIMI, HIPPO, HPOS10I, JAILSTOOL, JELLYJELLY, KOMA, LAUNCHCOIN, LUCE, M, MARSCOIN, MELANIA, MEMEFI, MICHI, MUBARAK, NEIROCTO, PENGU, PIPPIN, PNUT, PUMP, PUMPFUN, RFC, SIREN, SPX, TOSHI, TRUMP, TSTBSC, TUT, USELESS, VINE, WHITEWHALE, YZY, ZEREBRO

**Moedas marcadas como "já negociavam antes"** (Binance ou spot da Bybit > 30 dias antes): ALPINE, APEX, ASR, AVA, BLEND, CFG, CGPT, COOK, COOKIE, CPOOL, DATA, DBR, DIA, DOLO, FHE, FIS, FLUID, GPS, GRAM, HIVE, KII, LIT, LUCE, MEMEFI, MLN, MVL, NS, OBT, OM, PROS, PROVE, PUMPBTC, PUNDIX, RONIN, SAROS, SD, SERAPH, SOLO, SOSO, SPK, SQD, SXT, TAI, TROY, USD1, VANA, VET, VIC, VTHO, WET, WLFI, XDC, XION, XTER, XUSD, ZENT, ZEREBRO
