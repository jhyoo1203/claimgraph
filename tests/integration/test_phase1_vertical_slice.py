from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "eval"))

from phase1_evaluator import evaluate_phase1  # noqa: E402


def test_phase1_evaluator_covers_all_five_questions_and_traceability() -> None:
    summary = evaluate_phase1()

    assert summary["status"] == "pass"
    assert summary["question_count"] == 5
    assert summary["passed"] == 5
    assert summary["failed"] == 0
    for result in summary["results"]:
        assert result["pass"] is True
        assert result["report_citation_paths"]
        assert result["unsupported_claim_ids"]
        assert result["checks"]["single_search"] is True
        assert result["checks"]["citation_paths_in_markdown"] is True
        assert result["checks"]["unsupported_preserved"] is True
