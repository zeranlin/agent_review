# agent_review

`agent_review` is a harness-engineering style scaffold for reviewing Chinese government procurement tender documents.

The repository is designed around one principle: humans define policy, risk tolerance, and acceptance criteria; agents execute the repeatable review loop.

This version now focuses on:

- turning procurement review into a legible, layered agent workflow
- keeping repository knowledge as the system of record
- making every finding traceable to evidence in the tender document
- aligning the business flow, architecture, and review dimensions to the repository SOP
- creating a minimal local CLI that can be expanded into a full multi-agent review harness

## Why this repository is structured this way

The architecture follows key ideas from OpenAI's writing on harness engineering and agent loops:

- engineers should design environments, specify intent, and build feedback loops for reliable agent work
- repository knowledge should be the system of record, instead of a single giant instruction file
- architecture boundaries and output contracts should be enforced centrally
- review should run in loops, with self-checks and explicit escalation when judgment is required

Sources:

- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)
- [Unrolling the Codex agent loop](https://openai.com/zh-Hans-CN/index/unrolling-the-codex-agent-loop/)

## Repository layout

```text
docs/
  business_design.md        # SOP-aligned business design
  dimension_design.md       # review dimensions and risk taxonomy
  harness_architecture.md   # target agent architecture and control loop
  review_workflow.md        # procurement review stages and human escalation rules
src/agent_review/
  checklist.py              # review dimensions and default control points
  engine.py                 # orchestration loop for running the review
  models.py                 # typed review state, findings, evidence, and reports
  reporting.py              # markdown and json rendering helpers
  cli.py                    # local command line entry point
tests/
  test_engine.py            # lightweight verification of the scaffold
AGENTS.md                   # repository instructions for future agents
pyproject.toml              # package metadata and test config
```

## Review model

The tender review loop is aligned to the SOP's nine stages:

1. ingest the bidding document and normalize it into reviewable text units
2. identify the file type and declare the review scope
3. locate key sections
4. extract key clauses
5. run rule-based risk matching
6. perform cross-clause consistency checks
7. grade risks
8. form an overall conclusion
9. render a final report with issue-to-suggestion mappings

This repo currently ships a minimal deterministic implementation of that loop so the architecture is executable before model integration.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m agent_review.cli --input sample.txt --format markdown
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest
```

## Current scope

This version does not claim to provide legal conclusions by itself.

It provides:

- a structured compliance review workflow
- a finding schema with severity, confidence, rationale, and evidence
- file type, scope, section index, clause extraction, risk hit, and consistency artifacts
- a reusable checklist for common procurement review dimensions
- a minimal CLI and test suite

It does not yet provide:

- OCR / PDF parsing
- direct LLM integration
- statutory rule retrieval from a legal knowledge base
- automatic cross-checking against local procurement regulations

Those are the next layers to add on top of the harness.
