"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";

import {
  parseReportResponse,
  type Claim,
  type ClaimEvidenceRelation,
  type Evidence,
  type Report,
  type ReportStatement,
  type Source,
} from "./lib/report";

type FixtureMode = "default" | "loading" | "empty" | "error" | "unsupported";

type ReportState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: Report };

type EvidenceTrail = {
  evidence: Evidence;
  relation: ClaimEvidenceRelation;
  source: Source;
};

type MarkdownBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "unordered-list"; items: string[] }
  | { kind: "ordered-list"; items: string[] }
  | { kind: "blockquote"; text: string }
  | { kind: "code"; text: string };

const CLAIM_STATUS_META: Record<
  Claim["status"],
  { icon: string; label: string; description: string }
> = {
  supported: {
    icon: "↗",
    label: "근거 있음",
    description: "연결된 근거가 이 주장을 뒷받침합니다.",
  },
  unsupported: {
    icon: "∅",
    label: "근거 부족",
    description: "현재 연결된 근거가 없습니다.",
  },
  refuted: {
    icon: "×",
    label: "반박됨",
    description: "연결된 근거가 이 주장을 반박합니다.",
  },
  mixed: {
    icon: "±",
    label: "서로 다른 근거",
    description: "서로 다른 근거가 함께 있어 판단이 필요합니다.",
  },
  needs_review: {
    icon: "?",
    label: "검토 필요",
    description: "추가 검토가 필요한 상태입니다.",
  },
};

const RELATION_LABEL: Record<
  ClaimEvidenceRelation["relation_type"],
  string
> = {
  supports: "지지",
  refutes: "반박",
  qualifies: "조건부",
  mentions: "언급",
};

const REPORT_STATUS_LABEL: Record<Report["status"], string> = {
  draft: "초안",
  ready: "읽을 수 있음",
  published: "발행됨",
  failed: "실패함",
};

const INLINE_MARKDOWN_PATTERN =
  /(\[[^\]]+\]\((?:https?:\/\/|\/)[^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;

function isFixtureMode(value: string | null): value is FixtureMode {
  return (
    value === "default" ||
    value === "loading" ||
    value === "empty" ||
    value === "error" ||
    value === "unsupported"
  );
}

function readFixtureMode(): FixtureMode {
  if (typeof window === "undefined") {
    return "default";
  }

  const value = new URLSearchParams(window.location.search).get("mode");
  return isFixtureMode(value) ? value : "default";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function getErrorMessage(value: unknown): string {
  if (isRecord(value) && typeof value.message === "string") {
    return value.message;
  }

  return "보고서 응답을 확인하지 못했습니다.";
}

async function requestReport(
  mode: FixtureMode,
  signal: AbortSignal,
): Promise<Report | null> {
  const query = mode === "default" ? "" : `?mode=${mode}`;
  const response = await fetch(`/v1/reports/demo${query}`, {
    cache: "no-store",
    signal,
  });
  const payload: unknown = await response.json();

  if (!response.ok) {
    throw new Error(getErrorMessage(payload));
  }

  return parseReportResponse(payload).report;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "확인되지 않음";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeZone: "Asia/Seoul",
  }).format(date);
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function toDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.trim().split(/\r?\n/);
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trimEnd();
    if (line.trim() === "") {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      blocks.push({ kind: "code", text: codeLines.join("\n") });
      continue;
    }

    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(line);
    if (headingMatch) {
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2],
      });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ kind: "unordered-list", items });
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push({ kind: "ordered-list", items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ kind: "blockquote", text: quoteLines.join(" ") });
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() !== "" &&
      !/^#{1,3}\s+/.test(lines[index]) &&
      !/^[-*]\s+/.test(lines[index]) &&
      !/^\d+\.\s+/.test(lines[index]) &&
      !/^>\s?/.test(lines[index]) &&
      !lines[index].startsWith("```")
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(INLINE_MARKDOWN_PATTERN).filter(Boolean).map((part, index) => {
    if (part.startsWith("[") && part.includes("](")) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
      if (linkMatch && /^https?:\/\//i.test(linkMatch[2])) {
        return (
          <a
            href={linkMatch[2]}
            key={`${part}-${index}`}
            rel="noreferrer"
            target="_blank"
          >
            {linkMatch[1]}
          </a>
        );
      }
    }

    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }

    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={`${part}-${index}`}>{part.slice(1, -1)}</em>;
    }

    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    }

    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function MarkdownBody({ markdown }: { markdown: string }) {
  return (
    <div className="markdown-body">
      {parseMarkdown(markdown).map((block, index) => {
        const key = `${block.kind}-${index}`;
        if (block.kind === "heading") {
          if (block.level === 1) {
            return <h2 key={key}>{renderInlineMarkdown(block.text)}</h2>;
          }
          if (block.level === 2) {
            return <h3 key={key}>{renderInlineMarkdown(block.text)}</h3>;
          }
          return <h4 key={key}>{renderInlineMarkdown(block.text)}</h4>;
        }
        if (block.kind === "unordered-list") {
          return (
            <ul key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "ordered-list") {
          return (
            <ol key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
              ))}
            </ol>
          );
        }
        if (block.kind === "blockquote") {
          return <blockquote key={key}>{renderInlineMarkdown(block.text)}</blockquote>;
        }
        if (block.kind === "code") {
          return <pre key={key}>{block.text}</pre>;
        }
        return <p key={key}>{renderInlineMarkdown(block.text)}</p>;
      })}
    </div>
  );
}

function getEvidenceTrail(report: Report, claimId: string): EvidenceTrail[] {
  const evidenceById = new Map(
    report.evidence.map((evidence) => [evidence.evidence_id, evidence]),
  );
  const sourceById = new Map(
    report.sources.map((source) => [source.source_id, source]),
  );

  return report.claim_evidence_relations
    .filter((relation) => relation.claim_id === claimId)
    .flatMap((relation) => {
      const evidence = evidenceById.get(relation.evidence_id);
      const source = evidence ? sourceById.get(evidence.source_id) : undefined;
      if (!evidence || !source) {
        return [];
      }
      return [{ evidence, relation, source }];
    });
}

function StatusBadge({ status }: { status: Claim["status"] }) {
  const meta = CLAIM_STATUS_META[status];
  return (
    <span
      aria-label={`주장 상태: ${meta.label}`}
      className={`status-badge status-${status}`}
    >
      <span aria-hidden="true" className="status-icon">
        {meta.icon}
      </span>
      <span>{meta.label}</span>
    </span>
  );
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="site-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <span aria-hidden="true" className="brand-mark">
            <span />
            <span />
          </span>
          <span>ClaimGraph</span>
        </Link>
        <div className="topbar-meta">
          <span>보고서</span>
          <span className="topbar-divider" />
          <span>문장과 원문을 차례로 확인합니다.</span>
        </div>
      </header>
      {children}
    </div>
  );
}

function LoadingState() {
  return (
    <div aria-live="polite" className="state-card loading-card" role="status">
      <div className="state-kicker">보고서 불러오는 중</div>
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-line skeleton-line-wide" />
      <div className="skeleton skeleton-line" />
      <div className="loading-section">
        <div className="skeleton skeleton-line skeleton-line-short" />
        <div className="skeleton skeleton-block" />
        <div className="skeleton skeleton-block skeleton-block-short" />
      </div>
      <p className="state-supporting">보고서와 연결된 근거를 불러오는 중입니다.</p>
    </div>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="state-card" role="status">
      <div aria-hidden="true" className="state-symbol">
        —
      </div>
      <div className="state-kicker">보고서 없음</div>
      <h1>아직 보고서가 없습니다.</h1>
      <p>조사가 끝나면 이곳에서 결과와 근거를 확인할 수 있습니다.</p>
      <button className="button button-primary" onClick={onRetry} type="button">
        다시 불러오기
      </button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-card error-card" role="alert">
      <div aria-hidden="true" className="state-symbol">
        !
      </div>
      <div className="state-kicker">불러오기 오류</div>
      <h1>보고서를 불러오지 못했습니다.</h1>
      <p>{message}</p>
      <button className="button button-primary" onClick={onRetry} type="button">
        다시 불러오기
      </button>
    </div>
  );
}

function ReportOutline({ report }: { report: Report }) {
  const unsupportedCount = report.claims.filter(
    (claim) => claim.status === "unsupported",
  ).length;

  return (
    <aside aria-label="보고서 개요" className="trace-rail">
      <div className="rail-kicker">근거 안내</div>
      <p className="rail-title">문장에서 근거까지</p>
      <p className="rail-copy">
        문장에 담긴 주장과 그 근거를 차례로 확인합니다.
      </p>

      <div className="rail-stats">
        <div>
          <strong>{report.statements.length}</strong>
          <span>문장</span>
        </div>
        <div>
          <strong>{report.sources.length}</strong>
          <span>원문</span>
        </div>
      </div>

      <nav aria-label="보고서 문장" className="trace-index">
        {report.statements.map((statement, index) => {
          const claim = report.claims.find(
            (candidate) => candidate.claim_id === statement.claim_id,
          );
          return (
            <a
              className="trace-index-item"
              href={`#${toDomId(statement.statement_id)}`}
              key={statement.statement_id}
            >
              <span aria-hidden="true" className="trace-node">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span>
                <span className="trace-index-label">문장 {index + 1}</span>
                <span className="trace-index-status">
                  {claim ? CLAIM_STATUS_META[claim.status].label : "연결 누락"}
                </span>
              </span>
            </a>
          );
        })}
      </nav>

      {unsupportedCount > 0 && (
        <div className="rail-note">
          <span aria-hidden="true">∅</span>
          <p>
            {unsupportedCount}개 주장은 연결된 근거가 없어 ‘근거 부족’으로 남아 있습니다.
          </p>
        </div>
      )}
    </aside>
  );
}

function EvidenceCard({ trail }: { trail: EvidenceTrail }) {
  const { evidence, relation, source } = trail;
  return (
    <li className="evidence-item">
      <div className="evidence-item-heading">
        <span className="relation-label">
          <span aria-hidden="true">↳</span> {RELATION_LABEL[relation.relation_type]}
        </span>
      </div>
      <p className="evidence-quote">{evidence.quote_or_summary}</p>
      <details className="technical-details">
        <summary>근거 정보</summary>
        <code>근거 ID: {evidence.evidence_id}</code>
      </details>
      <div className="evidence-source">
        <div>
          <span className="source-label">원문</span>
          <strong>{source.title}</strong>
          <span className="source-meta">
            {source.publisher} · 위치: {evidence.locator}
          </span>
        </div>
        <a
          aria-label={`${source.title} 원문에서 근거 확인`}
          className="evidence-link"
          href={source.source_url ?? source.locator}
          rel="noreferrer"
          target="_blank"
        >
          원문에서 확인 <span aria-hidden="true">↗</span>
        </a>
      </div>
    </li>
  );
}

function StatementCard({
  index,
  report,
  statement,
}: {
  index: number;
  report: Report;
  statement: ReportStatement;
}) {
  const claim = report.claims.find(
    (candidate) => candidate.claim_id === statement.claim_id,
  );
  const trail = claim ? getEvidenceTrail(report, claim.claim_id) : [];
  const status = claim?.status ?? "unsupported";
  const statusMeta = CLAIM_STATUS_META[status];

  return (
    <li className={`statement-card statement-${status}`} id={toDomId(statement.statement_id)}>
      <div aria-hidden="true" className="statement-index">
        {String(index + 1).padStart(2, "0")}
      </div>
      <div className="statement-content">
        <div className="statement-eyebrow">보고서 문장</div>
        <p className="statement-text">{statement.text}</p>
        <div className={`claim-panel claim-panel-${status}`}>
          <div className="claim-panel-heading">
            <span className="claim-label">주장</span>
            {claim ? <StatusBadge status={claim.status} /> : <StatusBadge status="unsupported" />}
          </div>
          {claim ? (
            <>
              <p className="claim-text">{claim.text}</p>
              <div className="claim-meta">
                <span>근거 연결 정도 {formatConfidence(claim.confidence)}</span>
              </div>
              <details className="technical-details">
                <summary>기술 정보</summary>
                <code>주장 ID: {claim.claim_id}</code>
              </details>
              <p className="claim-description">
                <span aria-hidden="true">{statusMeta.icon}</span> {statusMeta.description}
              </p>
              {trail.length > 0 ? (
                <ul aria-label="연결된 근거" className="evidence-list">
                  {trail.map((item) => (
                    <EvidenceCard key={item.relation.relation_id} trail={item} />
                  ))}
                </ul>
              ) : (
                <div className="unsupported-callout">
                  <span aria-hidden="true">∅</span>
                  <div>
                    <strong>연결된 근거가 없습니다.</strong>
                    <p>확인할 근거가 없어 결과에서 제외하지 않고 ‘근거 부족’으로 표시했습니다.</p>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="unsupported-callout">
              <span aria-hidden="true">!</span>
              <div>
                <strong>이 문장에 연결된 주장을 찾을 수 없습니다.</strong>
                <p>현재 결과에서 연결 정보를 확인할 수 없습니다.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function ReportView({ report }: { report: Report }) {
  const unsupportedCount = report.claims.filter(
    (claim) => claim.status === "unsupported",
  ).length;

  return (
    <div className="page-frame">
      <div className="report-grid">
        <ReportOutline report={report} />
        <main className="report-column">
          <header className="report-header">
            <div className="report-kicker">
              <span>보고서</span>
            </div>
            <div className="report-header-row">
              <div>
                <h1>{report.title}</h1>
                <p className="report-question">{report.question}</p>
              </div>
              <span className={`report-status report-status-${report.status}`}>
                <span aria-hidden="true">{report.status === "failed" ? "!" : "·"}</span>
                {REPORT_STATUS_LABEL[report.status]}
              </span>
            </div>
            <div className="report-metadata">
              <span>작성 {formatDate(report.created_at)}</span>
              <span aria-hidden="true" className="metadata-dot" />
              <span>{report.statements.length}개 문장</span>
              <span aria-hidden="true" className="metadata-dot" />
              <span>{report.sources.length}개 원문</span>
            </div>
            <details className="technical-details report-technical-details">
              <summary>기술 정보</summary>
              <code>보고서 ID: {report.report_id}</code>
            </details>
          </header>

          {unsupportedCount > 0 && (
            <div className="report-notice" role="status">
              <span aria-hidden="true">∅</span>
              <p>
                <strong>근거가 부족한 주장도 결과에 남겨 두었습니다.</strong>
                <span>
                  연결된 근거가 없는 {unsupportedCount}개 항목은 판단을 보류할 수 있도록
                  ‘근거 부족’으로 표시합니다.
                </span>
              </p>
            </div>
          )}

          <section aria-labelledby="report-body-heading" className="report-section">
            <div className="section-heading">
              <div>
                <span className="section-kicker">01 / 보고서 내용</span>
                <h2 id="report-body-heading">보고서 본문</h2>
              </div>
              <span className="section-hint">읽기 쉬운 형식</span>
            </div>
            <MarkdownBody markdown={report.markdown} />
          </section>

          <section aria-labelledby="claim-trace-heading" className="report-section claim-trace-section">
            <div className="section-heading">
              <div>
                <span className="section-kicker">02 / 근거 확인</span>
                <h2 id="claim-trace-heading">문장에서 근거 확인</h2>
              </div>
              <span className="section-hint">주장 → 근거 → 원문</span>
            </div>
            <ol className="statement-list">
              {report.statements.map((statement, index) => (
                <StatementCard
                  index={index}
                  key={statement.statement_id}
                  report={report}
                  statement={statement}
                />
              ))}
            </ol>
          </section>

          <footer className="report-footer">
            <span>저장된 결과와 연결된 원문을 보여드리고 있습니다.</span>
            <details className="technical-details">
              <summary>기술 정보</summary>
              <code>조사 ID: {report.research_run_id}</code>
            </details>
          </footer>
        </main>
      </div>
    </div>
  );
}

export default function Home() {
  const [mode, setMode] = useState<FixtureMode>("default");
  const [state, setState] = useState<ReportState>({ kind: "loading" });

  const loadReport = useCallback(async (nextMode: FixtureMode) => {
    const controller = new AbortController();
    setMode(nextMode);
    setState({ kind: "loading" });

    try {
      const report = await requestReport(nextMode, controller.signal);
      setState(report ? { kind: "ready", report } : { kind: "empty" });
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setState({
        kind: "error",
        message:
          error instanceof Error ? error.message : "잠시 후 다시 시도해 주세요.",
      });
    }
  }, []);

  useEffect(() => {
    const initialMode = readFixtureMode();
    const controller = new AbortController();

    void requestReport(initialMode, controller.signal)
      .then((report) => {
        setMode(initialMode);
        setState(report ? { kind: "ready", report } : { kind: "empty" });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setMode(initialMode);
        setState({
          kind: "error",
          message:
            error instanceof Error ? error.message : "잠시 후 다시 시도해 주세요.",
        });
      });

    return () => controller.abort();
  }, []);

  const retry = useCallback(() => {
    void loadReport(mode);
  }, [loadReport, mode]);

  const content = useMemo(() => {
    if (state.kind === "loading") {
      return <LoadingState />;
    }
    if (state.kind === "empty") {
      return <EmptyState onRetry={retry} />;
    }
    if (state.kind === "error") {
      return <ErrorState message={state.message} onRetry={retry} />;
    }
    return <ReportView report={state.report} />;
  }, [retry, state]);

  return <AppShell>{content}</AppShell>;
}
