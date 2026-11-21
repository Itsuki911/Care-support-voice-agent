"""Unit tests for Tavily WebSearchTools and TavilyClient."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from livekit.agents import ToolError
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from approvals import ApprovalManager
from web_search_tools import TavilyClient, WebSearchError, WebSearchTools


def test_tavily_client_parses_results_and_records_fetched_at():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tvly-test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["query"] == "介護保険 最新"
        assert body["max_results"] == 2
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "厚生労働省 介護保険",
                        "url": "https://www.mhlw.go.jp/example",
                        "content": "制度の概要テキスト",
                        "score": 0.91234,
                    }
                ]
            },
        )

    client = TavilyClient(api_key="tvly-test-key", transport=httpx.MockTransport(handler))
    result = asyncio.run(client.search("介護保険 最新", max_results=2))
    assert result["provider"] == "tavily"
    assert result["count"] == 1
    assert result["fetched_at"]
    assert result["results"][0]["url"] == "https://www.mhlw.go.jp/example"
    assert result["results"][0]["score"] == 0.9123


def test_tavily_client_safe_error_never_leaks_api_key():
    secret = "tvly-super-secret-12345"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {secret}")

    client = TavilyClient(api_key=secret, transport=httpx.MockTransport(handler))
    with pytest.raises(WebSearchError) as exc_info:
        asyncio.run(client.search("test"))
    assert secret not in str(exc_info.value)


def test_web_search_requires_approval_and_records_trace_span():
    async def scenario():
        no_approval_tools = WebSearchTools(client=AsyncMock(), approvals=None)
        with pytest.raises(ToolError):
            await no_approval_tools.search_web("最新ニュース")

        sink = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(sink))

        client = AsyncMock()
        client.search.return_value = {
            "provider": "tavily",
            "fetched_at": "2026-11-21T09:00:00+00:00",
            "count": 1,
            "results": [{"title": "Example", "url": "https://example.com", "snippet": "info", "score": 0.9}],
        }
        manager = ApprovalManager("sess-web")
        tools = WebSearchTools(
            client=client,
            approvals=manager,
            max_searches_per_session=1,
            tracer_provider=provider,
        )

        task = asyncio.create_task(tools.search_web("最新ニュース", max_results=3))
        await asyncio.sleep(0)
        proposal = manager.snapshot()["proposal"]
        assert proposal is not None
        assert proposal["tool"] == "search_web"
        assert proposal["arguments"] == {"query": "最新ニュース", "max_results": 3}
        assert not client.search.called

        manager.decide("sess-web", proposal["execution_id"], True)
        res = await task
        assert res["count"] == 1
        client.search.assert_awaited_once_with("最新ニュース", max_results=3)

        with pytest.raises(ToolError):
            await tools.search_web("2回目の検索")

        spans = sink.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "web_search.tavily"
        assert spans[0].attributes["web_search.provider"] == "tavily"
        assert spans[0].attributes["web_search.result_count"] == 1
        assert list(spans[0].attributes["web_search.urls"]) == ["https://example.com"]
        provider.shutdown()

    asyncio.run(scenario())


def test_web_search_denied_never_calls_client():
    async def scenario():
        client = AsyncMock()
        manager = ApprovalManager("sess-deny")
        tools = WebSearchTools(client=client, approvals=manager)
        task = asyncio.create_task(tools.search_web("天気"))
        await asyncio.sleep(0)
        proposal = manager.snapshot()["proposal"]
        manager.decide("sess-deny", proposal["execution_id"], False)
        with pytest.raises(ToolError):
            await task
        assert not client.search.called

    asyncio.run(scenario())
