# Optional independent collector clock - not deployed or enabled

This is a small Cloudflare Workers Free Cron Trigger that dispatches the existing GitHub collector on main. It never retrieves ISU responses itself, edits pilot-data, serves schedules, modifies sorttreks.lv or touches the integration delivery Worker. The original GitHub job performs all collection, verification, capacity checks and persistence.

Default config: ENABLE_CLOCK=false, no cron triggers, no public workers.dev route, no bindings or paid resources. It imports config/monitoring.json, including the exact 2 November2026 18:00Z end. Both scheduled timestamp and current time must be within the campaign; delayed executions after the deadline cannot dispatch. It checks the last successful archived check time, rejects unverified/missing state and suppresses a new dispatch when the existing collector is not due. The existing GitHub concurrency lock and persisted plan protect against overlapping native/external triggers.

This clock bypasses GitHub's cron-event generator, not GitHub runner availability or Actions permissions. Neither platform offers an absolute timing guarantee on its free tier. Expected volume: two small requests per half-hour invocation; no D1, KV, R2, paid build or logging service.

## Setup actions required before activation

1. Authenticate an intended Cloudflare account and verify Workers Free. This implementation cannot infer the account billing plan from Wrangler config.
2. The owner creates a fine-grained GitHub token for **only lvbroskii/sorttreks-isu-data**, with **Actions: Read and write** and the automatically required **Metadata: Read**. No Contents write, Administration, secrets, Sites or Cloudflare permission is needed by this clock. Set expiry to3November2026 to cover the full campaign, then revoke after use. Do not paste it into chat or put it in a repository file.
3. Store it with the official Cloudflare CLI: `wrangler secret put GITHUB_DISPATCH_TOKEN --config scheduler/wrangler.jsonc`. The command prompts locally for the value. This is a new credential/security grant that requires the owner's involvement; it is not performed by the source commit.
4. Only after owner/account readiness, set ENABLE_CLOCK=true and add these UTC crons to scheduler/wrangler.jsonc:
   - `17,47 * 29-31 10 *`
   - `17,47 * 1-2 11 *`
5. Deploy this separate clock with `wrangler deploy --config scheduler/wrangler.jsonc` on Workers Free. No change to the calendar endpoint or Sites reader is required. Keep repository ENABLE_PILOT=true; that independent GitHub gate still controls the job.

## Proof and audit

Use Cloudflare's Cron Trigger execution record or a secure live tail to observe an actual scheduled handler invocation. Its sanitized result includes scheduledAt, checkedAt, source and dispatch status; it never logs headers, tokens or response bodies. Correlate an HTTP204 dispatch-accepted result with the newly created pilot.yml workflow_dispatch run and its new pilot-data check/raw-response retrieval records. This is a genuine externally scheduled execution, but its GitHub event remains workflow_dispatch. A label or a manually invoked scheduled handler alone is not proof of automatic execution.

Tests use a synthetic in-memory HTTP transport and a literal non-secret placeholder. They do not activate a scheduler or constitute live evidence. Run `node --test tests/clock.test.mjs`.
