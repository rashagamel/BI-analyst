from __future__ import annotations

import argparse
import json

from .demo_data import create_demo_db, create_saas_db


def main() -> None:
    p = argparse.ArgumentParser(prog="bi-analyst")
    sub = p.add_subparsers(dest="cmd", required=True)
    demo = sub.add_parser("init-demo", help="create data/demo.db (or data/saas.db with --saas)")
    demo.add_argument("--saas", action="store_true", help="create the harder SaaS database used by Eval v2")
    ask = sub.add_parser("ask", help="ask a business question")
    ask.add_argument("question")
    args = p.parse_args()

    if args.cmd == "init-demo":
        print("created", create_saas_db() if args.saas else create_demo_db())
        return

    from .runner import BIAnalyst

    r = BIAnalyst().ask(args.question)
    print(f"status:   {r['status']}  (route: {r['route']}, attempts: {r['attempts']})")
    if r["route"] == "multi_step":
        for i, sub in enumerate(r["sub_results"], 1):
            print(f"\n--- sub-question {i}: {sub['question']}")
            print(f"status: {sub['status']}  (attempts: {sub['attempts']})")
            print(f"sql:\n{sub['sql']}\n")
            if sub["error"]:
                print("error:", sub["error"])
            print(" | ".join(sub["columns"]))
            for row in sub["rows"][:20]:
                print(" | ".join(str(v) for v in row))
        if r["primary_index"]:
            print(f"\nprimary result: sub-question {r['primary_index']} (last one that succeeded)")
        for w in r["warnings"]:
            print("warning:", w)
    else:
        print(f"plan:\n{r['plan']}\n")
        print(f"sql:\n{r['sql']}\n")
        if r["error"]:
            print("error:", r["error"])
        print(" | ".join(r["columns"]))
        for row in r["rows"][:20]:
            print(" | ".join(str(v) for v in row))
        for w in r["warnings"]:
            print("warning:", w)
    u = r["usage"]["total"]
    print(f"\nllm calls: {u['calls']}  tokens in/out: {u['input_tokens']}/{u['output_tokens']}  llm time: {u['seconds']}s")
    print(f"\ntrace: traces/{r['trace_id']}.jsonl")


if __name__ == "__main__":
    main()
