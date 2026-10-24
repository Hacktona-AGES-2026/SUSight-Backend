import json

import httpx
import pytest
from google import genai
from google.genai import types

from susight.tribunal.provider import GeminiProvider


async def test_gemini_sdk_structured_contract_without_network(monkeypatch):
    original = genai.Client
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        vote = {
            "agente": "evidencias",
            "veredito": "contra",
            "posicao_sugerida": None,
            "justificativa": "As evidencias ainda sao insuficientes para justificar a mudanca.",
            "evidencias_citadas": [],
            "sem_comprovacao": True,
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": json.dumps(vote)}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    def factory(**kwargs):
        return original(
            **kwargs,
            http_options=types.HttpOptions(async_client_args={"transport": httpx.MockTransport(respond)}),
        )

    monkeypatch.setattr(genai, "Client", factory)
    provider = GeminiProvider()
    provider.key = "synthetic-test-key"
    provider.model = "gemini-test-model"
    vote = await provider.analyze("evidencias", {"evidencias": []})
    assert vote.agente == "evidencias"
    config = seen[0]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    # The vote's keys are described in the prompt: the SDK refuses the closed-object schema of the model.
    assert "responseSchema" not in config and "responseJsonSchema" not in config
    assert "veredito" in seen[0]["contents"][0]["parts"][0]["text"]


async def test_missing_provider_configuration_never_simulates(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="nao configurado"):
        await GeminiProvider().analyze("evidencias", {})
