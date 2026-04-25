"""Standalone evaluation harness for the multi-agent pipeline.

Runs 20 labeled test utterances through `process_voice_input()` with
real LLM calls and computes accuracy metrics:

    Intent Classification Accuracy     (%)
    Task Count Accuracy                (% with exact correct count)
    Category Accuracy                  (% top task matches expected)
    Priority Accuracy                  (% top task matches expected)
    Deadline Accuracy                  (% deadline present/absent matches)
    Dedup Precision                    (% duplicate cases correctly skipped)

Results are printed as a formatted table and saved to
`tests/eval_results.json`.

Usage:
    python -m tests.evaluation            # run all 20 cases
    python -m tests.evaluation --verbose  # per-utterance detail

Deviations from PLAN.md noted:
- Summary agent runs as final node; result dict now includes `summary`
  and `suggestions` — these are noted per utterance in verbose mode.
- `process_voice_input` is async; run via `asyncio.run()`.
- Evaluation uses a dedicated MongoDB database (`thought2do_eval`) so
  created tasks don't pollute the production database.  The database is
  dropped before and after the run.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

# Resolve project root so this script can be run from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

from app.agents.graph import process_voice_input  # noqa: E402
from app.config import get_settings  # noqa: E402

_EVAL_MONGO_URI = get_settings().MONGODB_URI
_EVAL_DB_NAME = "thought2do_eval"
_RESULTS_PATH = Path(__file__).parent / "eval_results.json"

# ---------------------------------------------------------------------------
# Labeled test set — 20 utterances
# Each entry:
#   transcript         — the raw input string
#   expected_intent    — CREATE / UPDATE / DELETE / QUERY / MIXED
#   expected_count     — exact expected number of tasks in the response
#   expected_category  — category of the primary (first) task, or None to skip
#   expected_priority  — priority of the primary (first) task, or None to skip
#   expected_deadline  — True if a deadline should be present, False if not, None to skip
#   is_duplicate       — True if this is one of the 5 dedup probe cases
# ---------------------------------------------------------------------------

TEST_CASES: List[Dict[str, Any]] = [
    # ── CREATE (simple) ────────────────────────────────────────────────────
    {
        "id": 1,
        "transcript": "remind me to buy milk",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": False,
    },
    {
        "id": 2,
        "transcript": "I need to submit my project report by Friday, it's urgent",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Work",
        "expected_priority": "Critical",
        "expected_deadline": True,
        "is_duplicate": False,
    },
    {
        "id": 3,
        "transcript": "schedule a dentist appointment for next week",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Health",
        "expected_priority": "Medium",
        "expected_deadline": True,
        "is_duplicate": False,
    },
    {
        "id": 4,
        "transcript": "I need to study for my algorithms exam",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Education",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": False,
    },
    {
        "id": 5,
        "transcript": "pay my credit card bill by end of the month",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Finance",
        "expected_priority": "Medium",
        "expected_deadline": True,
        "is_duplicate": False,
    },
    # ── CREATE (compound) ──────────────────────────────────────────────────
    {
        "id": 6,
        "transcript": "I need to buy groceries and also call the dentist",
        "expected_intent": "CREATE",
        "expected_count": 2,
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": False,
    },
    {
        "id": 7,
        "transcript": "I need to study for my exam and buy groceries and call mom",
        "expected_intent": "CREATE",
        "expected_count": 3,
        "expected_category": "Education",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": False,
    },
    # ── UPDATE ─────────────────────────────────────────────────────────────
    {
        "id": 8,
        "transcript": "I already finished the presentation",
        "expected_intent": "UPDATE",
        "expected_count": 1,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    {
        "id": 9,
        "transcript": "push my team meeting to next Monday",
        "expected_intent": "UPDATE",
        "expected_count": 1,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": True,
        "is_duplicate": False,
    },
    {
        "id": 10,
        "transcript": "change the gym task to high priority",
        "expected_intent": "UPDATE",
        "expected_count": 1,
        "expected_category": None,
        "expected_priority": "High",
        "expected_deadline": None,
        "is_duplicate": False,
    },
    # ── DELETE ─────────────────────────────────────────────────────────────
    {
        "id": 11,
        "transcript": "forget about the grocery task",
        "expected_intent": "DELETE",
        "expected_count": 1,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    {
        "id": 12,
        "transcript": "actually never mind about the dentist appointment",
        "expected_intent": "DELETE",
        "expected_count": 1,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    # ── QUERY ──────────────────────────────────────────────────────────────
    {
        "id": 13,
        "transcript": "what's due tomorrow",
        "expected_intent": "QUERY",
        "expected_count": None,  # query returns variable results
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    {
        "id": 14,
        "transcript": "what do I have on my plate this week",
        "expected_intent": "QUERY",
        "expected_count": None,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    {
        "id": 15,
        "transcript": "show me all my work tasks",
        "expected_intent": "QUERY",
        "expected_count": None,
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": None,
        "is_duplicate": False,
    },
    # ── MIXED ──────────────────────────────────────────────────────────────
    {
        "id": 16,
        "transcript": "add laundry and also mark my report as done",
        "expected_intent": "MIXED",
        "expected_count": 2,
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": False,
    },
    # ── Ambiguous / edge cases ─────────────────────────────────────────────
    {
        "id": 17,
        "transcript": "hmm let me think",
        "expected_intent": "CREATE",
        "expected_count": 0,  # empty or minimal output expected
        "expected_category": None,
        "expected_priority": None,
        "expected_deadline": False,
        "is_duplicate": False,
    },
    # ── Dedup probes (5 deliberate near-duplicates) ────────────────────────
    {
        "id": 18,
        "transcript": "buy milk",
        "expected_intent": "CREATE",
        "expected_count": 1,
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": True,
    },
    {
        "id": 19,
        "transcript": "remind me to pick up milk from the store",
        "expected_intent": "CREATE",
        "expected_count": 1,  # should detect dup of case 18 and skip/merge
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": True,
    },
    {
        "id": 20,
        "transcript": "I need to get some milk",
        "expected_intent": "CREATE",
        "expected_count": 1,  # another dup; dedup should skip
        "expected_category": "Personal",
        "expected_priority": "Medium",
        "expected_deadline": False,
        "is_duplicate": True,
    },
]


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _primary_task(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the first task from the most prominent bucket."""
    for bucket in ("tasks_created", "tasks_updated", "tasks_queried"):
        tasks = result.get(bucket) or []
        if tasks:
            return tasks[0]
    return None


def _intent_from_result(result: Dict[str, Any]) -> str:
    """Infer actual intent from which buckets are populated."""
    reasoning = result.get("agent_reasoning", "")
    for line in reasoning.splitlines():
        if line.startswith("[intent]"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] in {"CREATE", "UPDATE", "DELETE", "QUERY", "MIXED"}:
                return parts[1]
    # Fallback: infer from populated buckets
    if result.get("tasks_created"):
        return "CREATE"
    if result.get("tasks_updated"):
        return "UPDATE"
    if result.get("tasks_deleted"):
        return "DELETE"
    if result.get("tasks_queried"):
        return "QUERY"
    return "UNKNOWN"


def _total_task_count(result: Dict[str, Any]) -> int:
    return (
        len(result.get("tasks_created") or [])
        + len(result.get("tasks_updated") or [])
        + len(result.get("tasks_deleted") or [])
    )


# ---------------------------------------------------------------------------
# Async evaluation runner
# ---------------------------------------------------------------------------

async def _run_evaluation(verbose: bool) -> Dict[str, Any]:
    # Set up eval database
    sync_client = MongoClient(_EVAL_MONGO_URI)
    sync_client.drop_database(_EVAL_DB_NAME)
    motor_client = AsyncIOMotorClient(_EVAL_MONGO_URI)
    db = motor_client[_EVAL_DB_NAME]

    eval_user_id = str(ObjectId())

    intent_correct = 0
    count_correct = 0
    category_correct = 0
    category_total = 0
    priority_correct = 0
    priority_total = 0
    deadline_correct = 0
    deadline_total = 0
    dedup_skipped = 0
    dedup_total = 0

    per_case_results = []
    total = len(TEST_CASES)

    print(f"\nRunning {total} evaluation cases against real LLM …\n")

    for case in TEST_CASES:
        cid = case["id"]
        transcript = case["transcript"]
        print(f"  [{cid:02d}/{total}] {transcript[:70]}", end=" … ", flush=True)

        try:
            result = await process_voice_input(transcript, eval_user_id, db)
        except Exception as exc:
            print(f"ERROR: {exc}")
            per_case_results.append({**case, "error": str(exc)})
            continue

        actual_intent = _intent_from_result(result)
        actual_count = _total_task_count(result)
        primary = _primary_task(result)

        # Intent accuracy
        intent_ok = actual_intent == case["expected_intent"]
        if intent_ok:
            intent_correct += 1

        # Task count accuracy
        count_ok: Optional[bool] = None
        if case["expected_count"] is not None:
            count_ok = actual_count == case["expected_count"]
            if count_ok:
                count_correct += 1

        # Category accuracy (only when expected is set and a primary task exists)
        category_ok: Optional[bool] = None
        if case["expected_category"] is not None and primary:
            category_total += 1
            category_ok = primary.get("category") == case["expected_category"]
            if category_ok:
                category_correct += 1

        # Priority accuracy
        priority_ok: Optional[bool] = None
        if case["expected_priority"] is not None and primary:
            priority_total += 1
            priority_ok = primary.get("priority") == case["expected_priority"]
            if priority_ok:
                priority_correct += 1

        # Deadline accuracy
        deadline_ok: Optional[bool] = None
        if case["expected_deadline"] is not None and primary:
            deadline_total += 1
            has_deadline = primary.get("deadline") is not None
            deadline_ok = has_deadline == case["expected_deadline"]
            if deadline_ok:
                deadline_correct += 1

        # Dedup precision: duplicate cases should produce 0 created tasks
        # after the first occurrence has been stored.
        if case["is_duplicate"]:
            dedup_total += 1
            # Case 18 is the first occurrence — not a dup yet.
            if cid != 18:
                if len(result.get("tasks_created") or []) == 0:
                    dedup_skipped += 1

        status_str = "✓" if intent_ok else "✗"
        print(status_str)

        per_case_results.append({
            "id": cid,
            "transcript": transcript,
            "expected_intent": case["expected_intent"],
            "actual_intent": actual_intent,
            "intent_ok": intent_ok,
            "expected_count": case["expected_count"],
            "actual_count": actual_count,
            "count_ok": count_ok,
            "expected_category": case["expected_category"],
            "actual_category": primary.get("category") if primary else None,
            "category_ok": category_ok,
            "expected_priority": case["expected_priority"],
            "actual_priority": primary.get("priority") if primary else None,
            "priority_ok": priority_ok,
            "expected_deadline": case["expected_deadline"],
            "actual_deadline": primary.get("deadline") if primary else None,
            "deadline_ok": deadline_ok,
            "is_duplicate": case["is_duplicate"],
            "summary": result.get("summary", ""),
            "suggestions": result.get("suggestions", []),
        })

        if verbose:
            _print_case_detail(per_case_results[-1], result)

    # Metrics
    count_evaluated = sum(1 for c in TEST_CASES if c["expected_count"] is not None)
    dedup_precision = (dedup_skipped / max(dedup_total - 1, 1)) * 100

    metrics = {
        "intent_accuracy_pct":   round(intent_correct   / total * 100, 1),
        "count_accuracy_pct":    round(count_correct     / max(count_evaluated, 1) * 100, 1),
        "category_accuracy_pct": round(category_correct  / max(category_total, 1) * 100, 1),
        "priority_accuracy_pct": round(priority_correct  / max(priority_total, 1) * 100, 1),
        "deadline_accuracy_pct": round(deadline_correct  / max(deadline_total, 1) * 100, 1),
        "dedup_precision_pct":   round(dedup_precision, 1),
        "totals": {
            "intent":   f"{intent_correct}/{total}",
            "count":    f"{count_correct}/{count_evaluated}",
            "category": f"{category_correct}/{category_total}",
            "priority": f"{priority_correct}/{priority_total}",
            "deadline": f"{deadline_correct}/{deadline_total}",
            "dedup":    f"{dedup_skipped}/{max(dedup_total - 1, 1)}",
        },
    }

    # Teardown eval DB
    sync_client.drop_database(_EVAL_DB_NAME)
    sync_client.close()
    motor_client.close()

    return {"metrics": metrics, "cases": per_case_results}


def _print_case_detail(case_result: dict, pipeline_result: dict) -> None:
    print(f"\n    Intent  : {case_result['actual_intent']} (expected {case_result['expected_intent']}) {'✓' if case_result['intent_ok'] else '✗'}")
    print(f"    Count   : {case_result['actual_count']} (expected {case_result['expected_count']}) {'' if case_result['count_ok'] is None else ('✓' if case_result['count_ok'] else '✗')}")
    if case_result["category_ok"] is not None:
        print(f"    Category: {case_result['actual_category']} (expected {case_result['expected_category']}) {'✓' if case_result['category_ok'] else '✗'}")
    if case_result["priority_ok"] is not None:
        print(f"    Priority: {case_result['actual_priority']} (expected {case_result['expected_priority']}) {'✓' if case_result['priority_ok'] else '✗'}")
    if case_result["deadline_ok"] is not None:
        has_dl = case_result["actual_deadline"] is not None
        print(f"    Deadline: {'present' if has_dl else 'absent'} (expected {'present' if case_result['expected_deadline'] else 'absent'}) {'✓' if case_result['deadline_ok'] else '✗'}")
    if case_result["summary"]:
        print(f"    Summary : {case_result['summary'][:80]}")
    print()


def _print_report(metrics: dict) -> None:
    t = metrics["totals"]
    print("\n" + "=" * 52)
    print("  EVALUATION REPORT")
    print("=" * 52)
    print(f"  Intent Classification Accuracy : {metrics['intent_accuracy_pct']:5.1f}%  ({t['intent']})")
    print(f"  Task Count Accuracy            : {metrics['count_accuracy_pct']:5.1f}%  ({t['count']})")
    print(f"  Category Accuracy              : {metrics['category_accuracy_pct']:5.1f}%  ({t['category']})")
    print(f"  Priority Accuracy              : {metrics['priority_accuracy_pct']:5.1f}%  ({t['priority']})")
    print(f"  Deadline Accuracy              : {metrics['deadline_accuracy_pct']:5.1f}%  ({t['deadline']})")
    print(f"  Dedup Precision                : {metrics['dedup_precision_pct']:5.1f}%  ({t['dedup']})")
    print("=" * 52 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Thought2Do pipeline evaluation harness")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-utterance detail")
    args = parser.parse_args()

    output = asyncio.run(_run_evaluation(verbose=args.verbose))

    _print_report(output["metrics"])

    output["generated_at"] = datetime.now(timezone.utc).isoformat()
    _RESULTS_PATH.write_text(json.dumps(output, indent=2, default=str))
    print(f"Results saved to {_RESULTS_PATH}\n")


if __name__ == "__main__":
    main()
