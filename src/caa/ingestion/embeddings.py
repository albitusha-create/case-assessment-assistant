"""Embed text with the Azure OpenAI deployment, using Entra ID (no API keys).

The OpenAI SDK talks to Azure's v1 endpoint (`<endpoint>/openai/v1/`). Passing
a token provider as `api_key` makes the SDK fetch a fresh Entra token for each
request instead of sending a static key.
"""

from collections.abc import Sequence

from azure.core.credentials import TokenCredential
from azure.identity import get_bearer_token_provider
from openai import OpenAI

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
BATCH_SIZE = 16


def make_openai_client(endpoint: str, credential: TokenCredential) -> OpenAI:
    token_provider = get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE)
    return OpenAI(base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=token_provider)


def embed_texts(client: OpenAI, deployment: str, texts: Sequence[str]) -> list[list[float]]:
    """Return one vector per text, in the same order. Batches keep requests small."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start : start + BATCH_SIZE])
        response = client.embeddings.create(model=deployment, input=batch)
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
    return vectors
