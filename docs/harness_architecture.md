# Harness Architecture For Tender Compliance Review

## Design target

The goal is not a single prompt that "judges" a tender document.

The goal is a review harness that makes agent work reliable:

- the repository stores the workflow, review dimensions, schemas, and escalation policy
- the runtime breaks review into bounded stages
- each stage emits structured artifacts that the next stage can validate
- humans intervene only when legal judgment or policy choice is genuinely required

This mirrors the harness-engineering idea that engineers should design environments, specify intent, and build feedback loops rather than rely on one-shot prompting.

## Core principles translated to procurement review

### 1. Humans steer, agents execute

In this domain, humans define:

- the legal and policy basis for review
- which procurement risks matter most
- severity thresholds
- when an issue must be escalated for legal or supervisory review

Agents execute:

- document decomposition
- evidence extraction
- clause-level screening
- contradiction detection
- report drafting
- iterative self-review

### 2. Repository knowledge is the system of record

The repository should eventually hold:

- review dimensions
- output schemas
- escalation thresholds
- rule references
- test fixtures and acceptance examples

This is better than keeping all domain knowledge inside a single prompt because the harness can inspect, validate, and evolve it.

### 3. Legibility first

The agent should be able to inspect:

- the original tender text
- extracted sections and pagination anchors
- rule basis used for each conclusion
- unresolved ambiguities
- missing attachments or missing clauses

If the system cannot expose these artifacts, it cannot reliably review or defend its conclusions.

### 4. Enforce boundaries centrally

The review harness should separate:

- ingestion
- review planning
- rule execution
- evidence validation
- adjudication
- reporting

This prevents a single component from silently inventing legal conclusions without evidence.

### 5. Use loops, not single-pass generation

The review runtime should loop until:

- required dimensions were checked
- each finding has evidence
- contradictions were resolved or escalated
- the final report includes confidence and next actions

## Proposed control loop

```text
user request
  -> ingest document
  -> normalize into sections / clauses / attachments
  -> select checklist dimensions
  -> run dimension reviewers
  -> collect findings + evidence
  -> run self-review and contradiction checks
  -> decide: accept / escalate / incomplete
  -> render report
```

## Target reviewer roles

As the system grows, the single local orchestrator can evolve into specialized agents:

1. `document_ingestor`
   Reads PDF / DOCX / OCR output and produces normalized text units.
2. `review_planner`
   Decides which checks apply based on procurement type and document completeness.
3. `compliance_reviewer`
   Screens for discriminatory terms, qualification risk, scoring defects, process defects, and contract-risk clauses.
4. `evidence_auditor`
   Verifies that every issue is backed by a source citation.
5. `adjudicator`
   Downgrades, merges, or escalates findings when uncertainty remains.
6. `report_writer`
   Produces regulator-friendly markdown, json, or structured review output.

## Review dimensions

The initial default checklist covers:

- procurement scope clarity
- bidder qualification fairness
- evaluation criteria clarity and objectivity
- discriminatory or restrictive terms
- timeline and process completeness
- contract terms and risk allocation
- missing required information or attachments

## Escalation policy

The harness should escalate when:

- the evidence is incomplete or contradictory
- the issue turns on local legal interpretation not encoded in the repository
- the document appears missing annexes required for the conclusion
- the severity is high and the model confidence is not high

## Artifact contracts

Every run should produce:

- normalized document text
- structured findings
- evidence snippets
- manual-review queue
- final report

These artifacts should be durable so future agents can continue the loop without rereading everything from scratch.
