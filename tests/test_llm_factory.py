import pytest

from bi_analyst.config import Settings
from bi_analyst.llm import AnthropicLLM, OpenAICompatibleLLM, make_llm, strip_reasoning


def test_strip_reasoning():
    assert strip_reasoning("<think>hmm</think>```sql\nSELECT 1\n```") == "```sql\nSELECT 1\n```"


def test_free_provider_requires_model_name():
    with pytest.raises(ValueError, match="BI_MODEL"):
        make_llm(Settings(provider="groq", api_key="k", model="claude-sonnet-5-5"))


def test_free_provider_requires_key():
    with pytest.raises(ValueError, match="BI_API_KEY"):
        make_llm(Settings(provider="groq", api_key=None, model="llama-3.3-70b-versatile"))


def test_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        make_llm(Settings(provider="nope", api_key="k", model="m"))


def test_groq_preset_builds_client():
    llm = make_llm(Settings(provider="groq", api_key="k", model="llama-3.3-70b-versatile"))
    assert isinstance(llm, OpenAICompatibleLLM)
    assert "groq.com" in str(llm._client.base_url)


def test_ollama_needs_no_key():
    llm = make_llm(Settings(provider="ollama", api_key=None, model="llama3.1"))
    assert "11434" in str(llm._client.base_url)


def test_anthropic_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert isinstance(make_llm(Settings(provider="anthropic")), AnthropicLLM)
