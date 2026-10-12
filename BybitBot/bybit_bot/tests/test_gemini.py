from __future__ import annotations

import json

import httpx
import pytest

from bot.ai.gemini_analyst import AccessToken, GeminiAnalyst, GeminiError, parse_verdict, system_prompt
from bot.config import load_config
from conftest import CONFIG_PATH

CLOCK = [1_791_000_000.0]
GOOD = {"veredito": "Cautela", "risco": "médio", "resumo": "Payroll amanhã às 09:30.",
        "eventos": [{"tipo": "agenda", "data": "2026-10-13 09:30", "descricao": "Payroll (NFP)", "fonte": None}],
        "confianca": 0.7}


def gemini_response(text: str, sources=("https://exemplo.com/noticia",)) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": "pensando...", "thought": True}, {"text": text}]},
                            "groundingMetadata": {"groundingChunks": [{"web": {"uri": u}} for u in sources]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 200}}


class FakeToken(AccessToken):
    def __init__(self):
        pass

    def get(self) -> str:
        return "tok"


def make(tmp_path, handler, **cfg_updates):
    cfg = load_config(CONFIG_PATH).gemini.model_copy(update={"calls_enabled": True, **cfg_updates})
    calls = []

    def recorder(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(recorder))
    return GeminiAnalyst(cfg, tmp_path, http=http, token=FakeToken(), clock=lambda: CLOCK[0]), calls


def ok_handler(request):
    return httpx.Response(200, json=gemini_response("```json\n" + json.dumps(GOOD) + "\n```"))


def test_analise_valida_com_pesquisa_e_auditoria(tmp_path):
    analyst, calls = make(tmp_path, ok_handler)
    a = analyst.analyze("mt5:XAUUSD.s:compra", "mt5", {"ativo": "XAUUSD", "direcao": "compra"})
    assert a.ok and a.verdict.veredito == "cautela" and a.verdict.risco == "medio"
    assert a.verdict.eventos[0].fonte == "https://exemplo.com/noticia"   # sem URL própria: 1ª fonte da pesquisa
    body = json.loads(calls[0].content)
    assert body["tools"] == [{"googleSearch": {}}]
    assert "agenda econômica" in body["systemInstruction"]["parts"][0]["text"]
    assert calls[0].headers["Authorization"] == "Bearer tok"
    assert calls[0].url.path.endswith("/locations/global/publishers/google/models/gemini-3.8-flash:generateContent")
    fields = a.panel_fields()
    assert fields["gemini_verdict"] == "cautela" and fields["gemini_events"][0]["tipo"] == "agenda"
    audit = (tmp_path / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit) == 1 and json.loads(audit[0])["usage"]["promptTokenCount"] == 900


def test_cache_evita_nova_chamada(tmp_path):
    analyst, calls = make(tmp_path, ok_handler)
    analyst.analyze("k", "cripto", {})
    again = analyst.analyze("k", "cripto", {})
    assert again.cached and len(calls) == 1
    CLOCK[0] += 7 * 3600            # passou do cache_hours (6 h)
    try:
        analyst.analyze("k", "cripto", {})
    finally:
        CLOCK[0] -= 7 * 3600
    assert len(calls) == 2


def test_teto_diario_nao_chama_e_vira_cautela(tmp_path):
    analyst, calls = make(tmp_path, ok_handler, max_calls_per_day=2)
    analyst.analyze("a", "cripto", {})
    analyst.analyze("b", "cripto", {})
    third = analyst.analyze("c", "cripto", {})
    assert len(calls) == 2 and analyst.calls_today() == 2
    assert not third.ok and third.verdict.veredito == "cautela" and "teto" in third.error


@pytest.mark.parametrize("response", [
    httpx.Response(200, json=gemini_response("não sei responder")),               # sem JSON
    httpx.Response(200, json=gemini_response('{"veredito": "talvez", "risco": "baixo"}')),  # fora do schema
    httpx.Response(500, text="erro interno"),
])
def test_falhas_viram_cautela(tmp_path, response):
    analyst, _ = make(tmp_path, lambda r: response)
    a = analyst.analyze("k", "cripto", {})
    assert not a.ok and a.verdict.veredito == "cautela"
    assert "Sem análise do Gemini" in a.panel_fields()["gemini_summary"]


def test_fail_closed_veta(tmp_path):
    analyst, _ = make(tmp_path, lambda r: httpx.Response(503, text="x"), on_failure="fail_closed")
    assert analyst.analyze("k", "cripto", {}).verdict.veredito == "vetado"


def test_timeout_vira_cautela(tmp_path):
    def boom(request):
        raise httpx.ReadTimeout("lento", request=request)

    analyst, _ = make(tmp_path, boom)
    a = analyst.analyze("k", "mt5", {})
    assert not a.ok and a.error == "ReadTimeout"


def test_desligado_nao_chama(tmp_path):
    analyst, calls = make(tmp_path, ok_handler, calls_enabled=False)
    assert analyst.analyze("k", "cripto", {}) is None and calls == []


def test_parse_e_prompts():
    v = parse_verdict('Resposta: {"veredito": "aprovado", "risco": "baixo", "resumo": "' + "x" * 500 + '"} fim')
    assert v.veredito == "aprovado" and len(v.resumo) == 400
    with pytest.raises(GeminiError):
        parse_verdict("sem json")
    assert "unlock" in system_prompt("cripto") and "14 dias" in system_prompt("cripto")
    assert "payroll" in system_prompt("mt5") and "hack" not in system_prompt("mt5")


def test_token_pelo_gcloud_fora_da_vm():
    def no_metadata(request):
        raise httpx.ConnectError("sem servidor de metadados", request=request)

    token = AccessToken(http=httpx.Client(transport=httpx.MockTransport(no_metadata)),
                        runner=lambda args: "ya29.token\n")
    assert token.get() == "ya29.token"
