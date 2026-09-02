"""Runs a dataset over the agent's A2A endpoint and writes traces.

`agents-cli eval generate` drives the ADK REST path. Clients such as Gemini
Enterprise use A2A, where the executor withholds every author but the
synthesizer, so the two paths deliver different responses to the same prompt --
and only this one reflects what a user is shown.

    uv run python tests/eval/a2a_generate.py <dataset> <url> [app_name]

Writes artifacts/traces-a2a/traces_<stamp>.json and scores it with the metrics
named in eval_config_a2a.yaml. Scoring happens here rather than through
`eval grade` because an A2A artifact is not an ADK trace -- its parts are A2A
types, and the grader rejects the file rather than reading them.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path


def _token() -> str | None:
    """Identity token for a deployed agent; local serving needs none."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _send(
    rpc_url: str,
    text: str,
    message_id: str,
    token: str | None,
    context_id: str | None = None,
) -> tuple[list[dict], str | None]:
    """Sends one user message, returning its parts and the context to continue in."""
    message: dict = {
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
        "messageId": message_id,
        "kind": "message",
    }
    # Carrying the context forward is what makes an earlier turn real: the agent
    # resumes the same session, so a booking it made is still there to cancel.
    if context_id:
        message["contextId"] = context_id

    payload = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "message/send",
        "params": {"message": message},
    }
    request = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.load(response)

    result = body.get("result") or {}
    parts: list[dict] = []
    for artifact in result.get("artifacts") or []:
        parts.extend(artifact.get("parts") or [])
    return parts, result.get("contextId")


def _prompts_of(case: dict) -> list[str]:
    """Every user message of a case, oldest first.

    A case that lists more than one is run as a conversation, each turn executed
    for real. History written into ``agent_data`` instead is only narrated: the
    agent reads that it booked something without a booking existing, so anything
    stateful cannot be tested that way.
    """
    prompts = [
        part["text"]
        for part in (case.get("prompt") or {}).get("parts") or []
        if part.get("text")
    ]
    for turn in (case.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            if event.get("author") != "user":
                continue
            for part in (event.get("content") or {}).get("parts") or []:
                if part.get("text"):
                    prompts.append(part["text"])
    return prompts


def _score(cases: list[dict]) -> None:
    """Applies the metrics from eval_config_a2a.yaml and prints a summary."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import single_voice

    metrics = {"single_voice": single_voice}
    print("\n== scores ==")
    totals: dict[str, list[float]] = {name: [] for name in metrics}
    for case in cases:
        line = [f"{case['eval_case_id']:<28}"]
        for name, module in metrics.items():
            result = module.evaluate({"response": case["responses"]})
            totals[name].append(float(result["score"]))
            line.append(f"{name}={result['score']}")
        print("  " + "  ".join(line))
    print()
    for name, scores in totals.items():
        mean = sum(scores) / len(scores) if scores else 0.0
        print(f"  {name}: mean {mean:.4f} over {len(scores)} case(s)")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    dataset_path, base_url = sys.argv[1], sys.argv[2].rstrip("/")
    app_name = sys.argv[3] if len(sys.argv) > 3 else "luncher_agent"
    rpc_url = f"{base_url}/a2a/{app_name}"

    cases = json.loads(Path(dataset_path).read_text())["eval_cases"]
    token = _token()
    print(f"== A2A inference: {len(cases)} case(s) against {rpc_url} ==")

    generated = []
    for index, case in enumerate(cases):
        prompts = _prompts_of(case)
        if not prompts:
            print(f"[a2a] case[{index}] SKIPPED: no prompt text")
            continue

        # Only the last turn is graded; the earlier ones exist to create the
        # state it acts on.
        context_id: str | None = None
        parts: list[dict] = []
        failed = False
        for turn, prompt in enumerate(prompts):
            try:
                parts, context_id = _send(
                    rpc_url, prompt, f"eval-{index}-{turn}", token, context_id
                )
            except Exception as error:  # noqa: BLE001 - reported per case
                print(f"[a2a] case[{index}] turn[{turn}] FAILED: {error}")
                failed = True
                break
            if len(prompts) > 1:
                kinds = [part.get("kind") or "text" for part in parts]
                print(f"[a2a] case[{index}] turn[{turn}] done: parts={kinds}")
        if failed:
            continue

        generated.append({
            "eval_case_id": case.get("eval_case_id", str(index)),
            "prompt": case.get("prompt"),
            "reference": case.get("reference"),
            "responses": [{"response": {"role": "model", "parts": parts}}],
        })
        if len(prompts) == 1:
            kinds = [part.get("kind") or "text" for part in parts]
            print(f"[a2a] case[{index}] done: parts={kinds}")
        else:
            print(f"[a2a] case[{index}] done: {len(prompts)} turns")

    if not generated:
        print("No artifact written: every case failed.")
        return 1

    _score(generated)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path("artifacts/traces-a2a") / f"traces_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"eval_cases": generated}, indent=2) + "\n")
    print(f"\nTraces saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
