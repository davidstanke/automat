"""Drives a real multi-turn conversation against the locally running agent.

`agents-cli eval generate` narrates a case's earlier turns rather than running
them, so an agent reads that it booked something no booking exists for. Anything
stateful -- cancelling what a previous turn created -- cannot be tested that way.
Sharing one session id across sends makes each turn real.

    uv run python tests/eval/multi_turn_check.py

Clearing the calendar takes three turns, not two: the agent states the count
before accepting a confirmation, so confirming a number it has not shown you yet
does not satisfy it.
"""
import json, sys, urllib.request

BASE, APP, USER = "http://localhost:8082", "sched_agent", "eval"

def post(path, body=None):
    req = urllib.request.Request(f"{BASE}{path}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read().decode()

session = json.loads(post(f"/apps/{APP}/users/{USER}/sessions"))["id"]
print("session:", session)

for turn, text in enumerate([
    "Book Friday 12:00-13:00 with the Fiesta Taco Bar.",
    "Now cancel every lunch on the team calendar.",
    "Yes, confirmed - cancel all of them.",
]):
    raw = post("/run_sse", {"appName": APP, "userId": USER, "sessionId": session,
        "newMessage": {"role": "user", "parts": [{"text": text}]}, "streaming": False})
    calls, reply = [], ""
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:])
        for p in (ev.get("content") or {}).get("parts") or []:
            fc = p.get("functionCall") or p.get("function_call")
            if fc: calls.append(fc.get("name"))
            if p.get("text"): reply = p["text"]
    print(f"\nTURN {turn}: {text[:50]}")
    print("  calls:", calls)
    print("  reply:", reply[:600].replace("\n", " "))
