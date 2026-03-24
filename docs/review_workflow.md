# Review Workflow

## Review objective

Assess whether a government procurement tender document is procedurally complete, substantively fair, and suitable for lawful competition.

## Minimal operating workflow

1. Confirm the document can be parsed into text.
2. Split the text into numbered sections or stable chunks.
3. Run the default review checklist.
4. Record only findings that include at least one evidence anchor.
5. Record missing evidence when the document appears incomplete.
6. Escalate issues requiring legal interpretation or unavailable attachments.
7. Render the report in markdown and json.

## Finding categories

- `confirmed_issue`: likely non-compliance supported by document evidence
- `warning`: possible issue that merits attention but is not yet confirmed
- `missing_evidence`: the document lacks material needed for a full conclusion
- `manual_review_required`: legal or contextual judgment is needed
- `pass`: the dimension was checked and no issue was found

## Suggested future rule sources

This scaffold intentionally does not hardcode Chinese legal citations yet.

The next iteration should introduce machine-readable rule packs for:

- Government Procurement Law
- tendering and bidding implementing rules
- Ministry of Finance normative guidance
- local procurement supervision requirements

Each rule pack should define:

- rule id
- short title
- trigger patterns
- severity guidance
- required evidence
- escalation threshold
