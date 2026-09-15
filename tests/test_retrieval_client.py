import os

os.environ.setdefault("GEMINI_API_KEY", "test-key-for-unit-tests")

import httpx
import pytest
import respx

from app.config import settings
from app.exceptions import RetrievalClientError
from app.services.retrieval_client import RetrievalClient


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.post(f"{settings.retrieval_service_url}/api/v1/retrieve")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(500),
        httpx.Response(200, json=[{"id": "chunk1", "text": "hello"}]),
    ]

    client = RetrievalClient()
    result = await client.get_relevant_chunks("test query")

    assert result == [{"id": "chunk1", "text": "hello"}]
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_does_not_retry_on_4xx():
    route = respx.post(f"{settings.retrieval_service_url}/api/v1/retrieve")
    route.mock(return_value=httpx.Response(400, text="bad request"))

    client = RetrievalClient()
    with pytest.raises(RetrievalClientError):
        await client.get_relevant_chunks("test query")

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_raises_after_exhausting_retries_on_persistent_5xx():
    route = respx.post(f"{settings.retrieval_service_url}/api/v1/retrieve")
    route.mock(return_value=httpx.Response(503))

    client = RetrievalClient()
    with pytest.raises(RetrievalClientError):
        await client.get_relevant_chunks("test query")

    assert route.call_count == settings.retrieval_max_retries
