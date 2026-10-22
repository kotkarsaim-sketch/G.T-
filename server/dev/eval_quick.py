"""Quick smoke evaluation against the running API.

Asks a handful of questions covering answer, cross-instrument, and
out-of-corpus cases, and prints per-question outcomes. Not the full golden-set
harness (docs/evaluation.md) - just a fast sanity gate for local runs.
"""

import sys

import httpx

API = "http://127.0.0.1:8000/v1/chat"

CASES = [
    ("dogs", "How many dogs am I allowed to keep at home?", None, "answer"),
    ("noise-penalty", "What is the fixed penalty for construction noise outside permitted hours?", None, "answer"),
    ("bees", "Do I need permission to keep bees on agricultural land?", None, "answer"),
    ("parking", "Can I park my trailer on the street overnight?", None, "refuse-or-answer"),
    ("provincial", "What does provincial law require for pet sterilization?", None, "refuse"),
    ("history", "What was the maximum height for a front yard fence?", "2023-06-01", "answer"),
]


def ask(client: httpx.Client, question: str, as_of: str | None) -> dict:
    payload = {"question": question}
    if as_of:
        payload["as_of"] = as_of
    result = {"finish": "?", "used": [], "top": "-", "latency_ms": 0}
    event = ""
    with client.stream("POST", API, json=payload, timeout=300) as resp:
        if resp.status_code != 200:
            result["finish"] = f"http-{resp.status_code}"
            return result
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: ") and event:
                data = json.loads(line[6:])
                if event == "meta" and data["sources"]:
                    result["top"] = (
                        f"{data['sources'][0]['instrument']['number']}"
                        f" s.{data['sources'][0]['article']['number']}"
                    )
                elif event == "citations":
                    result["used"] = data["used"]
                elif event == "done":
                    result["finish"] = data["finish"]
                    result["latency_ms"] = data["latency_ms"]
            elif line == "":
                event = ""
    return result


import json  # noqa: E402


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"{'case':<15} {'expected':<16} {'finish':<10} {'cited':<6} {'top-source':<12} {'ms':>6}")
    print("-" * 75)
    with httpx.Client() as client:
        for name, question, as_of, expected in CASES:
            if only and only != name:
                continue
            r = ask(client, question, as_of)
            cited = len(r["used"])
            print(
                f"{name:<15} {expected:<16} {r['finish']:<10} {cited:<6} "
                f"{r['top']:<12} {r['latency_ms']:>6}"
            )


if __name__ == "__main__":
    main()
