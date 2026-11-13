import dataclasses
from types import SimpleNamespace

from bi_analyst import BIAnalyst
from bi_analyst.config import Settings
from bi_analyst.llm import FakeLLM, OpenAICompatibleLLM, make_llm, usage_scope

GOOD = "```sql\nSELECT COUNT(*) FROM customers\n```"
BAD = "```sql\nSELECT nope FROM customers\n```"
SIMPLE = '{"route": "simple", "sub_questions": []}'


def test_usage_counts_calls_per_agent(settings):
    r = BIAnalyst(settings, llm=FakeLLM({"planner": ["p"], "sql_writer": [GOOD]})).ask("how many customers")
    u = r["usage"]
    assert u["total"]["calls"] == 2
    assert set(u["by_agent"]) == {"planner", "sql_writer"}


def test_usage_counts_correction_calls(settings):
    r = BIAnalyst(settings, llm=FakeLLM({"planner": ["p"], "sql_writer": [BAD, GOOD]})).ask("how many customers")
    assert r["usage"]["by_agent"]["sql_writer"]["calls"] == 2 and r["usage"]["total"]["calls"] == 3


def test_usage_includes_router_when_enabled(settings):
    cfg = dataclasses.replace(settings, enable_router=True)
    r = BIAnalyst(cfg, llm=FakeLLM({"router": [SIMPLE], "planner": ["p"], "sql_writer": [GOOD]})).ask("how many customers")
    assert r["usage"]["by_agent"]["router"]["calls"] == 1 and r["usage"]["total"]["calls"] == 3


def test_usage_scopes_do_not_leak():
    with usage_scope() as a:
        FakeLLM({"x": ["1"]}).complete("s", "u", agent="x")
    with usage_scope() as b:
        pass
    assert a.summary()["total"]["calls"] == 1 and b.summary()["total"]["calls"] == 0


def test_openai_compatible_records_tokens_and_passes_max_tokens():
    llm = OpenAICompatibleLLM("m", "http://localhost:1/v1", "k", max_tokens=1234)
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="<think>x</think>hi"))],
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7))

    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with usage_scope() as u:
        assert llm.complete("sys", "usr", agent="planner") == "hi"
    t = u.summary()["total"]
    assert (t["input_tokens"], t["output_tokens"], t["calls"]) == (11, 7, 1)
    assert seen["max_tokens"] == 1234


def test_make_llm_uses_configured_max_tokens():
    llm = make_llm(Settings(provider="groq", api_key="k", model="some-model", max_tokens=777))
    assert llm._max_tokens == 777


def test_cannot_answer_ends_early_without_guessing(settings):
    llm = FakeLLM({"planner": ["p"], "sql_writer": ["CANNOT_ANSWER: there is no age column"]})
    r = BIAnalyst(settings, llm=llm).ask("average customer age?")
    assert r["status"] == "unanswerable" and r["attempts"] == 1
    assert r["error"].startswith("CANNOT_ANSWER") and "no age column" in r["error"]
    assert r["rows"] == [] and r["history"] == []          # never validated or executed


def test_cannot_answer_inside_a_fence_still_counts(settings):
    llm = FakeLLM({"planner": ["p"], "sql_writer": ["```\nCANNOT_ANSWER: no such table\n```"]})
    assert BIAnalyst(settings, llm=llm).ask("q")["status"] == "unanswerable"


def test_unanswerable_sub_question_gives_partial(settings):
    import json
    cfg = dataclasses.replace(settings, enable_router=True)
    route = json.dumps({"route": "multi_step", "sub_questions": ["how many customers", "average customer age"]})
    llm = FakeLLM({"router": [route], "planner": ["p"], "sql_writer": [GOOD, "CANNOT_ANSWER: no age"]})
    r = BIAnalyst(cfg, llm=llm).ask("customers and age")
    assert [s["status"] for s in r["sub_results"]] == ["success", "unanswerable"] and r["status"] == "partial"
