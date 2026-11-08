from __future__ import annotations

import argparse
import json

from .demo_data import create_demo_db


def main() -> None:
    p = argparse.ArgumentParser(prog="bi-analyst")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-demo", help="create data/demo.db")
    ask = sub.add_parser("ask", help="ask a business question")
    ask.add_argument("question")
    args = p.parse_args()

    if args.cmd == "init-demo":
        print("created", create_demo_db())
        return

    from .runner import BIAnalyst

    r = BIAnalyst().ask(args.question)
    print(f"status:   {r['status']}  (attempts: {r['attempts']})")
    print(f"plan:\n{r['plan']}\n")
    print(f"sql:\n{r['sql']}\n")
    if r["error"]:
        print("error:", r["error"])
    print(" | ".join(r["columns"]))
    for row in r["rows"][:20]:
        print(" | ".join(str(v) for v in row))
    for w in r["warnings"]:
        print("warning:", w)
    print(f"\ntrace: traces/{r['trace_id']}.jsonl")


if __name__ == "__main__":
    main()
