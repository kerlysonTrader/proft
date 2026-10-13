# ruff: noqa: E501, E741, B023, F841, E731
# (script de pesquisa, fora do código do robô: regras de estilo relaxadas)
"""Estudo: moedas recém-lançadas multiplicam o capital? (só dados públicos, sem chave, sem ordens)

Subcomandos (todos gravam em data/estudo_lancamentos/; o relatório sai em reports/):

    python src/bot/tools/estudo_lancamentos.py bybit-coletar      # instrumentos + velas de 1h (perps e spot)
    python src/bot/tools/estudo_lancamentos.py memes              # categoria "meme" da CoinGecko (pública)
    python src/bot/tools/estudo_lancamentos.py bybit-analisar     # métricas + simulações -> tabelas
    python src/bot/tools/estudo_lancamentos.py launchpad-coletar --horas 2   # pools novos (GeckoTerminal)
    python src/bot/tools/estudo_lancamentos.py launchpad-avaliar  # evolução do preço dos pools coletados
    python src/bot/tools/estudo_lancamentos.py relatorio          # monta reports/20261012_estudo_lancamentos.md

Não depende do pacote `bot`: usa só httpx, pandas e numpy. Nenhuma chamada exige chave; as APIs
públicas são limitadas por IP, então o script espaça as requisições e respeita 429.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]  # .../bybit_bot
DADOS = RAIZ / "data" / "estudo_lancamentos"
RELATORIOS = RAIZ / "reports"
HOJE = datetime.now(UTC)
JANELA_MESES = 24
INICIO_JANELA = datetime(HOJE.year - 2, HOJE.month, HOJE.day, tzinfo=UTC)  # ~24 meses atrás

UA = "estudo-lancamentos/0.1 (pesquisa pessoal; sem chave)"
BYBIT = "https://api.bybit.com"
GECKO_TERMINAL = "https://api.geckoterminal.com/api/v2"
COINGECKO = "https://api.coingecko.com/api/v3"

HORA_MS = 3_600_000
DIA_MS = 86_400_000


def agora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


class ClienteHTTP:
    """GET com espaçamento mínimo entre chamadas e retentativa em 429/5xx/rede."""

    def __init__(self, base: str, intervalo_s: float, timeout: float = 30.0) -> None:
        self.base = base
        self.intervalo = intervalo_s
        self.http = httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"}, timeout=timeout)
        self._ultimo = 0.0

    def get(self, caminho: str, params: dict | None = None, tentativas: int = 6) -> dict | list | None:
        for tentativa in range(tentativas):
            espera = self._ultimo + self.intervalo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.monotonic()
            try:
                r = self.http.get(self.base + caminho, params=params)
            except httpx.HTTPError as exc:
                log(f"rede: {exc!r} (tentativa {tentativa + 1})")
                time.sleep(5 * (tentativa + 1))
                continue
            if r.status_code == 429:
                pausa = min(90, 20 * (tentativa + 1))
                log(f"429 em {caminho[:60]} - aguardando {pausa}s")
                time.sleep(pausa)
                continue
            if r.status_code >= 500:
                time.sleep(5 * (tentativa + 1))
                continue
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                log(f"HTTP {r.status_code} em {caminho[:60]}: {r.text[:120]}")
                return None
            return r.json()
        return None


# --------------------------------------------------------------------------------------
# 1. LAUNCHPAD (GeckoTerminal) - coleta prospectiva de pools novos
# --------------------------------------------------------------------------------------

LP_ARQ = DADOS / "launchpad_pools.jsonl"
LP_OHLCV = DADOS / "launchpad_ohlcv"
# redes e páginas de new_pools por ciclo (cada página = 20 pools, ~8 min de atraso do feed)
LP_REDES = {"solana": 5, "bsc": 2, "base": 2}


def _pool_attrs(item: dict, dex_por_id: dict) -> dict:
    a = item["attributes"]
    rel = item.get("relationships", {})
    dex_id = rel.get("dex", {}).get("data", {}).get("id", "?")
    base_tok = rel.get("base_token", {}).get("data", {}).get("id", "")
    return {
        "pool_id": item["id"],
        "rede": item["id"].split("_", 1)[0],
        "endereco": a["address"],
        "dex": dex_por_id.get(dex_id, dex_id),
        "token": base_tok.split("_", 1)[-1],
        "nome": a.get("name"),
        "criado_em": a.get("pool_created_at"),
        "visto_em": agora_iso(),
        "preco_usd_visto": a.get("base_token_price_usd"),
        "fdv_usd_visto": a.get("fdv_usd"),
        "liquidez_usd_visto": a.get("reserve_in_usd"),
        "vol_h1_visto": (a.get("volume_usd") or {}).get("h1"),
    }


def cmd_launchpad_coletar(args: argparse.Namespace) -> int:
    DADOS.mkdir(parents=True, exist_ok=True)
    cli = ClienteHTTP(GECKO_TERMINAL, intervalo_s=2.6)
    vistos: set[str] = set()
    if LP_ARQ.exists():
        for linha in LP_ARQ.read_text(encoding="utf-8").splitlines():
            vistos.add(json.loads(linha)["pool_id"])
    fim = time.monotonic() + args.horas * 3600
    ciclo = 0
    log(f"coletor iniciado: {args.horas}h, {len(vistos)} pools já conhecidos")
    while time.monotonic() < fim:
        t0 = time.monotonic()
        novos = 0
        for rede, paginas in LP_REDES.items():
            for pag in range(1, paginas + 1):
                d = cli.get(f"/networks/{rede}/new_pools", {"page": pag, "include": "dex"})
                if not d:
                    continue
                dex_por_id = {x["id"]: x["attributes"]["name"] for x in d.get("included", []) if x["type"] == "dex"}
                linhas = []
                for item in d["data"]:
                    if item["id"] in vistos:
                        continue
                    vistos.add(item["id"])
                    linhas.append(_pool_attrs(item, dex_por_id))
                if linhas:
                    with LP_ARQ.open("a", encoding="utf-8") as f:
                        for ln in linhas:
                            f.write(json.dumps(ln, ensure_ascii=False) + "\n")
                    novos += len(linhas)
        ciclo += 1
        log(f"ciclo {ciclo}: +{novos} pools novos (total {len(vistos)})")
        resto = 120 - (time.monotonic() - t0)  # um ciclo a cada ~2 min
        if resto > 0 and time.monotonic() < fim:
            time.sleep(resto)
    log("coletor encerrado")
    return 0


# --------------------------------------------------------------------------------------
# 2. BYBIT - coleta (instrumentos, velas de 1h, idade da moeda na Binance)
# --------------------------------------------------------------------------------------

BY_DIR = DADOS / "bybit"
BY_VELAS = BY_DIR / "velas_1h"
BINANCE = "https://api.binance.com/api/v3"
DIAS_SEGUIR = 190  # 180 dias + folga
TIPOS_EXCLUIDOS = {"stock", "ETF", "commodity", "forex"}  # não são cripto recém-lançada


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _data(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def bybit_resultado(cli: ClienteHTTP, caminho: str, params: dict) -> dict | None:
    d = cli.get(caminho, params)
    if not d or d.get("retCode") != 0:
        return None
    return d["result"]


def listar_instrumentos(cli: ClienteHTTP, categoria: str, status: str | None = None) -> list[dict]:
    saida: list[dict] = []
    cursor = None
    while True:
        q: dict = {"category": categoria, "limit": 1000}
        if status:
            q["status"] = status
        if cursor:
            q["cursor"] = cursor
        r = bybit_resultado(cli, "/v5/market/instruments-info", q)
        if not r:
            break
        saida += r["list"]
        cursor = r.get("nextPageCursor")
        if not cursor:
            break
    return saida


def baixar_velas(cli: ClienteHTTP, categoria: str, simbolo: str, intervalo: str,
                 inicio_ms: int, fim_ms: int) -> pd.DataFrame:
    """Velas de [inicio, fim], paginando de trás para frente (a Bybit devolve as mais novas primeiro)."""
    linhas: list[list] = []
    fim_atual = fim_ms
    while True:
        r = bybit_resultado(cli, "/v5/market/kline", {"category": categoria, "symbol": simbolo, "interval": intervalo,
                                                       "start": inicio_ms, "end": fim_atual, "limit": 1000})
        lote = r["list"] if r else []
        if not lote:
            break
        linhas += lote
        mais_antigo = min(int(x[0]) for x in lote)
        if mais_antigo <= inicio_ms or len(lote) < 1000:
            break
        fim_atual = mais_antigo - 1
    if not linhas:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v", "turn"])
    df = pd.DataFrame(linhas, columns=["t", "o", "h", "l", "c", "v", "turn"]).astype(
        {"t": "int64", "o": "float64", "h": "float64", "l": "float64", "c": "float64", "v": "float64", "turn": "float64"})
    return df.drop_duplicates("t").sort_values("t").reset_index(drop=True)


def base_sem_multiplicador(base: str) -> str:
    """1000PEPE -> PEPE; 10000SATS -> SATS; 1INCH continua 1INCH."""
    i = 0
    while i < len(base) and base[i] == ("1" if i == 0 else "0"):
        i += 1
    if i >= 4 and i < len(base) and base[i].isalpha():  # 1 seguido de >=3 zeros e uma letra
        return base[i:]
    return base


def binance_primeira_vela(cli: ClienteHTTP, base: str) -> int | None:
    d = cli.get("/klines", {"symbol": f"{base}USDT", "interval": "1d", "startTime": 0, "limit": 1})
    if isinstance(d, list) and d:
        return int(d[0][0])
    return None


def cmd_bybit_coletar(args: argparse.Namespace) -> int:
    BY_VELAS.mkdir(parents=True, exist_ok=True)
    cli = ClienteHTTP(BYBIT, intervalo_s=0.11)
    inicio_ms = _ms(INICIO_JANELA)
    agora_ms = _ms(HOJE)

    # --- 1) perpétuos lineares USDT (ativos + deslistados) ---------------------------------
    arq_inst = BY_DIR / "instrumentos_linear.json.gz"
    if arq_inst.exists() and not args.refazer:
        inst = json.loads(gzip.open(arq_inst, "rt", encoding="utf-8").read())
    else:
        inst = listar_instrumentos(cli, "linear") + listar_instrumentos(cli, "linear", "Closed")
        with gzip.open(arq_inst, "wt", encoding="utf-8") as f:
            f.write(json.dumps(inst))
    log(f"instrumentos lineares: {len(inst)}")
    perps = [x for x in inst if x["contractType"] == "LinearPerpetual" and x["quoteCoin"] == "USDT"
             and int(x["launchTime"]) >= inicio_ms and x["status"] in ("Trading", "Closed")]
    excl = [x for x in perps if x.get("symbolType") in TIPOS_EXCLUIDOS]
    perps = [x for x in perps if x.get("symbolType") not in TIPOS_EXCLUIDOS]
    log(f"perps lançados na janela: {len(perps)} cripto (+{len(excl)} ações/ETF/commodities/forex excluídos)")
    pd.DataFrame([{
        "simbolo": x["symbol"], "base": x["baseCoin"], "base_limpa": base_sem_multiplicador(x["baseCoin"]),
        "lancamento_ms": int(x["launchTime"]), "status": x["status"], "entrega_ms": int(x["deliveryTime"] or 0),
        "tipo": x.get("symbolType") or "", "alavancagem_max": x["leverageFilter"]["maxLeverage"],
    } for x in perps]).to_csv(BY_DIR / "perps_selecionados.csv", index=False)

    # --- 2) spot: lançamentos na janela (ativos + candidatos deslistados via bases dos perps) ----
    spot_ativos = {x["symbol"]: x for x in listar_instrumentos(cli, "spot") if x["quoteCoin"] == "USDT"}
    bases_perps = {base_sem_multiplicador(x["baseCoin"]) for x in inst
                   if x["contractType"] == "LinearPerpetual" and x["quoteCoin"] == "USDT"
                   and x.get("symbolType") not in TIPOS_EXCLUIDOS}
    candidatos = sorted(set(spot_ativos) | {f"{b}USDT" for b in bases_perps})
    log(f"spot: {len(spot_ativos)} ativos, {len(candidatos)} candidatos a verificar")
    arq_spot = BY_DIR / "spot_lancamentos.csv"
    spot_rows: list[dict] = []
    feitos = pd.read_csv(arq_spot) if arq_spot.exists() and not args.refazer else pd.DataFrame()
    ja = set(feitos["simbolo"]) if len(feitos) else set()
    for i, sym in enumerate(candidatos):
        if sym in ja:
            continue
        # começa 40 dias antes da janela: se já havia vela nessa folga, a moeda não é lançamento da janela
        df = baixar_velas(cli, "spot", sym, "D", inicio_ms - 40 * DIA_MS, agora_ms)
        if df.empty:
            spot_rows.append({"simbolo": sym, "primeira_ms": 0, "n_dias": 0, "ativo": sym in spot_ativos})
        else:
            spot_rows.append({"simbolo": sym, "primeira_ms": int(df["t"].iloc[0]), "n_dias": len(df),
                              "ativo": sym in spot_ativos, "ultima_ms": int(df["t"].iloc[-1])})
        if (i + 1) % 100 == 0:
            log(f"  spot varredura {i + 1}/{len(candidatos)}")
    spot_df = pd.concat([feitos, pd.DataFrame(spot_rows)], ignore_index=True) if len(feitos) else pd.DataFrame(spot_rows)
    spot_df.to_csv(arq_spot, index=False)
    spot_sel = spot_df[(spot_df["n_dias"] > 0) & (spot_df["primeira_ms"] >= inicio_ms)]
    log(f"spot lançados na janela: {len(spot_sel)}")

    # --- 3) idade da moeda: primeira vela diária da Binance (spot) ---------------------------
    arq_bin = BY_DIR / "binance_idade.csv"
    bases = sorted({base_sem_multiplicador(x["baseCoin"]) for x in perps}
                   | {s[:-4] for s in spot_sel["simbolo"]})
    cli_bin = ClienteHTTP(BINANCE, intervalo_s=0.15)
    bin_df = pd.read_csv(arq_bin) if arq_bin.exists() and not args.refazer else pd.DataFrame(columns=["base", "binance_primeira_ms"])
    bin_ja = set(bin_df["base"])
    novos = []
    for b in bases:
        if b in bin_ja:
            continue
        novos.append({"base": b, "binance_primeira_ms": binance_primeira_vela(cli_bin, b) or 0})
    if novos:
        bin_df = pd.concat([bin_df, pd.DataFrame(novos)], ignore_index=True)
        bin_df.to_csv(arq_bin, index=False)
    log(f"idade Binance consultada para {len(bases)} moedas ({int((bin_df['binance_primeira_ms'] > 0).sum())} existem lá)")

    # --- 4) velas de 1h dos selecionados ---------------------------------------------------
    alvos: list[tuple[str, str, int, int]] = []
    for x in perps:
        lanc = int(x["launchTime"])
        fim = min(agora_ms, lanc + DIAS_SEGUIR * DIA_MS)
        if x["status"] == "Closed" and int(x["deliveryTime"] or 0) > 0:
            fim = min(fim, int(x["deliveryTime"]))  # com `end` depois da deslistagem a Bybit devolve lista vazia
        alvos.append(("linear", x["symbol"], lanc - HORA_MS, fim))
    for _, r in spot_sel.iterrows():
        fim = min(agora_ms, int(r["primeira_ms"]) + DIAS_SEGUIR * DIA_MS)
        if not r["ativo"] and r.get("ultima_ms", 0) > 0:
            fim = min(fim, int(r["ultima_ms"]) + DIA_MS)
        alvos.append(("spot", r["simbolo"], int(r["primeira_ms"]), fim))
    if args.inverter:  # segundo processo andando de trás para frente (acelera a coleta)
        alvos.reverse()
    log(f"baixando velas de 1h de {len(alvos)} símbolos")
    for i, (cat, sym, ini, fim) in enumerate(alvos):
        arq = BY_VELAS / f"{cat}_{sym}.csv.gz"
        if arq.exists() and not args.refazer:
            continue
        df = baixar_velas(cli, cat, sym, "60", ini, fim)
        if df.empty:
            log(f"  SEM VELAS para {sym} (não gravado; será tentado de novo)")
            continue
        df.to_csv(arq, index=False)
        if (i + 1) % 25 == 0:
            log(f"  velas {i + 1}/{len(alvos)} ({sym}: {len(df)} velas)")
    log("coleta Bybit concluída")
    return 0


# --------------------------------------------------------------------------------------
# 3. MEMES - categoria "meme" da CoinGecko (API pública, sem chave, ~10 chamadas/min)
# --------------------------------------------------------------------------------------

CG_CATEGORIAS = ["meme-token", "pump-fun-ecosystem", "four-meme-ecosystem"]


def cmd_memes(args: argparse.Namespace) -> int:
    BY_DIR.mkdir(parents=True, exist_ok=True)
    cli = ClienteHTTP(COINGECKO, intervalo_s=7.0)
    linhas: list[dict] = []
    for cat in CG_CATEGORIAS:
        for pag in range(1, 30):
            d = cli.get("/coins/markets", {"vs_currency": "usd", "category": cat, "order": "market_cap_desc",
                                           "per_page": 250, "page": pag})
            if not d:
                break
            for x in d:
                linhas.append({"categoria": cat, "id": x["id"], "simbolo": x["symbol"].upper(), "nome": x["name"],
                               "rank": x.get("market_cap_rank"), "mcap": x.get("market_cap")})
            log(f"{cat} pág {pag}: {len(d)} moedas (acum. {len(linhas)})")
            if len(d) < 250:
                break
    pd.DataFrame(linhas).to_csv(BY_DIR / "memes_coingecko.csv", index=False)
    log("memes salvos")
    return 0


# --------------------------------------------------------------------------------------
# 4. BYBIT - análise (métricas por moeda, estatísticas, simulações com taxas)
# --------------------------------------------------------------------------------------

JANELAS_DIAS = [1, 7, 30, 90, 180]
TAXA_SPOT = 0.001      # 0,1% por lado
TAXA_PERP = 0.00055    # 0,055% por lado (taker)
STOP_SHORT = 0.50      # stop de 50% acima da entrada
MM = 0.005             # margem de manutenção aproximada para estimar liquidação
SLIP_TESTE = 0.01      # 1% de derrapagem por lado (teste de sensibilidade)

# Marcação de memecoins: o símbolo da Bybit (sem o prefixo 1000) é cruzado com a categoria "meme-token" da
# CoinGecko. Símbolos repetem entre projetos, então só vale a correspondência quando a moeda da CoinGecko tem
# ranking de capitalização <= RANK_MAX_MEME (moedas minúsculas quase sempre são outro projeto com o mesmo
# símbolo) e o símbolo não está em NAO_MEMES (colisões que conheço, revisadas a olho). MEMES_EXTRA acrescenta
# memes que a CoinGecko não tem (moedas já mortas) ou que não achei pelo símbolo.
RANK_MAX_MEME = 5000
NAO_MEMES: set[str] = {"4STOCK", "AVA", "B", "BABY", "BASED", "KAT", "OPEN", "RONIN", "TA", "X", "NOM", "NIGHT"}
MEMES_EXTRA: set[str] = {"DOOD", "GORK", "JELLYJELLY", "NEIROCTO", "HAJIMI", "BOBBOB", "JAILSTOOL", "HPOS10I",
                         "LAUNCHCOIN", "PUMPFUN", "TSTBSC", "MEMEFI", "FWOG", "AI16Z"}


def carregar_velas(cat: str, sym: str) -> pd.DataFrame | None:
    arq = BY_VELAS / f"{cat}_{sym}.csv.gz"
    if not arq.exists():
        return None
    df = pd.read_csv(arq)
    return df if len(df) else None


def simular_moeda(df: pd.DataFrame, fim_dados_ms: int, delistada: bool, fund: np.ndarray | None = None) -> dict:
    """Todas as métricas de uma moeda, para as entradas A (abertura da 1ª vela), H (fechamento da 1ª hora)
    e B (fechamento de 24 h).

    Janela de N dias: A e H = comprar e vender no fechamento da hora 24N-1 (N dias desde o lançamento);
    B = comprar no fechamento da hora 23 e vender N dias depois (hora 24(N+1)-1).
    Moeda que parou de negociar antes do fim da janela (deslistada) sai no último fechamento.
    Janela que ainda não terminou para uma moeda viva fica de fora (censurada).
    """
    t0 = int(df["t"].iloc[0])
    k = ((df["t"].to_numpy() - t0) // HORA_MS).astype(int)
    o, h, l, c, turn = (df[x].to_numpy() for x in ("o", "h", "l", "c", "turn"))
    k_ult = int(k[-1])
    # os dados são cortados em DIAS_SEGUIR dias; "terminal" só vale para moeda deslistada/encerrada
    terminal = delistada and (int(df["t"].iloc[-1]) + HORA_MS) < fim_dados_ms - 3 * HORA_MS
    k_fim_dados = (fim_dados_ms - t0) // HORA_MS  # horas observáveis desde a 1ª vela
    out: dict = {"t0": t0, "horas_dados": k_ult + 1, "terminal": terminal,
                 "preco_ini": float(o[0]), "preco_ult": float(c[-1]),
                 "turn_1h": float(turn[k == 0].sum()), "turn_24h": float(turn[k < 24].sum()),
                 "turn_7d": float(turn[k < 168].sum()),
                 "alta_dia1": float(h[k < 24].max() / o[0] - 1), "queda_dia1": float(l[k < 24].min() / o[0] - 1)}

    def preco_em(kt: int) -> float:
        i = int(np.searchsorted(k, kt, side="right")) - 1
        return float(c[max(i, 0)])

    if k_fim_dados >= 24 and k_ult >= 1:
        # movimento do 1º dia depois da 1ª hora, em relação ao fechamento da 1ª hora (útil no spot, cuja abertura é artefato)
        dia1 = (k >= 1) & (k < 24)
        if dia1.any():
            out["alta_dia1_h"] = float(h[dia1].max() / c[0] - 1)
            out["queda_dia1_h"] = float(l[dia1].min() / c[0] - 1)
    for ent in ("A", "H", "B"):
        if ent == "A":
            k_ini, pe = 0, float(o[0])
        elif ent == "H":
            if k_ult < 1 or k_fim_dados < 2:
                continue
            k_ini, pe = 1, preco_em(0)
        else:
            if k_fim_dados < 24 or (k_ult < 23 and terminal):
                continue  # ainda sem 24h, ou morreu antes de completar o 1º dia
            k_ini, pe = 24, preco_em(23)
        out[f"pe_{ent}"] = pe
        for n in JANELAS_DIAS:
            k_fim = (24 * n - 1) if ent in ("A", "H") else (24 * (n + 1) - 1)
            if not terminal and (k_fim > k_fim_dados - 1 or k_fim > k_ult):
                continue  # janela ainda não completou (censurado)
            sel = (k >= k_ini) & (k <= k_fim)
            if not sel.any():
                continue
            hh, ll, oo = h[sel], l[sel], o[sel]
            px = preco_em(min(k_fim, k_ult))

            def saida_alta(limite: float) -> tuple[bool, float, int]:
                """Short com stop em +limite: sai no stop (ou na abertura, se houve gap acima)."""
                alvo = pe * (1 + limite)
                idx = np.nonzero(hh >= alvo)[0]
                if len(idx) == 0:
                    return False, px, -1
                i = int(idx[0])
                return True, max(alvo, float(oo[i])), i

            stop_hit, px_stop, i_stop = saida_alta(STOP_SHORT)
            liq_hit, _, _ = saida_alta(1 - MM)
            if fund is not None:
                def fsoma(k_a: int, k_b: int) -> float:
                    """Soma das taxas de funding pagas entre o início da hora k_a e o fim da hora k_b."""
                    m_ = (fund[:, 0] >= t0 + k_a * HORA_MS) & (fund[:, 0] < t0 + (k_b + 1) * HORA_MS)
                    return float(fund[m_, 1].sum())
                k_sai = min(k_fim, k_ult)
                out[f"{ent}{n}_fund"] = fsoma(k_ini, k_sai)
                out[f"{ent}{n}_fund_stop"] = fsoma(k_ini, int(k[sel][i_stop])) if stop_hit else out[f"{ent}{n}_fund"]
            pre = f"{ent}{n}"
            # long com alvo de +100% (ordem limite, executa no alvo ou na abertura se houver gap) e, na variante
            # com stop de -50%, o stop vence quando os dois caem na mesma vela (hipótese conservadora)
            i_tp = np.nonzero(hh >= pe * 2)[0]
            i_sl = np.nonzero(ll <= pe * 0.5)[0]
            ret_tp = max(1.0, float(oo[int(i_tp[0])]) / pe - 1) if len(i_tp) else px / pe - 1
            if len(i_tp) and (not len(i_sl) or i_tp[0] < i_sl[0]):
                ret_tpsl = ret_tp
            elif len(i_sl):
                ret_tpsl = min(-0.5, float(oo[int(i_sl[0])]) / pe - 1)
            else:
                ret_tpsl = px / pe - 1
            out[f"{pre}_ret_tp"] = ret_tp
            out[f"{pre}_ret_tpsl"] = ret_tpsl
            out[f"{pre}_ret"] = px / pe - 1
            out[f"{pre}_hi"] = float(hh.max() / pe - 1)
            out[f"{pre}_lo"] = float(ll.min() / pe - 1)
            out[f"{pre}_px"] = px
            out[f"{pre}_term"] = bool(terminal and k_fim > k_ult)
            out[f"{pre}_stop_hit"] = stop_hit
            out[f"{pre}_px_stop"] = px_stop
            out[f"{pre}_liq1x_hit"] = liq_hit
    return out


def wilson(x: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = x / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def boot_ic(x: np.ndarray, fn, reps: int = 3000, seed: int = 7) -> tuple[float, float]:
    if len(x) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    v = [fn(rng.choice(x, len(x), replace=True)) for _ in range(reps)]
    return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))


def pct(x: float, casas: int = 0) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{casas}f}%"


def pct_s(x: float, casas: int = 0) -> str:
    """Percentual com sinal explícito (retornos)."""
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.{casas}f}%"


def md_tabela(cabecalho: list[str], linhas: list[list]) -> str:
    sep = "|" + "|".join("---" for _ in cabecalho) + "|"
    corpo = ["| " + " | ".join(str(x) for x in ln) + " |" for ln in linhas]
    return "\n".join(["| " + " | ".join(cabecalho) + " |", sep] + corpo)


def montar_moedas() -> pd.DataFrame:
    """Une perps e spot em um DataFrame com as métricas de cada (instrumento, símbolo)."""
    perps = pd.read_csv(BY_DIR / "perps_selecionados.csv")
    spot_all = pd.read_csv(BY_DIR / "spot_lancamentos.csv")
    spot = spot_all[(spot_all["n_dias"] > 0) & (spot_all["primeira_ms"] >= _ms(INICIO_JANELA))]
    bin_df = pd.read_csv(BY_DIR / "binance_idade.csv").set_index("base")["binance_primeira_ms"].to_dict()
    spot_primeira = spot_all[spot_all["n_dias"] > 0].set_index("simbolo")["primeira_ms"].to_dict()
    itens = [("perp", r.simbolo, r.base_limpa, r.status) for r in perps.itertuples()]
    itens += [("spot", r.simbolo, r.simbolo[:-4], "Trading" if r.ativo else "Deslistada") for r in spot.itertuples()]
    cache: dict[tuple[str, str], pd.DataFrame] = {}
    fim = 0
    for inst, sym, _, _ in itens:
        df = carregar_velas("linear" if inst == "perp" else "spot", sym)
        if df is not None:
            cache[(inst, sym)] = df
            fim = max(fim, int(df["t"].iloc[-1]) + HORA_MS)
    linhas = []
    for inst, sym, base, st in itens:
        df = cache.get((inst, sym))
        if df is None:
            continue
        fund = None
        arq_f = BY_FUNDING / f"{sym}.csv.gz"
        if inst == "perp" and arq_f.exists():
            fd = pd.read_csv(arq_f)
            fund = fd[["t", "taxa"]].to_numpy(dtype=float) if len(fd) else np.zeros((0, 2))
        m = simular_moeda(df, fim, st in ("Closed", "Deslistada"), fund)
        m.update({"instrumento": inst, "simbolo": sym, "base": base, "status": st})
        # idade da moeda: primeira negociação conhecida na Binance (spot) ou no spot da Bybit
        refs = [x for x in (bin_df.get(base, 0), spot_primeira.get(f"{base}USDT", 0)) if x and x > 0]
        m["pre_existente"] = bool(refs and min(refs) < m["t0"] - 30 * DIA_MS)
        m["idade_ref_ms"] = min(refs) if refs else 0
        m["tem_spot_bybit"] = f"{base}USDT" in spot_primeira
        linhas.append(m)
    mo = pd.DataFrame(linhas)
    mo.attrs["fim_dados_ms"] = fim
    return mo


BY_FUNDING = BY_DIR / "funding"


def baixar_funding(cli: ClienteHTTP, simbolo: str, inicio_ms: int, fim_ms: int) -> pd.DataFrame:
    """Histórico de taxa de funding (200 por chamada, das mais novas para as mais antigas)."""
    linhas: list[tuple[int, float]] = []
    fim_atual = fim_ms
    while True:
        r = bybit_resultado(cli, "/v5/market/funding/history", {"category": "linear", "symbol": simbolo,
                                                                 "startTime": inicio_ms, "endTime": fim_atual, "limit": 200})
        lote = r["list"] if r else []
        if not lote:
            break
        linhas += [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in lote]
        mais_antigo = min(int(x["fundingRateTimestamp"]) for x in lote)
        if mais_antigo <= inicio_ms or len(lote) < 200:
            break
        fim_atual = mais_antigo - 1
    df = pd.DataFrame(linhas, columns=["t", "taxa"]).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return df


def cmd_bybit_funding(args: argparse.Namespace) -> int:
    BY_FUNDING.mkdir(parents=True, exist_ok=True)
    cli = ClienteHTTP(BYBIT, intervalo_s=0.11)
    inst = {x["symbol"]: x for x in json.loads(gzip.open(BY_DIR / "instrumentos_linear.json.gz", "rt", encoding="utf-8").read())}
    perps = pd.read_csv(BY_DIR / "perps_selecionados.csv")
    alvos = list(perps.itertuples())
    if args.inverter:
        alvos.reverse()
    agora_ms = _ms(HOJE)
    for i, r in enumerate(alvos):
        arq = BY_FUNDING / f"{r.simbolo}.csv.gz"
        if arq.exists():
            continue
        fim = min(agora_ms, int(r.lancamento_ms) + DIAS_SEGUIR * DIA_MS)
        if r.status == "Closed" and int(r.entrega_ms) > 0:
            fim = min(fim, int(r.entrega_ms))
        df = baixar_funding(cli, r.simbolo, int(r.lancamento_ms) - HORA_MS, fim)
        df.to_csv(arq, index=False)
        if (i + 1) % 25 == 0:
            log(f"  funding {i + 1}/{len(alvos)} ({r.simbolo}: {len(df)} registros)")
    log("funding concluído")
    return 0


def marcar_memes(mo: pd.DataFrame) -> pd.DataFrame:
    cg = pd.read_csv(BY_DIR / "memes_coingecko.csv")
    cg["simbolo"] = cg["simbolo"].astype(str).str.upper()
    aceitos = set(cg[cg["rank"].notna() & (cg["rank"] <= RANK_MAX_MEME)]["simbolo"])
    todos = set(cg["simbolo"])
    mo["meme_cg_bruto"] = mo["base"].str.upper().isin(todos)
    mo["meme_cg"] = mo["base"].str.upper().isin(aceitos)
    mo["meme"] = (mo["meme_cg"] & ~mo["base"].isin(NAO_MEMES)) | mo["base"].isin(MEMES_EXTRA)
    mo["prefixo_1000"] = mo["simbolo"].str.match(r"^10{3,}[A-Z]")
    return mo


def pnl_long(ret: np.ndarray, taxa: float, slip: float = 0.0) -> np.ndarray:
    """P&L em US$ de US$100 comprados (taxa já sai do valor investido) e vendidos."""
    return 100 * ((1 - taxa) ** 2 * (1 + ret) * ((1 - slip) / (1 + slip)) - 1)


def pnl_short(pe: np.ndarray, px: np.ndarray, taxa: float) -> np.ndarray:
    """Short de US$100 de nocional com US$100 de margem (1x): fecha comprando em px. Perda máxima = margem."""
    p = 100 * (1 - px / pe) - taxa * 100 * (1 + px / pe)
    return np.maximum(p, -100.0)


def resumo_pnl(p: np.ndarray) -> list:
    p = p[~np.isnan(p)]
    n = len(p)
    if n == 0:
        return ["0"] + ["-"] * 7
    ordenado = np.sort(p)[::-1]
    sem_top3 = ordenado[3:].mean() if n > 6 else float("nan")
    lo, hi = boot_ic(p, np.mean)
    return [n, f"{p.sum():+,.0f}", f"{p.mean():+.1f} [{lo:+.1f}; {hi:+.1f}]", f"{np.median(p):+.1f}",
            pct((p > 0).mean()), f"{ordenado[0]:+,.0f}", f"{p.min():+.0f}", f"{sem_top3:+.1f}"]


CAB_PNL = ["Cenário", "n", "Soma US$", "Média US$/trade [IC95%]", "Mediana", "% lucrativos", "Melhor", "Pior",
           "Média sem os 3 melhores"]


def estat(df: pd.DataFrame, ent: str, n: int) -> dict | None:
    col = f"{ent}{n}_ret"
    if col not in df:
        return None
    r = df[col].dropna().to_numpy()
    if len(r) == 0:
        return None
    lo, hi = boot_ic(r, np.mean)
    return {"n": len(r), "med": np.median(r), "media": r.mean(), "ic": (lo, hi),
            "p": np.percentile(r, [10, 25, 75, 90]), "abaixo": (r < 0).mean(), "ge2": (r >= 1).mean(), "perdeu50": (r <= -0.5).mean(), "ganhou": (r > 0).mean(),
            "term": float(df.loc[df[col].notna(), f"{ent}{n}_term"].mean())}


def tabela_janelas(df: pd.DataFrame, ent: str) -> str:
    linhas = []
    for n in JANELAS_DIAS:
        if ent == "B" and n == 1:
            continue
        e = estat(df, ent, n)
        if not e:
            continue
        linhas.append([f"{n} d", e["n"], pct_s(e["med"]), f"{pct_s(e['media'])} [{pct_s(e['ic'][0])}; {pct_s(e['ic'][1])}]",
                       pct_s(e["p"][0]), pct_s(e["p"][1]), pct_s(e["p"][2]), pct_s(e["p"][3]),
                       pct(e["abaixo"]), pct(e["perdeu50"]), pct(e["ge2"]), pct(e["term"])])
    return md_tabela(["Janela", "n", "Mediana", "Média [IC95%]", "P10", "P25", "P75", "P90",
                      "% abaixo da entrada", "% perdeu 50% ou mais", "% em 2× ou mais no fim", "% saiu por deslistagem"], linhas)


def tabela_multiplos(df: pd.DataFrame, ent: str) -> str:
    linhas = []
    for n in (30, 90, 180):
        hi = df[f"{ent}{n}_hi"].dropna() if f"{ent}{n}_hi" in df else pd.Series(dtype=float)
        if len(hi) == 0:
            continue
        cel = []
        for mult in (2, 5, 10):
            x = int((hi >= mult - 1).sum())
            lo, up = wilson(x, len(hi))
            cel.append(f"{pct(x / len(hi), 1)} ({x}) [{pct(lo)}-{pct(up)}]")
        linhas.append([f"{n} d", len(hi)] + cel)
    return md_tabela(["Dentro de", "n", "Tocou 2×", "Tocou 5×", "Tocou 10×"], linhas)


def tabela_extremos(df: pd.DataFrame, ent: str, n: int = 30) -> str:
    linhas = []
    for nome, col in (("Máxima alta (high/entrada − 1)", f"{ent}{n}_hi"), ("Máxima queda (low/entrada − 1)", f"{ent}{n}_lo")):
        x = df[col].dropna().to_numpy()
        if len(x) == 0:
            continue
        q = np.percentile(x, [10, 25, 50, 75, 90])
        linhas.append([nome, len(x)] + [pct_s(v) for v in q])
    return md_tabela([f"Primeiros {n} dias", "n", "P10", "P25", "Mediana", "P75", "P90"], linhas)


def linha_grupo(nome: str, df: pd.DataFrame, ent: str, n: int) -> list:
    e = estat(df, ent, n)
    if not e:
        return [nome, 0] + ["-"] * 6
    hi = df[f"{ent}{n}_hi"].dropna().to_numpy()
    return [nome, e["n"], pct_s(e["med"]), f"{pct_s(e['media'])} [{pct_s(e['ic'][0])}; {pct_s(e['ic'][1])}]",
            pct(e["abaixo"]), pct(e["ge2"]), pct((hi >= 1).mean()), pct((hi >= 4).mean())]


CAB_GRUPO = ["Grupo", "n", "Mediana", "Média [IC95%]", "% abaixo da entrada", "% em 2×+ no fim", "% tocou 2×", "% tocou 5×"]


ROTULO_ENT = {"A": "na abertura da 1ª vela", "H": "no fech. da 1ª hora", "B": "no fech. de 24 h"}
ENTRADAS = {"perp": ("A", "B"), "spot": ("H", "B")}


def cenarios_pnl(df: pd.DataFrame, inst: str, ent: str, n: int, shorts: bool) -> list[list]:
    taxa = TAXA_SPOT if inst == "spot" else TAXA_PERP
    col = f"{ent}{n}_ret"
    d = df[df[col].notna()]
    ret = d[col].to_numpy()
    pe = d[f"pe_{ent}"].to_numpy()
    linhas = [[f"Comprar {ROTULO_ENT[ent]}, segurar {n} d"] + resumo_pnl(pnl_long(ret, taxa))]
    if ent == "B":
        r_tp = d[f"{ent}{n}_ret_tp"].to_numpy()
        r_tpsl = d[f"{ent}{n}_ret_tpsl"].to_numpy()
        linhas.append([f"Comprar {ROTULO_ENT[ent]}, alvo +100% ou até {n} d"] + resumo_pnl(pnl_long(r_tp, taxa)))
        linhas.append([f"Comprar {ROTULO_ENT[ent]}, alvo +100% / stop −50% / até {n} d"] + resumo_pnl(pnl_long(r_tpsl, taxa)))
    if shorts:
        px = pe * (1 + ret)
        px_stop = d[f"{ent}{n}_px_stop"].to_numpy()
        liq = d[f"{ent}{n}_liq1x_hit"].astype(bool).to_numpy()
        stop_hit = d[f"{ent}{n}_stop_hit"].astype(bool).to_numpy()
        curto = pnl_short(pe, px, taxa)
        curto = np.where(liq, -100.0, curto)
        curto_stop = np.where(liq & ~stop_hit, -100.0, pnl_short(pe, px_stop, taxa))
        linhas.append([f"VENDER a descoberto {ROTULO_ENT[ent]}, {n} d, SEM stop"] + resumo_pnl(curto))
        linhas.append([f"VENDER a descoberto {ROTULO_ENT[ent]}, {n} d, stop +50%"] + resumo_pnl(curto_stop))
    return linhas


def tabela_funding(df: pd.DataFrame) -> str:
    """Efeito do funding (taxa paga entre comprados e vendidos a cada 1-8 h) sobre a média por operação, em US$."""
    linhas = []
    for ent in ("A", "B"):
        for n in (30, 90):
            col = f"{ent}{n}_fund"
            if col not in df:
                continue
            d = df[df[f"{ent}{n}_ret"].notna() & df[col].notna()]
            if len(d) == 0:
                continue
            ret = d[f"{ent}{n}_ret"].to_numpy()
            pe = d[f"pe_{ent}"].to_numpy()
            f = d[col].to_numpy()
            f_stop = d[f"{ent}{n}_fund_stop"].to_numpy()
            liq = d[f"{ent}{n}_liq1x_hit"].astype(bool).to_numpy()
            stop_hit = d[f"{ent}{n}_stop_hit"].astype(bool).to_numpy()
            px_stop = d[f"{ent}{n}_px_stop"].to_numpy()
            long0 = pnl_long(ret, TAXA_PERP)
            curto0 = np.where(liq, -100.0, pnl_short(pe, pe * (1 + ret), TAXA_PERP))
            stop0 = np.where(liq & ~stop_hit, -100.0, pnl_short(pe, px_stop, TAXA_PERP))
            curto1 = np.maximum(curto0 + 100 * f, -100.0)
            stop1 = np.maximum(stop0 + 100 * f_stop, -100.0)
            linhas.append([f"{ROTULO_ENT[ent]}, {n} d", len(d), pct_s(np.median(f), 2), pct_s(f.mean(), 2),
                           f"{long0.mean():+.1f} → {(long0 - 100 * f).mean():+.1f}",
                           f"{curto0.mean():+.1f} → {curto1.mean():+.1f}",
                           f"{stop0.mean():+.1f} → {stop1.mean():+.1f}"])
    return md_tabela(["Entrada e prazo", "n", "Funding acumulado (mediana)", "Funding acumulado (média)",
                      "Comprado: US$/trade sem → com funding", "Vendido sem stop: sem → com funding",
                      "Vendido com stop 50%: sem → com funding"], linhas)


def tabela_coortes_pnl(df: pd.DataFrame, ent: str = "B", n: int = 30) -> str:
    """P&L médio por semestre de lançamento: comprado, vendido sem stop e vendido com stop de 50%."""
    linhas = []
    for sem, g in list(df.groupby("semestre")) + [("Todos", df)]:
        d = g[g[f"{ent}{n}_ret"].notna()]
        if len(d) == 0:
            continue
        ret = d[f"{ent}{n}_ret"].to_numpy()
        pe = d[f"pe_{ent}"].to_numpy()
        liq = d[f"{ent}{n}_liq1x_hit"].astype(bool).to_numpy()
        stop_hit = d[f"{ent}{n}_stop_hit"].astype(bool).to_numpy()
        longo = pnl_long(ret, TAXA_PERP)
        curto = np.where(liq, -100.0, pnl_short(pe, pe * (1 + ret), TAXA_PERP))
        stop = np.where(liq & ~stop_hit, -100.0, pnl_short(pe, d[f"{ent}{n}_px_stop"].to_numpy(), TAXA_PERP))
        linhas.append([sem, len(d), f"{longo.mean():+.1f}", f"{curto.mean():+.1f}", pct((curto > 0).mean()),
                       f"{stop.mean():+.1f}", pct((stop > 0).mean())])
    return md_tabela(["Semestre de lançamento", "n", "Comprado (US$/trade)", "Vendido sem stop (US$/trade)",
                      "% lucrativos (sem stop)", "Vendido com stop 50% (US$/trade)", "% lucrativos (com stop)"], linhas)


def tabela_alavancagem(df: pd.DataFrame, ent: str = "B", n: int = 30) -> str:
    d = df[df[f"{ent}{n}_ret"].notna()]
    ret = d[f"{ent}{n}_ret"].to_numpy()
    hi = d[f"{ent}{n}_hi"].to_numpy()
    lo = d[f"{ent}{n}_lo"].to_numpy()
    linhas = []
    for lado in ("comprado", "vendido"):
        for alav in (2, 3, 5, 10, 20):
            lim = 1 / alav - MM
            if lado == "comprado":
                liq = lo <= -lim
                bruto = alav * ret
            else:
                liq = hi >= lim
                bruto = -alav * ret
            taxas = TAXA_PERP * alav * (1 + (1 + ret))
            p = np.where(liq, -100.0, np.maximum(100 * (bruto - taxas), -100.0))
            linhas.append([lado, f"{alav}×", pct(liq.mean()), f"{p.mean():+.1f}", f"{np.median(p):+.1f}", pct((p > 0).mean()), f"{p.sum():+,.0f}"])
    return md_tabela(["Lado", "Alavancagem", "% liquidado em 30 d", "Média US$/trade", "Mediana", "% lucrativos", "Soma US$ (n=" + str(len(d)) + ")"], linhas)


def semestre(ms: int) -> str:
    d = datetime.fromtimestamp(ms / 1000, UTC)
    return f"{d.year}-S{1 if d.month <= 6 else 2}"


def tabela_liquidez(df: pd.DataFrame, ref: str = "A") -> str:
    linhas = []
    for nome, col in (("Volume negociado na 1ª hora (US$)", "turn_1h"), ("Volume nas primeiras 24 h (US$)", "turn_24h"),
                      ("Volume nos primeiros 7 dias (US$)", "turn_7d")):
        q = np.percentile(df[col].dropna(), [10, 25, 50, 75, 90])
        linhas.append([nome] + [f"{v:,.0f}" for v in q])
    if ref == "A":
        for nome, col in (("Alta máx. do 1º dia sobre a abertura", "alta_dia1"), ("Queda máx. do 1º dia sobre a abertura", "queda_dia1")):
            q = np.percentile(df[col].dropna(), [10, 25, 50, 75, 90])
            linhas.append([nome] + [pct_s(v) for v in q])
    else:
        for nome, col in (("Fechamento da 1ª hora sobre a abertura da 1ª vela (artefato do leilão)", None),
                          ("Alta máx. do 1º dia (após a 1ª hora) sobre o fech. da 1ª hora", "alta_dia1_h"),
                          ("Queda máx. do 1º dia (após a 1ª hora) sobre o fech. da 1ª hora", "queda_dia1_h")):
            x = (df["pe_H"] / df["pe_A"] - 1) if col is None else df[col]
            q = np.percentile(x.dropna(), [10, 25, 50, 75, 90])
            linhas.append([nome] + [pct_s(v) for v in q])
    gap = (df["pe_B"] / df[f"pe_{ref}"] - 1).dropna().to_numpy()
    q = np.percentile(gap, [10, 25, 50, 75, 90])
    nome_ref = "abertura" if ref == "A" else "fechamento da 1ª hora"
    linhas.append([f"Fechamento de 24 h sobre {nome_ref}"] + [pct_s(v) for v in q])
    return md_tabela(["Métrica", "P10", "P25", "Mediana", "P75", "P90"], linhas)


def cmd_bybit_analisar(args: argparse.Namespace) -> int:
    mo = montar_moedas()
    mo = marcar_memes(mo)
    fim = mo.attrs["fim_dados_ms"]
    mo["semestre"] = mo["t0"].map(semestre)
    mo.to_csv(DADOS / "moedas_metricas.csv", index=False)
    T: dict[str, str] = {}
    perp = mo[mo["instrumento"] == "perp"]
    spot = mo[mo["instrumento"] == "spot"]
    T["data_fim"] = _data(fim)
    T["n_perp"] = str(len(perp))
    T["n_spot"] = str(len(spot))

    # amostra
    def cont(d: pd.DataFrame) -> list:
        return [len(d), int((d["status"] == "Trading").sum()), int(d["terminal"].sum()), int(d["meme"].sum()),
                int((~d["meme"]).sum()), int((~d["pre_existente"]).sum()), int(d["pre_existente"].sum())]
    T["amostra"] = md_tabela(["Amostra", "Moedas", "Ainda negociando", "Deslistadas/encerradas", "Memecoins", "Não memes",
                              "Lançamento aparente", "Já negociava antes (>30 d)"],
                             [["Perpétuos USDT", *cont(perp)], ["Spot USDT", *cont(spot)]])
    for nome, d in (("perp", perp), ("spot", spot)):
        for ent in (("A", "B") if nome == "perp" else ("A", "H", "B")):
            T[f"janelas_{nome}_{ent}"] = tabela_janelas(d, ent)
            T[f"multiplos_{nome}_{ent}"] = tabela_multiplos(d, ent)
            T[f"extremos_{nome}_{ent}"] = tabela_extremos(d, ent)

    # memes x não memes x novos
    for nome, d in (("perp", perp), ("spot", spot)):
        for ent in ENTRADAS[nome]:
            for n in (7, 30, 90):
                linhas = [linha_grupo("Todas", d, ent, n), linha_grupo("Memecoins", d[d["meme"]], ent, n),
                          linha_grupo("Não memes", d[~d["meme"]], ent, n),
                          linha_grupo("Lançamento aparente (sem negociação prévia conhecida)", d[~d["pre_existente"]], ent, n),
                          linha_grupo("Já negociava antes", d[d["pre_existente"]], ent, n),
                          linha_grupo("Memecoins + lançamento aparente", d[d["meme"] & ~d["pre_existente"]], ent, n),
                          linha_grupo("Não memes + lançamento aparente", d[~d["meme"] & ~d["pre_existente"]], ent, n),
                          linha_grupo("Memecoins, critério largo (qualquer símbolo igual ao de um meme da CoinGecko)", d[d["meme_cg_bruto"] | d["meme"]], ent, n),
                          linha_grupo("Só as ainda listadas hoje (o que veria quem ignora as deslistadas)", d[d["status"] == "Trading"], ent, n),
                          linha_grupo("Só as deslistadas", d[d["status"] != "Trading"], ent, n)]
                T[f"grupos_{nome}_{ent}{n}"] = md_tabela(CAB_GRUPO, linhas)

    # simulações
    for nome, d, shorts in (("perp", perp, True), ("spot", spot, False)):
        for sub, dd in (("todas", d), ("memes", d[d["meme"]]), ("naomemes", d[~d["meme"]]), ("novas", d[~d["pre_existente"]])):
            linhas = []
            for ent in ENTRADAS[nome]:
                for n in (30, 90):
                    if f"{ent}{n}_ret" in dd:
                        linhas += cenarios_pnl(dd, nome, ent, n, shorts)
            T[f"sim_{nome}_{sub}"] = md_tabela(CAB_PNL, linhas)
        # sensibilidade a derrapagem na entrada B
        dd = d[d["B30_ret"].notna()]
        r = dd["B30_ret"].to_numpy()
        taxa = TAXA_SPOT if nome == "spot" else TAXA_PERP
        T[f"slip_{nome}"] = md_tabela(CAB_PNL, [["Long B 30 d, sem derrapagem"] + resumo_pnl(pnl_long(r, taxa)),
                                                ["Long B 30 d, derrapagem 1%/lado"] + resumo_pnl(pnl_long(r, taxa, SLIP_TESTE))])
    if "B30_fund" in perp:
        T["funding_perp"] = tabela_funding(perp)
        T["funding_perp_memes"] = tabela_funding(perp[perp["meme"]])
    T["coortes_pnl_B30"] = tabela_coortes_pnl(perp, "B", 30)
    T["coortes_pnl_B90"] = tabela_coortes_pnl(perp, "B", 90)
    T["alavancagem_perp_B30"] = tabela_alavancagem(perp, "B", 30)
    T["alavancagem_perp_A30"] = tabela_alavancagem(perp, "A", 30)
    T["alavancagem_memes_B30"] = tabela_alavancagem(perp[perp["meme"]], "B", 30)

    # coortes por semestre e liquidez
    linhas = []
    for sem, d in perp.groupby("semestre"):
        linhas.append(linha_grupo(sem, d, "B", 30))
    T["coortes_perp_B30"] = md_tabela(["Semestre de lançamento"] + CAB_GRUPO[1:], linhas)
    linhas = []
    for sem, d in perp.groupby("semestre"):
        linhas.append(linha_grupo(sem, d, "A", 30))
    T["coortes_perp_A30"] = md_tabela(["Semestre de lançamento"] + CAB_GRUPO[1:], linhas)
    T["liquidez_perp"] = tabela_liquidez(perp[perp["pe_B"].notna()], "A")
    T["liquidez_spot"] = tabela_liquidez(spot[spot["pe_B"].notna()], "H")

    # melhores e piores (B, 30 d) para ilustrar
    d = perp[perp["B30_ret"].notna()].sort_values("B30_ret", ascending=False)
    cols = lambda x: [x.simbolo, "sim" if x.meme else "não", "sim" if x.pre_existente else "não", _data(int(x.t0)),
                      pct_s(x.B30_ret), pct_s(x.B30_hi), pct_s(x.B30_lo), f"{x.turn_24h:,.0f}"]
    cab = ["Símbolo", "Meme?", "Já existia?", "Lançada em", "Retorno 30 d (B)", "Máxima alta", "Máxima queda", "Volume 24 h (US$)"]
    T["melhores_perp"] = md_tabela(cab, [cols(x) for x in d.head(12).itertuples()])
    T["piores_perp"] = md_tabela(cab, [cols(x) for x in d.tail(8).iloc[::-1].itertuples()])

    T["lista_memes"] = ", ".join(sorted(set(mo[mo["meme"]]["base"])))
    T["lista_pre_existente"] = ", ".join(sorted(set(mo[mo["pre_existente"]]["base"])))
    (DADOS / "tabelas.json").write_text(json.dumps(T, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"tabelas salvas ({len(T)}); fim dos dados {T['data_fim']}")
    for k_ in ("amostra", "janelas_perp_B", "janelas_perp_A"):
        print(f"\n## {k_}\n{T[k_]}")
    return 0


# --------------------------------------------------------------------------------------
# 5. LAUNCHPAD - avaliação dos pools coletados (velas de 5 min da GeckoTerminal)
# --------------------------------------------------------------------------------------

LP_HORIZONTES_H = [1, 2, 3, 6, 24]
LP_ATRASO_MIN = 15  # "entrada realista": comprar 15 min depois da criação do pool
LP_TAXA = 0.01  # 1% por lado (taxa típica da curva da pump.fun); sem derrapagem nem taxa de prioridade


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def lp_velas(cli: ClienteHTTP, p: dict) -> list | None:
    LP_OHLCV.mkdir(parents=True, exist_ok=True)
    arq = LP_OHLCV / (p["pool_id"] + ".json")
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    d = cli.get(f"/networks/{p['rede']}/pools/{p['endereco']}/ohlcv/minute",
                {"aggregate": 5, "limit": 1000, "currency": "usd"})
    if d is None:
        return None
    lista = d["data"]["attributes"]["ohlcv_list"]
    arq.write_text(json.dumps({"coletado_em": time.time(), "velas": lista}), encoding="utf-8")
    return {"coletado_em": time.time(), "velas": lista}


def lp_metricas(p: dict, vel: dict) -> dict:
    criado = _ts(p["criado_em"])
    agora = vel["coletado_em"]
    v = sorted(vel["velas"], key=lambda x: x[0])
    idade_h = (agora - criado) / 3600
    m: dict = {"pool_id": p["pool_id"], "rede": p["rede"], "dex": p["dex"], "idade_h": idade_h, "n_velas": len(v)}
    if not v or v[0][0] > criado + 30 * 60:
        m["sem_negociacao"] = True
        return m
    m["sem_negociacao"] = False
    ts = np.array([x[0] for x in v], dtype=float)
    o, h, l, c = (np.array([x[i] for x in v], dtype=float) for i in (1, 2, 3, 4))

    def preco_ate(t_fim: float) -> float | None:
        """Fechamento da última vela de 5 min que termina até t_fim."""
        i = int(np.searchsorted(ts + 300, t_fim, side="right")) - 1
        return float(c[i]) if i >= 0 else None

    p0 = float(o[0])
    pe = preco_ate(criado + LP_ATRASO_MIN * 60)
    if pe is None:
        pe = float(c[0])
    m["p0"], m["pe"] = p0, pe
    m["alta_ate_entrada"] = float(h[ts < criado + LP_ATRASO_MIN * 60].max() / p0 - 1) if (ts < criado + LP_ATRASO_MIN * 60).any() else 0.0
    m["pe_sobre_p0"] = pe / p0 - 1
    sup = None
    try:
        sup = float(p["fdv_usd_visto"]) / float(p["preco_usd_visto"])
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    m["fdv_pico"] = float(h.max() * sup) if sup else None
    m["ultima_vela_min"] = (agora - float(ts[-1])) / 60
    for hz in LP_HORIZONTES_H:
        if idade_h < hz + 0.05:
            continue
        t_fim = criado + hz * 3600
        px = preco_ate(t_fim)
        janela = (ts >= criado + LP_ATRASO_MIN * 60 - 300) & (ts < t_fim)
        m[f"ret_{hz}h"] = px / pe - 1 if px else None
        m[f"alta_{hz}h"] = float(h[janela].max() / pe - 1) if janela.any() else None
        m[f"queda_{hz}h"] = float(l[janela].min() / pe - 1) if janela.any() else None
        m[f"ret_{hz}h_p0"] = px / p0 - 1 if px else None
        m[f"alta_{hz}h_p0"] = float(h[ts < t_fim].max() / p0 - 1)
    return m


def cmd_launchpad_avaliar(args: argparse.Namespace) -> int:
    pools = [json.loads(x) for x in LP_ARQ.read_text(encoding="utf-8").splitlines()]
    agora = time.time()
    elegiveis = [p for p in pools if p["rede"] in args.redes and (agora - _ts(p["criado_em"])) / 3600 >= args.idade_min_h]
    log(f"{len(pools)} pools coletados; {len(elegiveis)} com idade >= {args.idade_min_h}h nas redes {args.redes}")
    rng = random.Random(42)
    por_rede: dict[str, list] = {}
    for p in elegiveis:
        por_rede.setdefault(p["rede"], []).append(p)
    amostra: list[dict] = []
    for rede, lst in por_rede.items():
        rng.shuffle(lst)
        amostra += lst[: args.amostra if rede == "solana" else args.amostra_outras]
    log(f"amostra a avaliar: {len(amostra)} pools")
    cli = ClienteHTTP(GECKO_TERMINAL, intervalo_s=2.6)
    linhas = []
    for i, p in enumerate(amostra):
        vel = lp_velas(cli, p)
        if vel is None:
            continue
        linhas.append(lp_metricas(p, vel))
        if (i + 1) % 25 == 0:
            log(f"  avaliados {i + 1}/{len(amostra)}")
    df = pd.DataFrame(linhas)
    df.to_csv(DADOS / "launchpad_metricas.csv", index=False)
    log(f"métricas salvas: {len(df)} pools")
    return 0


LP_OUTROS_LAUNCHPADS = ("meteora dbc", "launchlab", "letsbonk", "stonkfun", "bankr", "moonshot", "boop", "bags", "moonit",
                        "wavebreak", "heaven", "token mill", "zora", "clanker", "believe")


def lp_grupo(dex: str) -> str:
    d = str(dex).lower()
    if d == "pump.fun":
        return "pump.fun (Solana)"
    if d == "four.meme":
        return "Four.meme (BSC)"
    if any(x in d for x in LP_OUTROS_LAUNCHPADS):
        return "Outros launchpads (Meteora DBC, LaunchLab, letsbonk, ...)"
    return "Pools de AMM (Uniswap, Pancake, PumpSwap, Meteora DAMM, ...)"


def resumo_launchpad(df: pd.DataFrame) -> dict[str, str]:
    """Tabelas em markdown a partir de launchpad_metricas.csv."""
    T: dict[str, str] = {}
    df = df.copy()
    df["grupo"] = df["dex"].map(lp_grupo)
    com = df[~df["sem_negociacao"].astype(bool)]
    T["lp_n"] = str(len(df))
    T["lp_n_com_negociacao"] = str(len(com))
    ordem = ["pump.fun (Solana)", "Four.meme (BSC)", "Outros launchpads (Meteora DBC, LaunchLab, letsbonk, ...)",
             "Pools de AMM (Uniswap, Pancake, PumpSwap, Meteora DAMM, ...)"]
    grupos = [("Todos os launchpads (3 primeiras linhas)", com[com["grupo"].isin(ordem[:3])])] + [(g, com[com["grupo"] == g]) for g in ordem]
    # composição e abandono
    linhas = []
    for g in ordem:
        d = df[df["grupo"] == g]
        c = d[~d["sem_negociacao"].astype(bool)]
        if len(d) == 0:
            continue
        linhas.append([g, len(d), pct(1 - len(c) / len(d)), pct((c["n_velas"] <= 3).mean()) if len(c) else "-",
                       pct((c["ultima_vela_min"] > 60).mean()) if len(c) else "-",
                       f"{c['idade_h'].median():.1f} h" if len(c) else "-"])
    T["lp_composicao"] = md_tabela(["Tipo de pool", "Pools avaliados", "% sem nenhuma negociação nos primeiros 30 min",
                                    "% com ≤ 3 velas de 5 min em toda a vida (≈ morreu em minutos)",
                                    "% sem negociação há mais de 1 h", "Idade mediana na avaliação"], linhas)
    linhas = []
    for nome, d in grupos:
        for hz in LP_HORIZONTES_H:
            col = f"ret_{hz}h"
            if col not in d:
                continue
            r = d[col].dropna().to_numpy()
            if len(r) < 8:
                continue
            a = d[f"alta_{hz}h"].dropna().to_numpy()
            lo, up = boot_ic(r, np.mean)
            linhas.append([nome, f"{hz} h", len(r), pct_s(np.median(r)), f"{pct_s(r.mean())} [{pct_s(lo)}; {pct_s(up)}]",
                           pct((r < -0.001).mean()), pct((r <= -0.5).mean()), pct((r <= -0.9).mean()),
                           pct((a >= 1).mean()), pct((a >= 4).mean()), pct((a >= 9).mean())])
    T["lp_entrada15"] = md_tabela(["Grupo", "Horizonte (desde a criação)", "n", "Mediana", "Média [IC95%]", "% abaixo da entrada",
                                   "% −50% ou pior", "% −90% ou pior", "% tocou 2×", "% tocou 5×", "% tocou 10×"], linhas)
    linhas = []
    for nome, d in grupos[:3]:
        for hz in LP_HORIZONTES_H:
            col = f"ret_{hz}h"
            if col not in d:
                continue
            r = d[col].dropna().to_numpy()
            if len(r) < 8:
                continue
            linhas.append([f"{nome} — vender {hz} h após a criação"] + resumo_pnl(pnl_long(r, LP_TAXA)))
    T["lp_pnl"] = md_tabela(CAB_PNL, linhas)
    linhas = []
    for nome, d in grupos[:2]:
        for hz in LP_HORIZONTES_H:
            col = f"ret_{hz}h_p0"
            if col not in d:
                continue
            r = d[col].dropna().to_numpy()
            if len(r) < 8:
                continue
            a = d[f"alta_{hz}h_p0"].dropna().to_numpy()
            linhas.append([nome, f"{hz} h", len(r), pct_s(np.median(r)), pct((r < -0.001).mean()), pct((r <= -0.9).mean()),
                           pct((a >= 1).mean()), pct((a >= 4).mean()), pct((a >= 9).mean())])
    T["lp_entrada_p0"] = md_tabela(["Grupo", "Horizonte", "n", "Mediana", "% abaixo do 1º preço", "% −90% ou pior",
                                    "% tocou 2×", "% tocou 5×", "% tocou 10×"], linhas)
    pe = com[com["grupo"].isin(ordem[:3])]["pe_sobre_p0"].dropna().to_numpy()
    if len(pe):
        T["lp_pe_sobre_p0"] = (f"mediana {pct_s(np.median(pe))}, média {pct_s(pe.mean())}; "
                               f"{pct((pe > 1).mean())} já estavam 2× acima do 1º preço aos {LP_ATRASO_MIN} min")
    linhas = []
    for g in ordem[:3]:
        c = com[com["grupo"] == g]
        fdv = c["fdv_pico"].dropna().to_numpy()
        if len(fdv) < 8:
            continue
        linhas.append([g, len(fdv), f"{np.median(fdv):,.0f}"] + [pct((fdv >= x).mean(), 1) for x in (10_000, 50_000, 100_000, 500_000, 1_000_000)])
    T["lp_fdv_pico"] = md_tabela(["Grupo", "n", "FDV de pico mediano (US$)", "≥ US$ 10 mil", "≥ US$ 50 mil", "≥ US$ 100 mil",
                                  "≥ US$ 500 mil", "≥ US$ 1 milhão"], linhas)
    return T


def cmd_launchpad_resumo(args: argparse.Namespace) -> int:
    df = pd.read_csv(DADOS / "launchpad_metricas.csv")
    T = resumo_launchpad(df)
    (DADOS / "tabelas_launchpad.json").write_text(json.dumps(T, ensure_ascii=False, indent=1), encoding="utf-8")
    for k_, v in T.items():
        print(f"\n## {k_}\n{v}")
    return 0


# --------------------------------------------------------------------------------------
# 6. RELATÓRIO - preenche o modelo com as tabelas calculadas
# --------------------------------------------------------------------------------------

def cmd_relatorio(args: argparse.Namespace) -> int:
    import re
    valores: dict[str, str] = {}
    for nome in ("tabelas.json", "tabelas_launchpad.json"):
        arq = DADOS / nome
        if arq.exists():
            valores.update(json.loads(arq.read_text(encoding="utf-8")))
    for nome, chave in (("fontes_launchpad.md", "fontes_launchpad"), ("lp_texto.md", "lp_texto"),
                        ("lp_resumo_curto.txt", "lp_resumo_curto")):
        arq = DADOS / nome
        if arq.exists():
            valores[chave] = arq.read_text(encoding="utf-8").strip()
    texto = (DADOS / "relatorio_modelo.md").read_text(encoding="utf-8")
    for _ in range(3):  # os blocos de texto também podem conter marcadores
        texto = re.sub(r"\{\{(\w+)\}\}", lambda m: valores.get(m.group(1), m.group(0)), texto)
    faltando = sorted(set(re.findall(r"\{\{(\w+)\}\}", texto)))
    saida = RELATORIOS / f"{HOJE.strftime('%Y%m%d')}_estudo_lancamentos.md"
    saida.write_text(texto, encoding="utf-8")
    log(f"relatório gravado em {saida} ({len(texto):,} caracteres)")
    if faltando:
        log(f"ATENÇÃO: marcadores sem valor: {faltando}")
    return 0


# --------------------------------------------------------------------------------------
# entrada
# --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Estudo de lançamentos de moedas (dados públicos)")
    sub = p.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("launchpad-coletar", help="coleta pools novos (GeckoTerminal)")
    lp.add_argument("--horas", type=float, default=2.0)
    lp.set_defaults(fn=cmd_launchpad_coletar)
    bc = sub.add_parser("bybit-coletar", help="instrumentos e velas de 1h da Bybit")
    bc.add_argument("--refazer", action="store_true", help="ignora o cache em disco")
    bc.add_argument("--inverter", action="store_true", help="baixa as velas em ordem inversa")
    bc.set_defaults(fn=cmd_bybit_coletar)
    bf = sub.add_parser("bybit-funding", help="histórico de funding dos perpétuos")
    bf.add_argument("--inverter", action="store_true")
    bf.set_defaults(fn=cmd_bybit_funding)
    ba = sub.add_parser("bybit-analisar", help="métricas, estatísticas e simulações da Bybit")
    ba.set_defaults(fn=cmd_bybit_analisar)
    la = sub.add_parser("launchpad-avaliar", help="evolução do preço dos pools coletados")
    la.add_argument("--idade-min-h", type=float, default=3.0)
    la.add_argument("--amostra", type=int, default=400, help="máx. de pools Solana avaliados")
    la.add_argument("--amostra-outras", type=int, default=80, help="máx. de pools por rede não-Solana")
    la.add_argument("--redes", nargs="+", default=["solana", "bsc", "base"])
    la.set_defaults(fn=cmd_launchpad_avaliar)
    lr = sub.add_parser("launchpad-resumo", help="tabelas do launchpad a partir de launchpad_metricas.csv")
    lr.set_defaults(fn=cmd_launchpad_resumo)
    rl = sub.add_parser("relatorio", help="preenche relatorio_modelo.md e grava em reports/")
    rl.set_defaults(fn=cmd_relatorio)
    mm = sub.add_parser("memes", help="lista de memecoins da CoinGecko")
    mm.set_defaults(fn=cmd_memes)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
