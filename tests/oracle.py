import re

from bi_analyst.llm import record_usage


class OracleLLM:
    """Pretends to be a perfect model: returns each question's gold SQL (found via the QUESTION
    line in the prompt). `override[id]` is a list of replies consumed one per call, to simulate
    wrong answers or a bad first attempt that the self-correction loop must repair."""

    def __init__(self, questions, override=None):
        self.by_question = {q["question"]: q for q in questions}
        self.override = {k: list(v) for k, v in (override or {}).items()}

    def complete(self, system, user, *, agent):
        record_usage(agent, 10, 5, 0.01)
        if agent == "planner":
            return "plan"
        q = self.by_question[re.search(r"QUESTION: (.*)", user).group(1)]
        queue = self.override.get(q["id"])
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        if q["kind"] == "unanswerable":
            return "CANNOT_ANSWER: the schema has no such data"
        if q["kind"] == "unsafe":
            return "DELETE FROM orders"
        return f"```sql\n{q['gold_sql']}\n```"


def check_question_set(questions, db, min_total, min_tricks):
    """Structural checks shared by every question suite."""
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)) and len(questions) >= min_total
    assert sum(1 for q in questions if "trick" in q["tags"]) >= min_tricks
    for q in questions:
        assert q["difficulty"] in {"easy", "medium", "hard"}
        assert q["kind"] in {"answerable", "unanswerable", "unsafe"}
        if q["kind"] != "answerable":
            assert not q.get("gold_sql")
            continue
        for sql in [q["gold_sql"], *q.get("alt_gold_sql", [])]:
            rows = db.run(sql).rows                      # raises if the reference SQL is broken
            assert len(rows) <= 500, f"{q['id']} returns too many rows"
            assert bool(rows) != q["expect_empty"], f"{q['id']}: empty/non-empty does not match expect_empty"
