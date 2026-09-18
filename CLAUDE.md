# CLAUDE.md — Next.js 15 + SQLite SaaS

This file is the operating contract for an opinionated, production-ready SaaS built with Next.js 15 App Router, TypeScript, React 19, and SQLite. Follow it without asking for choices that are already settled here. If a request conflicts with a security or data-integrity rule, stop and explain the conflict before changing code.

## Stack and versions

- Node.js 20 LTS or newer LTS; use the version declared in `.nvmrc` or `engines`.
- Next.js 15 App Router with React 19 and TypeScript in strict mode.
- `pnpm` is the package manager. Never mix `npm`, `yarn`, and `pnpm` lockfiles.
- SQLite for local and single-instance deployments, using `better-sqlite3` behind a small repository layer. Turso/libSQL is the production-compatible remote option; application code must use the same repository interface for both.
- Zod validates every untrusted boundary: form data, route params, search params, webhook bodies, and environment variables.
- Vitest is the unit-test runner; Playwright covers critical browser flows.

When a repository already pins a compatible patch version, keep that pin. Do not upgrade the framework, database driver, or auth library as part of an unrelated feature.

## Non-negotiable rules

1. **Server by default.** Files are React Server Components unless they require browser state, event handlers, or a browser-only API. Add `"use client"` only at the smallest interactive leaf.
2. **Validate at the boundary.** Parse inputs before authorization, queries, or mutations. Return a typed validation error; never pass raw request data into SQL, redirects, shell commands, or HTML.
3. **Authorize on the server.** UI hiding is not authorization. Every Server Action, Route Handler, and data repository method checks the current user and tenant before reading or mutating data.
4. **Parameterized SQL only.** Never interpolate values into SQL. Keep migrations and queries in the data layer; route and component code calls named repository functions.
5. **No secret leakage.** Only variables explicitly prefixed `NEXT_PUBLIC_` may reach client bundles. Do not log tokens, cookies, passwords, full webhook bodies, or personal data.
6. **Mutations are deliberate.** Destructive operations require an explicit confirmation in the UI, a server-side authorization check, and an audit record. Prefer soft delete and reversible state transitions.
7. **Errors are typed and useful.** Show users a safe message with a request/correlation id; log the detailed cause on the server with secrets and personal data redacted.
8. **Tests must be hermetic.** Unit tests use an isolated temporary SQLite database and mocked network boundaries. No test depends on a developer's database, clock, filesystem layout, or network service.

## Project structure

```text
app/
  (auth)/                 # sign-in, sign-up, password reset
  (dashboard)/            # authenticated product UI
  api/                    # thin Route Handlers; parse, authorize, delegate
  actions/                # Server Actions grouped by capability
  layout.tsx              # root providers, metadata, global error boundary
  loading.tsx             # route-level pending UI
  error.tsx               # route-level recoverable error UI
components/
  ui/                     # presentational, reusable primitives
  features/<feature>/     # feature-specific components and schemas
lib/
  auth/                   # session and authorization helpers
  db/                     # client, migrations, repository functions
  env.ts                  # validated environment variables
  http/                   # safe fetch wrapper and correlation ids
  validation/             # shared Zod schemas
tests/
  unit/                   # repository, schema, and pure-function tests
  integration/            # Route Handler and Server Action tests
  e2e/                    # Playwright critical journeys
public/                   # immutable static assets only
scripts/                  # safe, repeatable maintenance commands
```

Keep feature code close to its route, but keep database access, authorization, and validation in `lib/` so they can be tested without rendering React.

## Package scripts

The root `package.json` must expose these commands (an existing project may add flags, but must keep the intent):

```json
{
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "next lint",
  "typecheck": "tsc --noEmit",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:e2e": "playwright test",
  "db:migrate": "tsx scripts/db-migrate.ts",
  "db:status": "tsx scripts/db-status.ts"
}
```

Before opening a PR, run `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, and the relevant Playwright project. A failed check is a stop signal, not something to hide with a skipped test.

## Environment and configuration

Create `.env.example` with names and safe example values; keep real `.env*` files out of Git. Parse configuration once in `lib/env.ts` with Zod and import that module instead of reading `process.env` throughout the app.

Required production categories:

- `DATABASE_URL` (SQLite path or Turso URL) and, for Turso, `DATABASE_AUTH_TOKEN`.
- `AUTH_SECRET` with a documented minimum length; never use a development fallback in production.
- `APP_URL` validated as an absolute HTTPS URL in production.
- Provider credentials and webhook secrets, if used.

Fail fast at startup for missing production variables. Development may provide explicit local defaults only when the value cannot authenticate to a real service.

## Database and migration rules

- Every schema change is a numbered, committed migration. Migrations are forward-only, idempotent, run in a transaction where SQLite permits it, and record their version in a migrations table.
- Never edit an applied migration. Add a new migration for corrections.
- Add indexes only for demonstrated query paths; document the query they support.
- New columns are nullable or have a safe default before application code relies on them. Backfill in a separate bounded step, then tighten constraints in a later migration.
- Preserve user data. Do not use `DROP TABLE`, `DELETE` without a narrow predicate, or a destructive reset in a production path.
- Enable foreign keys on every connection and use UTC ISO-8601 timestamps (or integer epoch milliseconds) consistently.
- Transactions must include all writes that must succeed or fail together. Do not perform network calls while holding a database transaction.
- Repositories return domain-shaped values, not raw driver rows. Map nullable database fields explicitly.

For SQLite concurrency, keep transactions short, set a busy timeout, and prefer WAL mode. For Turso, avoid relying on local process state or SQLite-specific filesystem APIs.

## Components, routes, and Server Actions

- Define the data contract first: Zod input schema, domain result, and safe error codes.
- Use `loading.tsx`, `error.tsx`, and `not-found.tsx` at route boundaries where a slow or missing resource is expected.
- Mutating forms use a Server Action or Route Handler that validates the complete payload again. Disable the submit control while pending and make success/failure visible without relying on a toast alone.
- Use stable IDs and accessible labels. Every interactive control has a keyboard path, visible focus state, and a meaningful name.
- Do not fetch the same server data again from a Client Component when the Server Component already owns it; pass the smallest serializable props.
- Cache only public or explicitly scoped data. Mark user-specific data dynamic and revalidate after mutations.
- Use `redirect()` only after successful authorization and mutation; never place untrusted input directly in a redirect target.

## Authentication, authorization, and webhooks

- Store only a session identifier in an HttpOnly, Secure, SameSite cookie. Rotate sessions after sign-in and privilege changes.
- Check tenant/resource ownership in the repository or service layer, not only in page code.
- Rate-limit login, password reset, search, and webhook endpoints. Verify webhook signatures over the raw body before parsing JSON, reject stale timestamps, and make event handling idempotent.
- Return the same safe response shape for authentication failures to avoid account enumeration.

## SQL, API, and external service conventions

- Repository functions accept typed arguments and return typed results. Use explicit column lists; never rely on `SELECT *` across migrations.
- Route handlers set correct status codes (`400` validation, `401` unauthenticated, `403` unauthorized, `404` absent, `409` conflict, `429` rate limit, `5xx` unexpected).
- Outbound `fetch` calls have an allowlisted origin, timeout, bounded retries only for idempotent operations, and structured error handling. Never retry a payment or other non-idempotent mutation without an idempotency key.
- Keep third-party response bodies out of logs unless explicitly redacted and bounded.

## Testing and review checklist

For every feature or bug fix, add the smallest tests that prove the behavior and its failure modes:

- schema tests for missing, wrong-type, boundary, and extra fields;
- repository tests for authorization scope, empty results, conflicts, and transaction rollback;
- route/action tests for status codes and safe error envelopes;
- regression tests for the reported bug;
- an accessibility smoke check for new interactive UI;
- an end-to-end happy path and one recovery path for user-visible flows.

Use deterministic clocks and IDs in tests. Assert observable behavior, not private implementation details. Do not weaken a test because a production bug makes it inconvenient.

The minimum pre-PR gate is:

```bash
pnpm lint
pnpm typecheck
pnpm test -- --coverage
pnpm build
pnpm test:e2e --project=chromium
```

Record the commands and their results in the PR description. If a command cannot run in a constrained environment, state the exact limitation and run the closest hermetic substitute.

## What we do not do

- Do not add generic rules such as “write clean code” without a concrete, checkable behavior.
- Do not commit `.env`, database files, credentials, generated build output, or personal data.
- Do not introduce a global client state library when URL state, server data, or a local component state is sufficient.
- Do not silently coerce invalid input, guess an account/tenant, or select the first result when a request is ambiguous.
- Do not use `any` to bypass a type error; model the boundary or narrow the unknown value.
- Do not make unrelated formatting, dependency, or architecture changes in a focused PR.
- Do not claim a test, benchmark, deployment, or payment that was not actually run, observed, or received.

## Definition of done

A change is ready only when the acceptance criteria are implemented, the relevant tests and build pass, migrations are reviewed for rollback/data safety, user-facing errors are understandable, secrets are absent from the diff, and the PR records exactly what was run. Keep the change small enough that a maintainer can verify it from the diff and the commands above.
