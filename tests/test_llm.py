"""LLM layer tests using fake provider clients (no network, no keys)."""
import asyncio
from types import SimpleNamespace as NS

from app import llm


def make(provider_client=None, provider="gemini"):
    it = llm.Interpreter.__new__(llm.Interpreter)
    it.provider, it.model, it.gemini, it.anthropic = "rules", None, None, None
    if provider_client is not None:
        it.provider, it.model, it.gemini = provider, "fake-model", provider_client
    return it


def fake_gemini(parts=None, raises=None):
    async def generate_content(**kw):
        if raises:
            raise raises
        return NS(candidates=[NS(content=NS(parts=parts))])
    return NS(aio=NS(models=NS(generate_content=generate_content)))


def run(coro):
    return asyncio.run(coro)


def test_rules_mode_extracts_url_and_page_count():
    out = run(make().interpret([{"role": "user", "content": "crawl https://example.com 5 pages"}]))
    assert out["action"] == "crawl" and out["url"] == "https://example.com" and out["max_pages"] == 5


def test_rules_mode_small_talk_is_reply():
    assert run(make().interpret([{"role": "user", "content": "hello"}]))["action"] == "reply"


def test_gemini_function_call_becomes_crawl_intent():
    call = NS(name="crawl_site", args={"url": "https://example.com", "depth": 1})
    it = make(fake_gemini([NS(function_call=call, text=None)]))
    out = run(it.interpret([{"role": "user", "content": "scan example.com"}]))
    assert out == {"action": "crawl", "url": "https://example.com", "max_pages": None,
                   "depth": 1, "source": "gemini"}


def test_gemini_text_only_is_reply():
    it = make(fake_gemini([NS(function_call=None, text="Please give me a URL.")]))
    out = run(it.interpret([{"role": "user", "content": "crawl something"}]))
    assert out["action"] == "reply" and "URL" in out["text"]


def test_gemini_error_falls_back_to_rules_with_note():
    it = make(fake_gemini(raises=RuntimeError("quota")))
    out = run(it.interpret([{"role": "user", "content": "crawl https://example.com"}]))
    assert out["action"] == "crawl" and out["source"] == "rules" and "unavailable" in out["note"]


def test_gemini_summary_and_template_fallback():
    result = {"target": "https://example.com", "stats": {"pages_crawled": 1}, "site": {}, "pages": []}
    ok = make(fake_gemini([NS(function_call=None, text="A tiny site.")]))
    assert run(ok.summarize(result, "x")) == ("A tiny site.", "gemini")
    bad = make(fake_gemini(raises=RuntimeError("boom")))
    text, src = run(bad.summarize(result, "x"))
    assert src == "template" and "Crawled 1 page" in text
