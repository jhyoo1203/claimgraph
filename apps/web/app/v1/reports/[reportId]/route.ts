import { NextRequest } from "next/server";

import {
  reportFixture,
  unsupportedReportFixture,
} from "@/app/lib/report-fixture";

type ReportRouteContext = {
  params: Promise<{ reportId: string }>;
};

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

export async function GET(
  request: NextRequest,
  context: ReportRouteContext,
): Promise<Response> {
  const { reportId } = await context.params;
  if (reportId !== "demo") {
    return Response.json(
      {
        error_code: "REPORT_NOT_FOUND",
        message: "요청한 보고서를 찾을 수 없습니다.",
      },
      { status: 404 },
    );
  }

  const mode = request.nextUrl.searchParams.get("mode");
  if (mode === "error") {
    return Response.json(
      {
        error_code: "REPORT_UNAVAILABLE",
        message: "보고서를 잠시 불러오지 못했습니다.",
      },
      { status: 503 },
    );
  }

  if (mode === "empty") {
    return Response.json({ report: null });
  }

  if (mode === "loading") {
    await wait(700);
  }

  if (mode === "unsupported") {
    return Response.json(unsupportedReportFixture);
  }

  return Response.json(reportFixture);
}
