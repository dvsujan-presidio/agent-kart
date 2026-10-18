"""OpenAI models in Microsoft Foundry. Only place that builds an LLM client; config is env-only."""

import sys

from openai import AzureOpenAI

from app.config import get_settings


def endpoint() -> str:
    s = get_settings()
    if s.model_endpoint:
        return s.model_endpoint
    if not s.foundry_resource:
        raise RuntimeError("Set FOUNDRY_RESOURCE (see docs/azure-setup.md)")
    return f"https://{s.foundry_resource}.cognitiveservices.azure.com/"


def get_client() -> AzureOpenAI:
    s = get_settings()
    if not s.model_api_key:
        raise RuntimeError("Set MODEL_API_KEY (see docs/azure-setup.md)")
    return AzureOpenAI(
        azure_endpoint=endpoint(), api_key=s.model_api_key, api_version=s.model_api_version
    )


def deployment(fast: bool = False) -> str:
    s = get_settings()
    return s.model_deployment_fast if fast else s.model_deployment


def check() -> int:
    """`make check-model`: one tiny call to each distinct deployment."""
    client = get_client()
    for name in dict.fromkeys([deployment(True), deployment(False)]):
        resp = client.chat.completions.create(
            model=name,
            max_completion_tokens=512,  # reasoning models spend tokens thinking first
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        )
        choice = resp.choices[0]
        print(f"{name}: finish_reason={choice.finish_reason} text={choice.message.content!r}")
    return 0


if __name__ == "__main__":
    sys.exit(check())
