"""Offline JSON evaluator. No provider, DB, credentials or LLM imports.

Input: {sessions: [ISO date,...], net_returns: {arm: {ISO date: r|null}},
        trial_sharpes: {horizon: [all unannualized trial SRs]}}.
Returns MUST be daily close interval returns already net of costs. Missing
sessions/quality failures must be null, not omitted from `sessions`. The script
refuses daily path inference if any arm is incomplete. No trade replay implied.
Output is stdout; caller may redirect to /tmp. With no input prints protocol.
"""
import argparse
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

from alpha_agent.research_eval.metrics import common_dates, excess_returns, matched_summary
from alpha_agent.research_eval.protocol import PROTOCOL
from alpha_agent.research_eval.statistics import deflated_sharpe, newey_west, non_overlapping


def evaluate(payload):
    sessions = [date.fromisoformat(day) for day in payload["sessions"]]
    series = {name: {date.fromisoformat(day): value for day, value in values.items()}
              for name, values in payload["net_returns"].items()}
    aligned = common_dates(series, sessions)
    output = {"protocol": PROTOCOL.to_dict(), "fingerprint": PROTOCOL.fingerprint,
              "status": "complete" if aligned.complete else "incomplete_path",
              "coverage": aligned.coverage, "comparisons": []}
    for arm in series:
        for benchmark in PROTOCOL.primary_comparators:
            if arm == benchmark or benchmark not in series:
                continue
            item = {"arm": arm, "benchmark": benchmark,
                    "summary": matched_summary(aligned, arm, benchmark), "horizons": {}}
            if aligned.complete:
                a, b = aligned.values[arm], aligned.values[benchmark]
                item["daily_hac"] = asdict(newey_west(excess_returns(a, b)))
                for h in PROTOCOL.horizons:
                    offsets = []
                    for offset in range(h):
                        aa = non_overlapping(series[arm], sessions, h, offset=offset)
                        bb = non_overlapping(series[benchmark], sessions, h, offset=offset)
                        excess = excess_returns(tuple(aa.values()), tuple(bb.values()))
                        result = {"offset": offset, "hac": asdict(newey_west(excess))}
                        registry = payload.get("trial_sharpes", {}).get(str(h))
                        result["dsr"] = (deflated_sharpe(excess, trial_sharpes=registry)
                                         if registry else {"probability": None, "reason": "full_trial_registry_required"})
                        offsets.append(result)
                    item["horizons"][str(h)] = offsets
            output["comparisons"].append(item)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    args = parser.parse_args()
    output = (evaluate(json.loads(args.input.read_text())) if args.input else
              {"protocol": PROTOCOL.to_dict(), "fingerprint": PROTOCOL.fingerprint})
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False,
                     default=lambda value: value.isoformat()))


if __name__ == "__main__":
    main()
