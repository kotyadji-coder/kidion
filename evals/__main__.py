"""
CLI entry point for eval system.

Usage:
    python -m evals run              — full eval run
    python -m evals run --quick      — only 3 lesson + 3 chat cases
    python -m evals compare          — compare last two runs
    python -m evals list             — list all runs
"""

import argparse
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.runner import run_eval, run_real_data_eval, compare_runs, get_all_runs
from evals.dataset import LESSON_TEST_CASES, CHAT_TEST_CASES


def cmd_run(args):
    if args.quick:
        lessons = LESSON_TEST_CASES[:3]
        chats = CHAT_TEST_CASES[:3]
    else:
        lessons = LESSON_TEST_CASES
        chats = CHAT_TEST_CASES

    run_id = run_eval(
        lesson_cases=lessons,
        chat_cases=chats,
        version=args.version or "",
    )
    print(f"Run #{run_id} saved. View at /evals/dashboard")


def cmd_check(args):
    run_id = run_real_data_eval()
    if run_id > 0:
        print(f"Run #{run_id} saved. View at /evals/dashboard")


def cmd_compare(args):
    result = compare_runs()
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\nBaseline: Run #{result['baseline']['run_id']} ({result['baseline']['git_hash']})")
    print(f"Current:  Run #{result['current']['run_id']} ({result['current']['git_hash']})")

    if result["det_delta"] is not None:
        sign = "+" if result["det_delta"] >= 0 else ""
        print(f"\nDeterministic: {sign}{result['det_delta']:.1%}")

    print("\n--- Lessons ---")
    for key, info in result["deltas"]["lessons"].items():
        sign = "+" if info["delta"] >= 0 else ""
        flag = " !! REGRESSION" if info["regression"] else ""
        print(f"  {key:25s}: {info['baseline']:.1f} -> {info['current']:.1f} ({sign}{info['delta']:.1f}){flag}")

    print("\n--- Chats ---")
    for key, info in result["deltas"]["chats"].items():
        sign = "+" if info["delta"] >= 0 else ""
        flag = " !! REGRESSION" if info["regression"] else ""
        print(f"  {key:25s}: {info['baseline']:.1f} -> {info['current']:.1f} ({sign}{info['delta']:.1f}){flag}")

    if result["regressions"]:
        print(f"\n!! {len(result['regressions'])} REGRESSION(S) DETECTED:")
        for r in result["regressions"]:
            print(f"   - {r}")
    else:
        print("\nNo regressions detected.")


def cmd_list(args):
    runs = get_all_runs()
    if not runs:
        print("No eval runs found.")
        return

    print(f"\n{'ID':>4} | {'Status':>10} | {'Git':>8} | {'Det':>6} | {'LLM':>6} | {'Lessons':>7} | {'Chats':>5} | Started")
    print("-" * 80)
    for r in runs:
        det = f"{r['avg_deterministic']:.0%}" if r['avg_deterministic'] else "—"
        llm = f"{r['avg_llm_score']:.1f}" if r['avg_llm_score'] else "—"
        started = r['started_at'][:16] if r['started_at'] else "—"
        print(f"{r['id']:>4} | {r['status']:>10} | {r['git_hash'] or '—':>8} | {det:>6} | {llm:>6} | {r['lesson_count']:>7} | {r['chat_count']:>5} | {started}")


def main():
    parser = argparse.ArgumentParser(description="Kidion Eval System")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Synthetic eval (generate new lessons)")
    run_parser.add_argument("--quick", action="store_true", help="Quick mode (3 cases)")
    run_parser.add_argument("--version", default="", help="Version label")

    sub.add_parser("check", help="Check existing lessons (real data, cheap)")
    sub.add_parser("compare", help="Compare last two runs")
    sub.add_parser("list", help="List all runs")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
