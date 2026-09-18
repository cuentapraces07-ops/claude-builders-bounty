#!/usr/bin/env python3
"""Review a public GitHub pull request and emit a structured Markdown report.

The CLI uses Claude when ANTHROPIC_API_KEY is available. Without a key it uses
an intentionally conservative, deterministic local pass so the command remains
useful for previews and tests; the report labels that mode explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


MAX_DIFF_BYTES = 1_000_000
GITHUB_PULL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9][0-9]*)/?$"
)


@dataclass(frozen=True)
class PullRequest:
    url: str
    owner: str
    repo: str
    number: int
    title: str
    body: str
    diff: str


@dataclass(frozen=True)
class Review:
    summary: str
    risks: tuple[str, ...]
    suggestions: tuple[str, ...]
    confidence: str
    mode: str


def _request(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "claude-review-bounty-agent/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(MAX_DIFF_BYTES + 1)
    if len(data) > MAX_DIFF_BYTES:
        raise ValueError(f"response exceeded {MAX_DIFF_BYTES} bytes: {url}")
    return data


def parse_pull_url(url: str) -> tuple[str, str, int]:
    match = GITHUB_PULL_RE.fullmatch(url.strip())
    if not match:
        raise ValueError("--pr must be an HTTPS github.com owner/repo/pull/number URL")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def fetch_pull(url: str) -> PullRequest:
    owner, repo, number = parse_pull_url(url)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    metadata = json.loads(_request(api_url, "application/vnd.github+json").decode("utf-8"))
    if not isinstance(metadata, dict) or not metadata.get("title"):
        raise ValueError("GitHub API returned no pull-request metadata")
    diff = _request(f"https://github.com/{owner}/{repo}/pull/{number}.diff", "text/plain").decode(
        "utf-8", errors="replace"
    )
    return PullRequest(
        url=url.rstrip("/"),
        owner=owner,
        repo=repo,
        number=number,
        title=str(metadata["title"]),
        body=str(metadata.get("body") or ""),
        diff=diff,
    )


def changed_files(diff: str) -> tuple[str, ...]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return tuple(dict.fromkeys(files))


def diff_stats(diff: str) -> tuple[int, int, int]:
    additions = deletions = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return len(changed_files(diff)), additions, deletions


def heuristic_review(pr: PullRequest) -> Review:
    """Produce a useful baseline without pretending that a model was called."""

    files, additions, deletions = diff_stats(pr.diff)
    lower = pr.diff.lower()
    risks: list[str] = []
    suggestions: list[str] = []

    patterns = (
        (r"\beval\s*\(", "Dynamic eval-like execution deserves a security review."),
        (r"shell\s*=\s*true|subprocess\.", "Process execution is present; validate arguments and avoid shell interpolation."),
        (r"(password|secret|api[_-]?key|token)\s*[:=]", "A credential-shaped assignment appears in the diff; verify it is not a real secret."),
        (r"select\s+.+\s+from|insert\s+into|update\s+.+\s+set", "SQL is present; verify every value is parameterized and authorization is enforced."),
        (r"except\s*:\s*$|catch\s*\([^)]*\)\s*\{", "A broad exception handler may hide failures; preserve actionable error context."),
        (r"todo|fixme", "TODO/FIXME markers remain; either track them or remove them before merge."),
    )
    for pattern, message in patterns:
        if re.search(pattern, lower, flags=re.MULTILINE):
            risks.append(message)

    if not risks:
        risks.append("No high-signal risk pattern was detected by the local pass; tests and domain review are still required.")
    if files > 10:
        suggestions.append("Split or justify the broad file surface so reviewers can isolate behavior changes.")
    if additions + deletions > 500:
        suggestions.append("Add focused tests for the highest-risk paths and consider smaller reviewable commits.")
    if not re.search(r"test|spec|fixture", lower):
        suggestions.append("Add or update a regression test for the changed behavior.")
    suggestions.append("Run the repository's lint, type-check, and test commands in CI before merging.")

    summary = (
        f"The pull request changes {files} file(s), adding {additions} line(s) and removing {deletions}. "
        f"Its title is {pr.title!r}. The deterministic baseline reviews the fetched diff without executing repository code."
    )
    confidence = "Medium" if files and additions + deletions <= 500 else "Low"
    return Review(summary, tuple(risks), tuple(dict.fromkeys(suggestions)), confidence, "local heuristic (no Claude API key)")


def _claude_review(pr: PullRequest, api_key: str) -> Review:
    prompt = f"""Review this GitHub pull request. Return JSON only with keys summary (2-3 sentences), risks (array of strings), suggestions (array of strings), and confidence (Low, Medium, or High). Be specific and do not claim tests were run unless the diff proves it.\n\nURL: {pr.url}\nTitle: {pr.title}\nBody:\n{pr.body[:8000]}\n\nDiff:\n{pr.diff[:50000]}"""
    payload = json.dumps(
        {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1200,
            "system": "You are a careful software reviewer. Analyze only the supplied pull request.",
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "claude-review-bounty-agent/1.0",
            "anthropic-version": "2023-06-01",
            "x-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read(MAX_DIFF_BYTES).decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Claude API request failed: {exc}") from exc
    content = data.get("content") if isinstance(data, dict) else None
    text = content[0].get("text", "") if isinstance(content, list) and content else ""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise RuntimeError("Claude response did not contain a JSON review")
    result = json.loads(match.group(0))
    confidence = str(result.get("confidence", "Low"))
    if confidence not in {"Low", "Medium", "High"}:
        confidence = "Low"
    return Review(
        str(result.get("summary", "No summary returned.")),
        tuple(str(value) for value in result.get("risks", [])),
        tuple(str(value) for value in result.get("suggestions", [])),
        confidence,
        "Claude API (claude-sonnet-4-20250514)",
    )


def review(pr: PullRequest, api_key: str | None) -> Review:
    if api_key:
        try:
            return _claude_review(pr, api_key)
        except RuntimeError as exc:
            print(f"warning: {exc}; using local baseline", file=sys.stderr)
    return heuristic_review(pr)


def render(pr: PullRequest, result: Review) -> str:
    files, additions, deletions = diff_stats(pr.diff)
    lines = [
        f"# Pull request review: {pr.title}",
        "",
        f"- URL: {pr.url}",
        f"- Scope: {files} changed file(s), +{additions}/-{deletions}",
        f"- Engine: {result.mode}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
        "## Identified risks",
        "",
    ]
    lines.extend(f"- {risk}" for risk in result.risks)
    lines.extend(["", "## Improvement suggestions", ""])
    lines.extend(f"- {suggestion}" for suggestion in result.suggestions)
    lines.extend(["", f"## Confidence: {result.confidence}", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a GitHub pull request and print structured Markdown.")
    parser.add_argument("--pr", required=True, help="HTTPS GitHub pull request URL")
    parser.add_argument("--output", "-o", help="Write Markdown to this file instead of stdout")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Disable Claude API calls and use the local review (GitHub metadata/diff are still fetched)",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pr = fetch_pull(args.pr)
        result = review(pr, None if args.offline else os.environ.get("ANTHROPIC_API_KEY"))
        output = render(pr, result)
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(output + "\n")
        else:
            print(output)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
