from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = ROOT / "apps" / "web" / "app" / "page.tsx"
FIXTURE_PATH = ROOT / "apps" / "web" / "app" / "lib" / "report-fixture.ts"
ROUTE_PATH = ROOT / "apps" / "web" / "app" / "v1" / "reports" / "[reportId]" / "route.ts"


def test_web_states_use_plain_korean_copy_and_actionable_ctas() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")

    for copy in (
        "보고서 불러오는 중",
        "아직 보고서가 없습니다.",
        "보고서를 불러오지 못했습니다.",
        "근거가 부족한 주장도 결과에 남겨 두었습니다.",
        "다시 불러오기",
    ):
        assert copy in page

    for deprecated in (
        "REPORT / LOADING",
        "REPORT / EMPTY",
        "REPORT / ERROR",
        "Report statement를 따라가며 Claim 상태와 Evidence 링크를 확인합니다.",
        "문장을 따라가며 주장(Claim)의 상태와 근거(Evidence)를 확인합니다.",
        "원문 (Source)",
        "주장 (Claim)",
        "개의 Claim은 Evidence가 없어",
        "현재 Report snapshot의 표시 결과입니다.",
        "REPORT BODY",
        "CLAIM TRACE",
        "<code>{status}</code>",
        "<code>{report.report_id}</code>",
    ):
        assert deprecated not in page

    assert "주장(Claim)" not in page
    assert "근거(Evidence)" not in page
    assert "원문 (Source)" not in page
    assert "기술 정보" in page

    route = ROUTE_PATH.read_text(encoding="utf-8")
    assert "요청한 보고서를 찾을 수 없습니다." in route
    assert "보고서를 잠시 불러오지 못했습니다." in route
    assert "요청한 Report를 찾을 수 없습니다." not in route
    assert "Report 저장소에 일시적으로 연결할 수 없습니다." not in route


def test_web_report_fixture_does_not_reintroduce_developer_facing_copy() -> None:
    fixture = FIXTURE_PATH.read_text(encoding="utf-8")

    for copy in (
        "근거를 확인하는 보고서",
        "주장, 근거, 원문으로 이어지는 확인 경로를 볼 수 있습니다.",
        "근거가 없는 주장도 결과에 남겨 둘 수 있을까요?",
    ):
        assert copy in fixture

    for deprecated in (
        "How should the MVP expose",
        "MVP Claim Visibility",
        "주장(Claim)",
        "근거(Evidence)",
        "원문(Source)",
        "ReportStatement",
        "ClaimEvidenceRelation",
        "This scenario keeps an unsupported Claim",
    ):
        assert deprecated not in fixture
