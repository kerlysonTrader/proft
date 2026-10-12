# Setups de estrutura — resumo (12/10/2026)

Critério mínimo (✅): ≥ 100 trades, expectância > 0.1 R, PF ≥ 1.2 e positivo em pelo menos 2/3 dos anos. Intraday 15m/1H, sem exigir score, custos incluídos.

## Combinações que passam

| mercado | lado | saida | setup | trades | acerto | exp_r | pf | anos_pos | passa |
|---|---|---|---|---|---|---|---|---|---|
| perp | compra | parcial + móvel | estrutura_bos | 348 | 42.2% | +0.116 | 1.22 | 2/2 | ✅ |

## 15 melhores por expectância (setup individual)

| mercado | lado | saida | setup | trades | acerto | exp_r | pf | anos_pos | passa |
|---|---|---|---|---|---|---|---|---|---|
| perp | venda | alvo 2R | medias_cruzamento | 199 | 39.7% | +0.160 | 1.27 | 1/2 |  |
| perp | compra | alvo 2R | estrutura_choch | 70 | 38.6% | +0.130 | 1.22 | 2/2 |  |
| indices | venda | parcial + móvel | medias_cruzamento | 82 | 42.7% | +0.119 | 1.19 | 3/5 |  |
| perp | compra | parcial + móvel | estrutura_bos | 348 | 42.2% | +0.116 | 1.22 | 2/2 | ✅ |
| perp | compra | alvo 2R | estrutura_bos | 328 | 36.6% | +0.089 | 1.15 | 1/2 |  |
| perp | compra | parcial + móvel | medias_cruzamento | 169 | 44.4% | +0.069 | 1.14 | 2/2 |  |
| perp | compra | alvo 1R | estrutura_bos | 517 | 53.2% | +0.069 | 1.16 | 2/2 |  |
| perp | venda | alvo 2R | lt_rompimento | 188 | 37.2% | +0.065 | 1.10 | 1/2 |  |
| metais | compra | alvo 2R | estrutura_bos | 359 | 36.8% | +0.063 | 1.11 | 4/5 |  |
| indices | venda | alvo 1R | medias_cruzamento | 96 | 49.0% | +0.043 | 1.08 | 3/5 |  |
| perp | compra | alvo 2R | medias_cruzamento | 166 | 34.9% | +0.026 | 1.04 | 1/2 |  |
| indices | compra | alvo 1R | estrutura_choch | 194 | 47.9% | +0.021 | 1.04 | 3/5 |  |
| perp | venda | alvo 1R | lt_rompimento | 269 | 51.7% | +0.016 | 1.03 | 1/2 |  |
| perp | compra | parcial + móvel | cunha | 107 | 42.1% | +0.012 | 1.02 | 1/2 |  |
| energia | compra | parcial + móvel | estrutura_choch | 110 | 42.7% | +0.011 | 1.02 | 2/5 |  |

## Tabela completa

| mercado | lado | saida | setup | trades | acerto | exp_r | pf | anos_pos | passa |
|---|---|---|---|---|---|---|---|---|---|
| energia | compra | alvo 1R | todos | 1436 | 38.4% | -0.361 | 0.49 | 0/5 |  |
| energia | compra | alvo 1R | cunha | 119 | 40.3% | -0.380 | 0.51 | 0/5 |  |
| energia | compra | alvo 1R | estrutura_bos | 558 | 37.6% | -0.370 | 0.46 | 0/5 |  |
| energia | compra | alvo 1R | estrutura_choch | 134 | 44.0% | -0.164 | 0.72 | 1/5 |  |
| energia | compra | alvo 1R | lt_rompimento | 345 | 34.5% | -0.533 | 0.37 | 0/5 |  |
| energia | compra | alvo 1R | medias_cruzamento | 280 | 41.1% | -0.219 | 0.66 | 1/5 |  |
| energia | compra | alvo 2R | todos | 1200 | 28.2% | -0.415 | 0.52 | 0/5 |  |
| energia | compra | alvo 2R | cunha | 91 | 24.2% | -0.550 | 0.45 | 1/5 |  |
| energia | compra | alvo 2R | estrutura_bos | 456 | 26.8% | -0.427 | 0.47 | 0/5 |  |
| energia | compra | alvo 2R | estrutura_choch | 98 | 37.8% | -0.042 | 0.94 | 2/5 |  |
| energia | compra | alvo 2R | lt_rompimento | 320 | 26.9% | -0.573 | 0.42 | 0/5 |  |
| energia | compra | alvo 2R | medias_cruzamento | 235 | 30.6% | -0.278 | 0.66 | 2/5 |  |
| energia | compra | parcial + móvel | todos | 1280 | 32.7% | -0.398 | 0.50 | 0/5 |  |
| energia | compra | parcial + móvel | cunha | 108 | 33.3% | -0.437 | 0.51 | 1/5 |  |
| energia | compra | parcial + móvel | estrutura_bos | 454 | 31.5% | -0.406 | 0.47 | 0/5 |  |
| energia | compra | parcial + móvel | estrutura_choch | 110 | 42.7% | +0.011 | 1.02 | 2/5 |  |
| energia | compra | parcial + móvel | lt_rompimento | 347 | 29.1% | -0.599 | 0.35 | 0/5 |  |
| energia | compra | parcial + móvel | medias_cruzamento | 261 | 35.2% | -0.272 | 0.63 | 1/5 |  |
| energia | venda | alvo 1R | todos | 1375 | 38.4% | -0.429 | 0.44 | 0/5 |  |
| energia | venda | alvo 1R | cunha | 151 | 38.4% | -0.509 | 0.42 | 1/5 |  |
| energia | venda | alvo 1R | estrutura_bos | 501 | 42.3% | -0.266 | 0.58 | 0/5 |  |
| energia | venda | alvo 1R | estrutura_choch | 104 | 39.4% | -0.341 | 0.51 | 1/5 |  |
| energia | venda | alvo 1R | lt_rompimento | 335 | 35.2% | -0.559 | 0.38 | 0/5 |  |
| energia | venda | alvo 1R | medias_cruzamento | 284 | 34.9% | -0.551 | 0.35 | 0/5 |  |
| energia | venda | alvo 2R | todos | 1128 | 27.7% | -0.468 | 0.49 | 0/5 |  |
| energia | venda | alvo 2R | cunha | 125 | 32.8% | -0.436 | 0.57 | 2/5 |  |
| energia | venda | alvo 2R | estrutura_bos | 406 | 27.6% | -0.343 | 0.57 | 0/5 |  |
| energia | venda | alvo 2R | estrutura_choch | 91 | 26.4% | -0.348 | 0.59 | 1/5 |  |
| energia | venda | alvo 2R | lt_rompimento | 272 | 25.4% | -0.663 | 0.39 | 0/5 |  |
| energia | venda | alvo 2R | medias_cruzamento | 234 | 28.2% | -0.523 | 0.45 | 0/5 |  |
| energia | venda | parcial + móvel | todos | 1198 | 32.7% | -0.462 | 0.47 | 0/5 |  |
| energia | venda | parcial + móvel | cunha | 147 | 34.7% | -0.533 | 0.45 | 0/5 |  |
| energia | venda | parcial + móvel | estrutura_bos | 390 | 35.6% | -0.283 | 0.60 | 0/5 |  |
| energia | venda | parcial + móvel | estrutura_choch | 97 | 30.9% | -0.331 | 0.59 | 2/5 |  |
| energia | venda | parcial + móvel | lt_rompimento | 301 | 31.9% | -0.563 | 0.42 | 0/5 |  |
| energia | venda | parcial + móvel | medias_cruzamento | 263 | 28.9% | -0.618 | 0.35 | 0/5 |  |
| forex | compra | alvo 1R | todos | 3619 | 31.2% | -0.454 | 0.51 | 0/5 |  |
| forex | compra | alvo 1R | cunha | 389 | 28.5% | -0.636 | 0.45 | 0/5 |  |
| forex | compra | alvo 1R | estrutura_bos | 1281 | 34.5% | -0.292 | 0.61 | 0/5 |  |
| forex | compra | alvo 1R | estrutura_choch | 280 | 36.8% | -0.170 | 0.75 | 2/5 |  |
| forex | compra | alvo 1R | lt_rompimento | 901 | 29.0% | -0.617 | 0.44 | 0/5 |  |
| forex | compra | alvo 1R | medias_cruzamento | 768 | 27.7% | -0.545 | 0.44 | 0/5 |  |
| forex | compra | alvo 2R | todos | 2959 | 22.3% | -0.493 | 0.54 | 0/5 |  |
| forex | compra | alvo 2R | cunha | 341 | 21.1% | -0.591 | 0.53 | 0/5 |  |
| forex | compra | alvo 2R | estrutura_bos | 991 | 23.3% | -0.364 | 0.59 | 0/5 |  |
| forex | compra | alvo 2R | estrutura_choch | 265 | 27.9% | -0.136 | 0.83 | 1/5 |  |
| forex | compra | alvo 2R | lt_rompimento | 731 | 20.9% | -0.746 | 0.43 | 0/5 |  |
| forex | compra | alvo 2R | medias_cruzamento | 631 | 20.8% | -0.500 | 0.51 | 0/5 |  |
| forex | compra | parcial + móvel | todos | 3166 | 25.1% | -0.550 | 0.46 | 0/5 |  |
| forex | compra | parcial + móvel | cunha | 381 | 22.8% | -0.739 | 0.41 | 0/5 |  |
| forex | compra | parcial + móvel | estrutura_bos | 988 | 26.8% | -0.374 | 0.56 | 0/5 |  |
| forex | compra | parcial + móvel | estrutura_choch | 278 | 28.8% | -0.320 | 0.61 | 0/5 |  |
| forex | compra | parcial + móvel | lt_rompimento | 812 | 22.8% | -0.770 | 0.36 | 0/5 |  |
| forex | compra | parcial + móvel | medias_cruzamento | 707 | 25.3% | -0.532 | 0.47 | 0/5 |  |
| forex | venda | alvo 1R | todos | 3353 | 29.9% | -0.483 | 0.48 | 0/5 |  |
| forex | venda | alvo 1R | cunha | 408 | 30.6% | -0.586 | 0.48 | 1/5 |  |
| forex | venda | alvo 1R | estrutura_bos | 1185 | 31.4% | -0.346 | 0.55 | 0/5 |  |
| forex | venda | alvo 1R | estrutura_choch | 263 | 25.1% | -0.493 | 0.41 | 0/5 |  |
| forex | venda | alvo 1R | lt_rompimento | 836 | 27.8% | -0.652 | 0.42 | 0/5 |  |
| forex | venda | alvo 1R | medias_cruzamento | 661 | 31.3% | -0.446 | 0.50 | 0/5 |  |
| forex | venda | alvo 2R | todos | 2830 | 21.8% | -0.508 | 0.52 | 0/5 |  |
| forex | venda | alvo 2R | cunha | 372 | 22.8% | -0.542 | 0.56 | 0/5 |  |
| forex | venda | alvo 2R | estrutura_bos | 940 | 22.9% | -0.403 | 0.56 | 0/5 |  |
| forex | venda | alvo 2R | estrutura_choch | 243 | 19.3% | -0.474 | 0.46 | 0/5 |  |
| forex | venda | alvo 2R | lt_rompimento | 720 | 20.0% | -0.662 | 0.47 | 1/5 |  |
| forex | venda | alvo 2R | medias_cruzamento | 555 | 22.7% | -0.476 | 0.53 | 0/5 |  |
| forex | venda | parcial + móvel | todos | 3013 | 25.0% | -0.540 | 0.47 | 0/5 |  |
| forex | venda | parcial + móvel | cunha | 410 | 25.4% | -0.645 | 0.46 | 1/5 |  |
| forex | venda | parcial + móvel | estrutura_bos | 962 | 25.4% | -0.405 | 0.51 | 0/5 |  |
| forex | venda | parcial + móvel | estrutura_choch | 258 | 21.7% | -0.495 | 0.43 | 0/5 |  |
| forex | venda | parcial + móvel | lt_rompimento | 808 | 23.8% | -0.716 | 0.41 | 0/5 |  |
| forex | venda | parcial + móvel | medias_cruzamento | 575 | 27.5% | -0.466 | 0.52 | 0/5 |  |
| indices | compra | alvo 1R | todos | 2095 | 43.3% | -0.117 | 0.82 | 0/5 |  |
| indices | compra | alvo 1R | cunha | 190 | 41.1% | -0.158 | 0.77 | 1/5 |  |
| indices | compra | alvo 1R | estrutura_bos | 871 | 43.3% | -0.123 | 0.80 | 0/5 |  |
| indices | compra | alvo 1R | estrutura_choch | 194 | 47.9% | +0.021 | 1.04 | 3/5 |  |
| indices | compra | alvo 1R | lt_rompimento | 449 | 43.7% | -0.107 | 0.84 | 0/5 |  |
| indices | compra | alvo 1R | medias_cruzamento | 391 | 41.7% | -0.162 | 0.76 | 0/5 |  |
| indices | compra | alvo 2R | todos | 1620 | 30.6% | -0.107 | 0.87 | 0/5 |  |
| indices | compra | alvo 2R | cunha | 151 | 29.1% | -0.176 | 0.80 | 1/5 |  |
| indices | compra | alvo 2R | estrutura_bos | 627 | 30.0% | -0.149 | 0.81 | 2/5 |  |
| indices | compra | alvo 2R | estrutura_choch | 152 | 29.6% | -0.036 | 0.95 | 3/5 |  |
| indices | compra | alvo 2R | lt_rompimento | 369 | 32.5% | -0.039 | 0.95 | 2/5 |  |
| indices | compra | alvo 2R | medias_cruzamento | 321 | 30.5% | -0.105 | 0.87 | 1/5 |  |
| indices | compra | parcial + móvel | todos | 1758 | 35.1% | -0.168 | 0.78 | 0/5 |  |
| indices | compra | parcial + móvel | cunha | 187 | 34.8% | -0.166 | 0.80 | 1/5 |  |
| indices | compra | parcial + móvel | estrutura_bos | 601 | 34.1% | -0.183 | 0.76 | 1/5 |  |
| indices | compra | parcial + móvel | estrutura_choch | 171 | 38.0% | -0.085 | 0.87 | 2/5 |  |
| indices | compra | parcial + móvel | lt_rompimento | 423 | 37.6% | -0.110 | 0.86 | 1/5 |  |
| indices | compra | parcial + móvel | medias_cruzamento | 376 | 32.7% | -0.247 | 0.69 | 0/5 |  |
| indices | venda | alvo 1R | todos | 500 | 41.6% | -0.161 | 0.76 | 2/5 |  |
| indices | venda | alvo 1R | cunha | 61 | 34.4% | -0.359 | 0.57 | 1/5 |  |
| indices | venda | alvo 1R | estrutura_bos | 181 | 44.2% | -0.095 | 0.84 | 3/5 |  |
| indices | venda | alvo 1R | estrutura_choch | 39 | 33.3% | -0.309 | 0.57 | 1/5 |  |
| indices | venda | alvo 1R | lt_rompimento | 123 | 38.2% | -0.272 | 0.64 | 1/5 |  |
| indices | venda | alvo 1R | medias_cruzamento | 96 | 49.0% | +0.043 | 1.08 | 3/5 |  |
| indices | venda | alvo 2R | todos | 385 | 25.5% | -0.317 | 0.63 | 1/5 |  |
| indices | venda | alvo 2R | cunha | 50 | 20.0% | -0.623 | 0.40 | 0/5 |  |
| indices | venda | alvo 2R | estrutura_bos | 127 | 30.7% | -0.113 | 0.85 | 2/5 |  |
| indices | venda | alvo 2R | estrutura_choch | 29 | 27.6% | -0.208 | 0.73 | 2/5 |  |
| indices | venda | alvo 2R | lt_rompimento | 105 | 21.0% | -0.472 | 0.51 | 1/5 |  |
| indices | venda | alvo 2R | medias_cruzamento | 74 | 25.7% | -0.281 | 0.67 | 1/5 |  |
| indices | venda | parcial + móvel | todos | 405 | 33.1% | -0.273 | 0.65 | 0/5 |  |
| indices | venda | parcial + móvel | cunha | 57 | 22.8% | -0.655 | 0.33 | 0/5 |  |
| indices | venda | parcial + móvel | estrutura_bos | 117 | 35.0% | -0.170 | 0.76 | 3/5 |  |
| indices | venda | parcial + móvel | estrutura_choch | 33 | 27.3% | -0.438 | 0.45 | 1/5 |  |
| indices | venda | parcial + móvel | lt_rompimento | 116 | 31.0% | -0.419 | 0.51 | 1/5 |  |
| indices | venda | parcial + móvel | medias_cruzamento | 82 | 42.7% | +0.119 | 1.19 | 3/5 |  |
| metais | compra | alvo 1R | todos | 1253 | 44.0% | -0.078 | 0.86 | 1/5 |  |
| metais | compra | alvo 1R | cunha | 109 | 43.1% | -0.109 | 0.82 | 0/5 |  |
| metais | compra | alvo 1R | estrutura_bos | 470 | 47.2% | -0.007 | 0.99 | 2/5 |  |
| metais | compra | alvo 1R | estrutura_choch | 98 | 40.8% | -0.113 | 0.80 | 2/5 |  |
| metais | compra | alvo 1R | lt_rompimento | 347 | 45.5% | -0.047 | 0.92 | 1/5 |  |
| metais | compra | alvo 1R | medias_cruzamento | 229 | 36.7% | -0.242 | 0.62 | 1/5 |  |
| metais | compra | alvo 2R | todos | 1027 | 31.8% | -0.072 | 0.90 | 1/5 |  |
| metais | compra | alvo 2R | cunha | 101 | 32.7% | -0.010 | 0.99 | 3/5 |  |
| metais | compra | alvo 2R | estrutura_bos | 359 | 36.8% | +0.063 | 1.11 | 4/5 |  |
| metais | compra | alvo 2R | estrutura_choch | 76 | 26.3% | -0.159 | 0.78 | 2/5 |  |
| metais | compra | alvo 2R | lt_rompimento | 291 | 30.9% | -0.100 | 0.87 | 1/5 |  |
| metais | compra | alvo 2R | medias_cruzamento | 200 | 26.0% | -0.270 | 0.63 | 2/5 |  |
| metais | compra | parcial + móvel | todos | 1093 | 36.3% | -0.088 | 0.87 | 0/5 |  |
| metais | compra | parcial + móvel | cunha | 121 | 36.4% | -0.139 | 0.81 | 1/5 |  |
| metais | compra | parcial + móvel | estrutura_bos | 352 | 37.5% | -0.066 | 0.89 | 2/5 |  |
| metais | compra | parcial + móvel | estrutura_choch | 74 | 32.4% | -0.113 | 0.83 | 2/5 |  |
| metais | compra | parcial + móvel | lt_rompimento | 330 | 37.6% | -0.049 | 0.93 | 1/5 |  |
| metais | compra | parcial + móvel | medias_cruzamento | 216 | 33.8% | -0.148 | 0.78 | 3/5 |  |
| metais | venda | alvo 1R | todos | 1061 | 40.8% | -0.134 | 0.77 | 0/5 |  |
| metais | venda | alvo 1R | cunha | 143 | 34.3% | -0.354 | 0.53 | 0/5 |  |
| metais | venda | alvo 1R | estrutura_bos | 359 | 44.0% | -0.023 | 0.95 | 1/5 |  |
| metais | venda | alvo 1R | estrutura_choch | 91 | 34.1% | -0.241 | 0.59 | 0/5 |  |
| metais | venda | alvo 1R | lt_rompimento | 273 | 41.0% | -0.166 | 0.73 | 0/5 |  |
| metais | venda | alvo 1R | medias_cruzamento | 195 | 42.6% | -0.085 | 0.84 | 2/5 |  |
| metais | venda | alvo 2R | todos | 874 | 27.6% | -0.215 | 0.69 | 0/5 |  |
| metais | venda | alvo 2R | cunha | 117 | 21.4% | -0.467 | 0.47 | 0/5 |  |
| metais | venda | alvo 2R | estrutura_bos | 282 | 28.7% | -0.121 | 0.80 | 1/5 |  |
| metais | venda | alvo 2R | estrutura_choch | 69 | 21.7% | -0.271 | 0.58 | 1/5 |  |
| metais | venda | alvo 2R | lt_rompimento | 243 | 28.0% | -0.286 | 0.63 | 0/5 |  |
| metais | venda | alvo 2R | medias_cruzamento | 163 | 31.9% | -0.069 | 0.89 | 2/5 |  |
| metais | venda | parcial + móvel | todos | 925 | 32.4% | -0.206 | 0.68 | 0/5 |  |
| metais | venda | parcial + móvel | cunha | 138 | 24.6% | -0.526 | 0.39 | 0/5 |  |
| metais | venda | parcial + móvel | estrutura_bos | 272 | 34.2% | -0.113 | 0.80 | 1/5 |  |
| metais | venda | parcial + móvel | estrutura_choch | 73 | 32.9% | -0.169 | 0.69 | 1/5 |  |
| metais | venda | parcial + móvel | lt_rompimento | 267 | 33.7% | -0.229 | 0.67 | 0/5 |  |
| metais | venda | parcial + móvel | medias_cruzamento | 175 | 33.7% | -0.079 | 0.87 | 1/5 |  |
| perp | compra | alvo 1R | todos | 1146 | 48.4% | -0.043 | 0.92 | 0/2 |  |
| perp | compra | alvo 1R | cunha | 117 | 45.3% | -0.143 | 0.75 | 1/2 |  |
| perp | compra | alvo 1R | estrutura_bos | 517 | 53.2% | +0.069 | 1.16 | 2/2 |  |
| perp | compra | alvo 1R | estrutura_choch | 105 | 43.8% | -0.148 | 0.73 | 0/2 |  |
| perp | compra | alvo 1R | lt_rompimento | 222 | 43.2% | -0.163 | 0.72 | 0/2 |  |
| perp | compra | alvo 1R | medias_cruzamento | 185 | 45.9% | -0.087 | 0.84 | 0/2 |  |
| perp | compra | alvo 2R | todos | 796 | 35.3% | +0.043 | 1.07 | 2/2 |  |
| perp | compra | alvo 2R | cunha | 84 | 33.3% | -0.054 | 0.92 | 1/2 |  |
| perp | compra | alvo 2R | estrutura_bos | 328 | 36.6% | +0.089 | 1.15 | 1/2 |  |
| perp | compra | alvo 2R | estrutura_choch | 70 | 38.6% | +0.130 | 1.22 | 2/2 |  |
| perp | compra | alvo 2R | lt_rompimento | 148 | 32.4% | -0.027 | 0.96 | 1/2 |  |
| perp | compra | alvo 2R | medias_cruzamento | 166 | 34.9% | +0.026 | 1.04 | 1/2 |  |
| perp | compra | parcial + móvel | todos | 857 | 40.0% | +0.001 | 1.00 | 1/2 |  |
| perp | compra | parcial + móvel | cunha | 107 | 42.1% | +0.012 | 1.02 | 1/2 |  |
| perp | compra | parcial + móvel | estrutura_bos | 348 | 42.2% | +0.116 | 1.22 | 2/2 | ✅ |
| perp | compra | parcial + móvel | estrutura_choch | 61 | 32.8% | -0.208 | 0.68 | 1/2 |  |
| perp | compra | parcial + móvel | lt_rompimento | 172 | 32.6% | -0.233 | 0.65 | 0/2 |  |
| perp | compra | parcial + móvel | medias_cruzamento | 169 | 44.4% | +0.069 | 1.14 | 2/2 |  |
| perp | venda | alvo 1R | todos | 1339 | 47.9% | -0.059 | 0.88 | 0/2 |  |
| perp | venda | alvo 1R | cunha | 124 | 46.0% | -0.127 | 0.78 | 0/2 |  |
| perp | venda | alvo 1R | estrutura_bos | 572 | 47.2% | -0.063 | 0.88 | 0/2 |  |
| perp | venda | alvo 1R | estrutura_choch | 102 | 47.1% | -0.065 | 0.87 | 0/2 |  |
| perp | venda | alvo 1R | lt_rompimento | 269 | 51.7% | +0.016 | 1.03 | 1/2 |  |
| perp | venda | alvo 1R | medias_cruzamento | 272 | 47.1% | -0.094 | 0.82 | 0/2 |  |
| perp | venda | alvo 2R | todos | 900 | 34.2% | -0.005 | 0.99 | 1/2 |  |
| perp | venda | alvo 2R | cunha | 74 | 35.1% | -0.016 | 0.98 | 1/2 |  |
| perp | venda | alvo 2R | estrutura_bos | 363 | 30.3% | -0.102 | 0.85 | 0/2 |  |
| perp | venda | alvo 2R | estrutura_choch | 76 | 30.3% | -0.140 | 0.79 | 0/2 |  |
| perp | venda | alvo 2R | lt_rompimento | 188 | 37.2% | +0.065 | 1.10 | 1/2 |  |
| perp | venda | alvo 2R | medias_cruzamento | 199 | 39.7% | +0.160 | 1.27 | 1/2 |  |
| perp | venda | parcial + móvel | todos | 1050 | 40.9% | -0.031 | 0.95 | 1/2 |  |
| perp | venda | parcial + móvel | cunha | 125 | 46.4% | +0.006 | 1.01 | 2/2 |  |
| perp | venda | parcial + móvel | estrutura_bos | 343 | 38.8% | -0.072 | 0.88 | 0/2 |  |
| perp | venda | parcial + móvel | estrutura_choch | 93 | 37.6% | -0.051 | 0.91 | 1/2 |  |
| perp | venda | parcial + móvel | lt_rompimento | 245 | 42.9% | -0.002 | 1.00 | 1/2 |  |
| perp | venda | parcial + móvel | medias_cruzamento | 244 | 40.2% | -0.016 | 0.97 | 0/2 |  |
