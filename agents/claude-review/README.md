# Claude PR review agent

This directory contains a dependency-free CLI that fetches a public GitHub PR,
reviews its diff, and emits a structured Markdown report. With
`ANTHROPIC_API_KEY` set it calls `claude-sonnet-4-6`; with no key it
falls back to a deterministic local baseline and labels that mode in the
report. `--offline` disables Anthropic API calls but still fetches the public
GitHub metadata and diff; it is not a network-free mode. The fallback is not
a claim that Claude reviewed the PR.

## Setup and use

1. Copy this directory into a project with Python 3.10+.
2. From the repository root, run the included executable:
   `./bin/claude-review --pr https://github.com/owner/repo/pull/123`.
   On Windows, invoke the same entry point with
   `python bin/claude-review --pr https://github.com/owner/repo/pull/123`.
3. Optionally set `ANTHROPIC_API_KEY`; add `--output review.md` to save the
   report, then inspect it before merging.

The client accepts only HTTPS `github.com` pull-request URLs, caps fetched
diffs at 1 MB, and falls back to GitHub's paginated PR-files API if the `.diff`
endpoint fails. If GitHub omits any file patch or the page limit is reached,
the report marks coverage partial and forces confidence to Low. It never
executes the target repository and does not print API keys. The Claude request
is limited to the PR metadata and diff; the repository
is not granted credentials or write access. PR titles, bodies, and diffs are
treated as untrusted data: instructions embedded in a diff are not followed,
and the reviewer does not post comments or modify repositories. The local
baseline also flags common destructive shell/SQL patterns such as `rm -rf`,
`git push --force`, `DROP TABLE`, `TRUNCATE`, and unqualified `DELETE FROM` for
explicit maintainer review.
The baseline also flags common prompt-injection and credential-exfiltration
phrases in PR content so they remain review data rather than instructions.
Claude's response is parsed as a bounded JSON review: the summary must contain
2–3 sentences, list fields must contain strings, oversized output is rejected,
and invalid responses fall back to a deterministic three-sentence local pass.
Untrusted titles and review prose are flattened and escaped before Markdown
rendering so they cannot add headings, links, or raw HTML to the generated
report.
Claude receives at most 8,000 characters of PR body and 50,000 characters of
diff. If either limit is exceeded, the report marks the review as partial,
states what was omitted, and forces confidence to Low.

## Output contract

Every report uses the four-section contract `Summary`, `Risks`, `Improvement
suggestions`, and `Confidence` (`Low`/`Medium`/`High`). The engine and diff
scope are recorded as metadata so a reviewer can distinguish an API review
from the offline baseline. The CLI only emits a report; it never posts a
comment or changes a repository.

## Tests

Run the standard-library unit tests from the repository root:

```bash
python -m unittest discover -s agents/claude-review/tests -v
```

Two real public pull requests are included in `samples/`; they were fetched
without credentials and rendered with `--offline` so the sample output is
reproducible without an API key.

The original implementation used `claude-sonnet-4-20250514`, which Anthropic
retired on June 15, 2026. This implementation uses Anthropic's documented
replacement, `claude-sonnet-4-6`; no live API call is made by the offline
tests.
