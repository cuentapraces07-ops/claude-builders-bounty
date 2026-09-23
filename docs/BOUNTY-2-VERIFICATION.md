# Bounty #2 local verification

This evidence records what can be verified locally for the Next.js + SQLite
`CLAUDE.md` template. It is not a claim that Claude Code, a deployment, or a
payment was observed.

## Structural check

```text
python -B -m unittest discover -s tests -v
```

The zero-dependency test checks that the template includes the required stack,
project layout, naming conventions, migration rules, actionable commands,
anti-pattern reasons, and an honest greenfield protocol.

## Behavioral gate still required

The issue asks for a greenfield project to be created, the template copied
into it, and a live Claude Code session to demonstrate that settled defaults do
not require clarification. That is an external, authenticated tool interaction
and is deliberately not substituted with a fabricated transcript or a static
test. When an authorized live run is available, record the exact project setup,
prompt, Claude Code version, and observed result before claiming this criterion
has passed.
