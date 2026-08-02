# Evaluation Questions

This directory defines representative AI and technology research questions for ClaimGraph evaluation.

## Files

- `questions.json` contains 20 representative questions.
- `expectations/ai-tech-001.json` through `expectations/ai-tech-005.json` define the phase 1 Claim/Evidence fixtures.

## Question Coverage

The question set covers:

- Deterministic technical facts, such as standard-library additions and canonical paper claims.
- Architecture and implementation tradeoffs for LLM adaptation, retrieval, observability, authentication, and deployment.
- Time-sensitive release or compatibility research that must cite current official sources.
- Conflicting evidence cases where the answer should preserve uncertainty instead of forcing a single supported Claim.

Exactly five questions are marked with `phase1_candidate: true`. At least two questions use `difficulty: "deterministic"` so phase 1 can include stable parsing and citation checks.

## Evaluation Criteria

An answer passes when:

- Every supported Claim has at least one relevant Evidence item from the required `source_types`.
- Evidence locators are specific enough to replay the judgment, such as a paper section, release note, documentation page, benchmark table, or compatibility entry.
- Time-sensitive answers include an explicit answer date and use current official documentation or release notes when available.
- Tradeoff questions include both recommendation conditions and material caveats.
- Conflict questions keep competing Claims separate and do not hide unresolved uncertainty.

## Unsupported Rules

A Claim must be marked `unsupported` when:

- It has no Evidence.
- The Evidence is irrelevant to the Claim or only supports a weaker statement.
- The answer relies on stale, unofficial, or missing-source data for a time-sensitive fact.
- The answer states a universal conclusion where the fixture expects task-specific validation or conflicting evidence.
- The answer invents product behavior, benchmark results, release versions, or compatibility guarantees that are not present in the cited source.
