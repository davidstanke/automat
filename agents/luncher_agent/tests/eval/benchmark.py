"""Token and latency benchmark for the synthesizer.

`agents-cli eval` grades response quality but reports no token counts or wall
clock, and `agent_turn_count` is not a usable proxy. This drives the synthesizer
in isolation -- no orchestrator, no sub-agent hops -- so the
numbers reflect the synthesizer alone.

Repeats matter: the value of building the surface deterministically shows up as a
*failure rate* in the tail, not as a better average. Defaults to 5 runs.

    cd agents/luncher_agent
    PYTHONPATH=. uv run python tests/eval/benchmark.py [runs]
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai.types import Content, Part  # noqa: E402

from app.agent import synthesizer_agent  # noqa: E402

CONTEXT = (
    "Strategic priorities: the OmniChef smart-kitchen launch is the Q4 priority; "
    "VisionSphere beta follows in Q1.\n"
    "Team availability: Tue 12 Aug 12:00-13:00 (8 of 8 free), Wed 13 Aug 12:30-13:30 "
    "(7 of 8), Thu 14 Aug 12:00-13:00 (6 of 8).\n"
    "Team: Liam, Diego, Dan, Maya, Aaliyah, Naomi, Jordan, Kai."
)


async def _one_run() -> dict:
    runner = InMemoryRunner(agent=synthesizer_agent, app_name="benchmark")
    session = await runner.session_service.create_session(
        app_name="benchmark", user_id="bench"
    )

    started = time.time()
    text, usage = "", []
    async for event in runner.run_async(
        user_id="bench",
        session_id=session.id,
        new_message=Content(role="user", parts=[Part(text=CONTEXT)]),
    ):
        if event.usage_metadata:
            usage.append(event.usage_metadata)
        if event.content and event.content.parts:
            text += "".join(p.text for p in event.content.parts if p.text)

    result = {
        "seconds": time.time() - started,
        "prompt_tokens": sum(u.prompt_token_count or 0 for u in usage),
        "output_tokens": sum(u.candidates_token_count or 0 for u in usage),
        "valid": False,
        "problem": None,
    }

    if not text.strip():
        result["problem"] = "no output text emitted"
        return result

    required_snippets = ["#", "Strategic Rationale", "Included Team Members", "Proposed Time Slots"]
    missing = [s for s in required_snippets if s.casefold() not in text.casefold()]
    if missing:
        result["problem"] = f"missing required sections: {missing}"
        return result

    result["valid"] = True
    return result


async def main(runs: int) -> None:
    results = []
    for index in range(1, runs + 1):
        outcome = await _one_run()
        results.append(outcome)
        flag = "ok" if outcome["valid"] else f"FAIL ({outcome['problem']})"
        print(
            f"  run {index}/{runs}: {outcome['seconds']:5.1f}s "
            f"prompt={outcome['prompt_tokens']:,} out={outcome['output_tokens']:,}  {flag}"
        )

    valid = sum(r["valid"] for r in results)
    print(
        f"\n  valid           {valid}/{runs}  ({100 * valid / runs:.0f}%)\n"
        f"  median latency  {statistics.median(r['seconds'] for r in results):.1f}s\n"
        f"  median prompt   {statistics.median(r['prompt_tokens'] for r in results):,.0f} tokens\n"
        f"  median output   {statistics.median(r['output_tokens'] for r in results):,.0f} tokens"
    )
    for failure in (r for r in results if not r["valid"]):
        print(f"  failure: {failure['problem']}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5))
