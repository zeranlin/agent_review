# AGENTS.md

## Purpose

This repository builds an agent-first government procurement tender review system.

Agents should optimize for:

- evidence-backed findings
- explicit uncertainty
- narrow, typed interfaces between stages
- repository docs as the source of truth

## Golden principles

1. Every finding must cite concrete evidence from the source document.
2. Findings should distinguish between `confirmed_issue`, `warning`, `missing_evidence`, and `manual_review_required`.
3. Rules belong in typed code or repository docs, not in ad hoc prompt prose.
4. The review loop should prefer escalation over bluffing whenever legal interpretation is ambiguous.
5. New checks must be added through the shared checklist and report schema.
6. Avoid giant instruction files; keep knowledge close to the domain module that uses it.

## Architecture rules

- `models.py` owns shared contracts.
- `checklist.py` defines reusable review dimensions.
- `engine.py` orchestrates the loop, but does not hardcode presentation.
- `reporting.py` renders output, but does not decide findings.
- docs describe the intended system behavior and escalation policy.

## Review expectations

When extending this repository:

- prefer deterministic pre-checks before adding model calls
- make uncertainty explicit in the output
- add or update tests with every behavior change
- encode repeated review feedback back into the repository
