# Evaluation report: v4-check2

## Configuration

- **date:** 2026-11-21T14:47:11
- **provider:** groq
- **model:** openai/gpt-oss-120b
- **router:** False
- **max_attempts:** 3
- **db_dialect:** sqlite
- **questions_file:** questions_v2.jsonl
- **n_questions:** 2
- **repeat:** 1

## Headline results

Runs: 1 (accuracy shown as mean; range given when runs differ)

| Metric | Value |
|---|---|
| Execution accuracy (answerable questions, n=2) | 100.0% |
| First-attempt accuracy | 100.0% |
| Self-correction lift | 0.0% |
| Refusal accuracy (unanswerable/unsafe, n=0) | n/a |
| Avg seconds per question | 3.53 |
| Avg LLM calls per question | 2 |
| Tokens in / out (run 1) | 3372 / 2728 |
| API/pipeline errors (run 1) | 0 |

## Accuracy by difficulty (run 1, answerable only)

| Difficulty | n | Accuracy |
|---|---|---|
| hard | 2 | 100.0% |

## Failure types (run 1)

No failures.

## Failed questions (run 1): 0

## Notes

- Review failures by hand: some may be a reasonable alternative reading, or an error in the reference SQL.
- Free-tier and different models are not comparable; always report which model produced these numbers.
