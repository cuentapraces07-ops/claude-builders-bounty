# Bounty #2 local verification

This evidence records what can be verified locally for the Next.js + SQLite
`CLAUDE.md` template. It is not a claim that Claude Code, a deployment, or a
payment was observed.

## Structural check

```text
python -B -m unittest discover -s tests -v
```

The zero-dependency tests check that the template includes the required stack,
project layout, naming conventions, migration rules, actionable commands,
anti-pattern reasons, and an honest greenfield protocol. One test also copies
the exact `CLAUDE.md` into a newly created, empty temporary project directory
and checks the copied file retains the required defaults. This verifies
copyability and the static contract; it does not exercise Claude Code.

## Behavioral gate still required

The issue also asks for a live Claude Code session to demonstrate that settled
defaults do not require clarification. No Claude Code executable or
authenticated session is available in this environment, so this criterion is
still unverified. The static copy test is not a substitute. Record the exact
project setup, prompt, Claude Code version, and observed result before claiming
that criterion has passed.
