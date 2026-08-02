export type SourceType = "web" | "document" | "paper" | "dataset" | "api" | "manual";
export type EvidenceKind = "quote" | "summary" | "table" | "metric" | "observation";
export type ClaimStatus = "unsupported" | "supported" | "refuted" | "mixed" | "needs_review";
export type ClaimEvidenceRelationType = "supports" | "refutes" | "qualifies" | "mentions";
export type ReportStatus = "draft" | "ready" | "published" | "failed";

export type Source = {
  source_id: string;
  research_run_id: string;
  source_type: SourceType;
  title: string;
  locator: string;
  source_url: string | null;
  publisher?: string;
  retrieved_at: string;
  content_hash: string;
};

export type Evidence = {
  evidence_id: string;
  source_id: string;
  research_run_id: string;
  kind: EvidenceKind;
  quote_or_summary: string;
  locator: string;
  collected_at: string;
  content_hash: string;
};

export type Claim = {
  claim_id: string;
  research_run_id: string;
  text: string;
  status: ClaimStatus;
  confidence: number;
  created_at: string;
};

export type ClaimEvidenceRelation = {
  relation_id: string;
  claim_id: string;
  evidence_id: string;
  relation_type: ClaimEvidenceRelationType;
  confidence: number;
  created_at: string;
};

export type ReportStatement = {
  statement_id: string;
  report_id: string;
  claim_id: string;
  position: number;
  text: string;
  created_at: string;
};

export type Report = {
  report_id: string;
  research_run_id: string;
  question: string;
  title: string;
  status: ReportStatus;
  markdown: string;
  created_at: string;
  statements: ReportStatement[];
  claims: Claim[];
  evidence: Evidence[];
  sources: Source[];
  claim_evidence_relations: ClaimEvidenceRelation[];
};

export type ReportResponse = {
  report: Report | null;
};

const SOURCE_TYPES = ["web", "document", "paper", "dataset", "api", "manual"] as const;
const EVIDENCE_KINDS = ["quote", "summary", "table", "metric", "observation"] as const;
const CLAIM_STATUSES = [
  "unsupported",
  "supported",
  "refuted",
  "mixed",
  "needs_review",
] as const;
const RELATION_TYPES = ["supports", "refutes", "qualifies", "mentions"] as const;
const REPORT_STATUSES = ["draft", "ready", "published", "failed"] as const;
const SHA256_PATTERN = /^sha256:[a-f0-9]{64}$/;

export function parseReportResponse(value: unknown): ReportResponse {
  const response = requireRecord(value, "ReportResponse");
  if (!("report" in response)) {
    throw new TypeError("ReportResponse.report is required");
  }

  return {
    report: response.report === null ? null : parseReport(response.report),
  };
}

function parseReport(value: unknown): Report {
  const record = requireRecord(value, "Report");
  const report: Report = {
    report_id: requireString(record.report_id, "Report.report_id"),
    research_run_id: requireString(record.research_run_id, "Report.research_run_id"),
    question: requireString(record.question, "Report.question"),
    title: requireString(record.title, "Report.title"),
    status: requireEnum(record.status, REPORT_STATUSES, "Report.status"),
    markdown: requireString(record.markdown, "Report.markdown"),
    created_at: requireString(record.created_at, "Report.created_at"),
    statements: requireArray(record.statements, "Report.statements").map(parseStatement),
    claims: requireArray(record.claims, "Report.claims").map(parseClaim),
    evidence: requireArray(record.evidence, "Report.evidence").map(parseEvidence),
    sources: requireArray(record.sources, "Report.sources").map(parseSource),
    claim_evidence_relations: requireArray(
      record.claim_evidence_relations,
      "Report.claim_evidence_relations",
    ).map(parseRelation),
  };

  if (report.statements.length === 0) {
    throw new TypeError("Report.statements must not be empty");
  }
  validateReportGraph(report);
  return report;
}

function parseSource(value: unknown): Source {
  const record = requireRecord(value, "Source");
  const sourceUrl = "source_url" in record
    ? record.source_url === null
      ? null
      : requireString(record.source_url, "Source.source_url")
    : null;

  if (sourceUrl !== null && !/^https:\/\//i.test(sourceUrl)) {
    throw new TypeError("Source.source_url must use HTTPS");
  }

  return {
    source_id: requireString(record.source_id, "Source.source_id"),
    research_run_id: requireString(record.research_run_id, "Source.research_run_id"),
    source_type: requireEnum(record.source_type, SOURCE_TYPES, "Source.source_type"),
    title: requireString(record.title, "Source.title"),
    locator: requireString(record.locator, "Source.locator"),
    source_url: sourceUrl,
    publisher: optionalString(record.publisher, "Source.publisher"),
    retrieved_at: requireString(record.retrieved_at, "Source.retrieved_at"),
    content_hash: requireHash(record.content_hash, "Source.content_hash"),
  };
}

function parseEvidence(value: unknown): Evidence {
  const record = requireRecord(value, "Evidence");
  return {
    evidence_id: requireString(record.evidence_id, "Evidence.evidence_id"),
    source_id: requireString(record.source_id, "Evidence.source_id"),
    research_run_id: requireString(record.research_run_id, "Evidence.research_run_id"),
    kind: requireEnum(record.kind, EVIDENCE_KINDS, "Evidence.kind"),
    quote_or_summary: requireString(record.quote_or_summary, "Evidence.quote_or_summary"),
    locator: requireString(record.locator, "Evidence.locator"),
    collected_at: requireString(record.collected_at, "Evidence.collected_at"),
    content_hash: requireHash(record.content_hash, "Evidence.content_hash"),
  };
}

function parseClaim(value: unknown): Claim {
  const record = requireRecord(value, "Claim");
  return {
    claim_id: requireString(record.claim_id, "Claim.claim_id"),
    research_run_id: requireString(record.research_run_id, "Claim.research_run_id"),
    text: requireString(record.text, "Claim.text"),
    status: requireEnum(record.status, CLAIM_STATUSES, "Claim.status"),
    confidence: requireConfidence(record.confidence, "Claim.confidence"),
    created_at: requireString(record.created_at, "Claim.created_at"),
  };
}

function parseRelation(value: unknown): ClaimEvidenceRelation {
  const record = requireRecord(value, "ClaimEvidenceRelation");
  return {
    relation_id: requireString(record.relation_id, "ClaimEvidenceRelation.relation_id"),
    claim_id: requireString(record.claim_id, "ClaimEvidenceRelation.claim_id"),
    evidence_id: requireString(record.evidence_id, "ClaimEvidenceRelation.evidence_id"),
    relation_type: requireEnum(
      record.relation_type,
      RELATION_TYPES,
      "ClaimEvidenceRelation.relation_type",
    ),
    confidence: requireConfidence(
      record.confidence,
      "ClaimEvidenceRelation.confidence",
    ),
    created_at: requireString(record.created_at, "ClaimEvidenceRelation.created_at"),
  };
}

function parseStatement(value: unknown): ReportStatement {
  const record = requireRecord(value, "ReportStatement");
  return {
    statement_id: requireString(record.statement_id, "ReportStatement.statement_id"),
    report_id: requireString(record.report_id, "ReportStatement.report_id"),
    claim_id: requireString(record.claim_id, "ReportStatement.claim_id"),
    position: requireInteger(record.position, "ReportStatement.position"),
    text: requireString(record.text, "ReportStatement.text"),
    created_at: requireString(record.created_at, "ReportStatement.created_at"),
  };
}

function validateReportGraph(report: Report): void {
  const reportStatementIds = uniqueIds(
    report.statements.map((statement) => statement.statement_id),
    "Report statements",
  );
  const claimIds = uniqueIds(
    report.claims.map((claim) => claim.claim_id),
    "Claim",
  );
  const evidenceIds = uniqueIds(
    report.evidence.map((evidence) => evidence.evidence_id),
    "Evidence",
  );
  const sourceIds = uniqueIds(
    report.sources.map((source) => source.source_id),
    "Source",
  );
  uniqueIds(
    report.claim_evidence_relations.map((relation) => relation.relation_id),
    "ClaimEvidenceRelation",
  );

  if (reportStatementIds.size !== report.statements.length) {
    throw new TypeError("Report statements must have unique IDs");
  }

  for (const statement of report.statements) {
    if (statement.report_id !== report.report_id) {
      throw new TypeError(`ReportStatement ${statement.statement_id} has the wrong report ID`);
    }
    if (!claimIds.has(statement.claim_id)) {
      throw new TypeError(`ReportStatement ${statement.statement_id} references a missing Claim`);
    }
  }

  for (const claim of report.claims) {
    if (claim.research_run_id !== report.research_run_id) {
      throw new TypeError(`Claim ${claim.claim_id} has the wrong ResearchRun ID`);
    }
  }

  for (const source of report.sources) {
    if (source.research_run_id !== report.research_run_id) {
      throw new TypeError(`Source ${source.source_id} has the wrong ResearchRun ID`);
    }
  }

  for (const evidence of report.evidence) {
    if (evidence.research_run_id !== report.research_run_id) {
      throw new TypeError(`Evidence ${evidence.evidence_id} has the wrong ResearchRun ID`);
    }
    if (!sourceIds.has(evidence.source_id)) {
      throw new TypeError(`Evidence ${evidence.evidence_id} references a missing Source`);
    }
  }

  const relationsByClaim = new Map<string, ClaimEvidenceRelation[]>();
  for (const relation of report.claim_evidence_relations) {
    if (!claimIds.has(relation.claim_id)) {
      throw new TypeError(`Relation ${relation.relation_id} references a missing Claim`);
    }
    if (!evidenceIds.has(relation.evidence_id)) {
      throw new TypeError(`Relation ${relation.relation_id} references missing Evidence`);
    }
    const relations = relationsByClaim.get(relation.claim_id) ?? [];
    relationsByClaim.set(relation.claim_id, [...relations, relation]);
  }

  for (const claim of report.claims) {
    const relations = relationsByClaim.get(claim.claim_id) ?? [];
    if (claim.status === "unsupported") {
      continue;
    }
    if (relations.length === 0) {
      throw new TypeError(`Claim ${claim.claim_id} requires an Evidence relation`);
    }
    if (claim.status === "supported" && !relations.some((item) => item.relation_type === "supports")) {
      throw new TypeError(`Claim ${claim.claim_id} requires a supports relation`);
    }
    if (claim.status === "refuted" && !relations.some((item) => item.relation_type === "refutes")) {
      throw new TypeError(`Claim ${claim.claim_id} requires a refutes relation`);
    }
    if (
      claim.status === "mixed" &&
      (!relations.some((item) => item.relation_type === "supports") ||
        !relations.some((item) => item.relation_type === "refutes"))
    ) {
      throw new TypeError(`Claim ${claim.claim_id} requires both supports and refutes relations`);
    }
  }
}

function uniqueIds(values: string[], label: string): Set<string> {
  const ids = new Set(values);
  if (ids.size !== values.length) {
    throw new TypeError(`${label} IDs must be unique`);
  }
  return ids;
}

function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new TypeError(`${field} must be an array`);
  }
  return value;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${field} must be a non-empty string`);
  }
  return value;
}

function optionalString(value: unknown, field: string): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  return requireString(value, field);
}

function requireEnum<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  field: string,
): Values[number] {
  if (typeof value !== "string" || !values.includes(value)) {
    throw new TypeError(`${field} has an unsupported value`);
  }
  return value as Values[number];
}

function requireConfidence(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new TypeError(`${field} must be a number from 0 to 1`);
  }
  return value;
}

function requireInteger(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new TypeError(`${field} must be a non-negative integer`);
  }
  return value;
}

function requireHash(value: unknown, field: string): string {
  const hash = requireString(value, field);
  if (!SHA256_PATTERN.test(hash)) {
    throw new TypeError(`${field} must be a sha256 hash`);
  }
  return hash;
}
