"""Demo client: ask a question and print the SSE event stream as it arrives."""

import json
import sys

import httpx

API = "http://127.0.0.1:8000/v1/chat"


def main() -> None:
    question = sys.argv[1]
    as_of = sys.argv[2] if len(sys.argv) > 2 else None

    payload = {"question": question}
    if as_of:
        payload["as_of"] = as_of

    sources = []
    answer_parts: list[str] = []
    finish = "?"
    used: list[int] = []

    with httpx.stream("POST", API, json=payload, timeout=300) as resp:
        print(f"[{resp.status_code} {resp.headers.get('content-type')}]\n")
        event = ""
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: ") and event:
                data = json.loads(line[6:])
                if event == "meta":
                    sources = data["sources"]
                elif event == "token":
                    answer_parts.append(data["text"])
                    print(data["text"], end="", flush=True)
                elif event == "notice":
                    print(f"\n[NOTICE] {data['text']}")
                elif event == "citations":
                    used = data["used"]
                elif event == "done":
                    finish = data["finish"]
                    print(f"\n\n--- finish={finish} latency={data['latency_ms']}ms")
            elif line == "":
                event = ""

    print("\n=== cited sources ===")
    for s in sources:
        marker = "*" if s["n"] in used or not used else " "
        origin = f" ({s['origin']})" if s["origin"] != "seed" else ""
        print(f" {marker}[{s['n']}] {s['instrument']['title']} s.{s['article']['number']}"
              f" - {s['article']['heading'][:50]}{origin}")


if __name__ == "__main__":
    main()
