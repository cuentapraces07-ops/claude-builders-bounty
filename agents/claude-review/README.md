# Claude PR review agent

This directory contains a dependency-free CLI that fetches a public GitHub PR,
reviews its diff, and emits a structured Markdown report. With
`ANTHROPIC_API_KEY` set it calls `claude-sonnet-4-20250514`; with no key it
falls back to a deterministic local baseline and labels that mode in the
report. The fallback is for safe previews and tests, not a claim that Claude
reviewed the PR.

## Setup and use

1. Copy this directory into a project with Python 3.10+.
2. Optionally set `ANTHROPIC_API_KEY` and run:
   `python agents/claude-review/claude_review.py --pr https://github.com/owner/repo/pull/123`.
3. Add `--output review.md` to save the report, then inspect it before merging.

The client accepts only HTTPS `github.com` pull-request URLs, caps fetched
diffs at 1 MB, never executes the target repository, and does not print API
keys. The Claude request is limited to the PR metadata and diff; the repository
is not granted credentials or write access.

## Output contract

Every report contains a 2–3 sentence summary, an identified-risks list,
improvement suggestions, and a `Low`/`Medium`/`High` confidence score. The
engine and diff scope are recorded so a reviewer can distinguish an API review
from the offline baseline.

## Tests

Run the standard-library unit tests from the repository root:

```bash
python -m unittest discover -s agents/claude-review/tests -v
```

Two real public pull requests are included in `samples/`; they were fetched
without credentials and rendered with `--offline` so the sample output is
reproducible without an API key.
