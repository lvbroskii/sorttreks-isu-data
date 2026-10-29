# Calendar integration v1 - prepared, not activated

The Montreal pilot and `pilot-data` remain independent. No change to `pilot.yml`, its permissions, cadence, campaign end or archive retention. No website publication, Cloudflare resource or approved-data branch has been created by this implementation.

## Delivery path

Existing collector -> explicit offline review/export -> cumulative `approved-data/calendar.v1.json` -> read-only Cloudflare Worker -> existing Sites calendar/browser.

D1 is unnecessary for a small immutable feed. Git holds approved history; the Worker uses a fixed public raw GitHub URL and the free edge cache. It needs no secrets, database, KV, R2, cron or write API. The existing pilot/D1 scaffold stays separate in `worker/index.mjs`; the new production-capable-but-disabled implementation is `worker/delivery.mjs`.

Cloudflare Workers Free includes 100,000 requests/day and 10ms CPU/request. Above the free quota, requests fail and the browser retains its fallback. Do not switch the account to Workers Paid, add paid observability or use larger GitHub runners. Standard `ubuntu-24.04` runners in the public repository are free. No Actions artifacts/caches are used here. Shared-account request usage also counts. This is a zero-additional-cost design with limited capacity, not an unlimited availability promise.

Sources checked 29 October 2026:
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://docs.github.com/en/billing/concepts/product-billing/github-actions

## Contract

`integration/feed.mjs` is the executable strict v1 contract shared by Worker and browser. `fixtures/integration/*.json` are explicitly synthetic-not-official. `website-baseline.json` is the existing verified website dataset, not a captured ISU response or newly verified official source.

Envelope: `schemaVersion: sorttreks.calendar.v1`, `kind: approved`, monotonic positive `revision`, aware ISO `issuedAt`, `validUntil` (maximum six hours), SHA256 of the exact bundled races.json in `baselineDigest`, cumulative `events`.

Each event pins ID, IANA zone and venue dates. Approval binds a reviewer, reviewed timestamp, exact input report bytes (`reportSha256`), selected authority version and basis. Sources preserve URL, public sanitized body hash, retrieval timestamp and revision evidence. Retrieval is never used to select authority.

`rounds`: gender, distance, occurrence, round, aware instant, source URL, `timeBasis: round-start`. Full returned individual programme remains distinct from confirmed Latvian participation. The UI groups venue dates and formats instants in Europe/Riga. Repeated Junior World Cup distances use occurrence; no inference from season discipline selection.

`firstStarts`/`laterStarts`: exact round key and instant, draw and programme sources, `evidenceKind: start-list`; first starts additionally require complete opening-day coverage. Heat timestamps are deliberately not exposed as round timestamps. The existing publication assessor and matching guards supply confirmations, not rankings or generic entries.

`sessionMappings` require a separate explicitly verified session row and review mapping to a site session ID with LV/EN label. The collector currently does not extract real daily sessions. First/last rounds cannot create sessions, broadcast ends, break states or event completion. Owner-estimated ends remain estimates. Invalid or overlapping revised windows reject the entire update. Existing verified ends cannot be erased by start-only evidence.

Only official HTTPS links are accepted. No HTML, arbitrary event fields, executable code, rankings, standings or stream-window patches are accepted. Existing World Tour standings stay unchanged.

## Review/export without publication

1. Save an actual collector report locally. `monitor` produces an envelope; the exporter also accepts a single event report. Preserve its bytes.
2. Compute `sha256sum report.json`. Review selected `scheduleAuthority`, source versions, completeness and manual comparisons.
3. Write approval.json:

```json
{
  "reviewer": "YOUR_NAME",
  "reviewedAt": "2026-10-30T12:00:00+00:00",
  "reportSha256": "EXACT_64_HEX_SHA256_OF_REPORT_FILE",
  "sessionMappings": []
}
```

4. Run from repository root:

```bash
PYTHONPATH=src python3 -m isu_pilot.feed --report report.json --approval approval.json --baseline fixtures/integration/website-baseline.json --out out/calendar.v1.json
```

For subsequent revisions add `--previous path/to/previous-calendar.v1.json`. Output is validated with the exact JS contract before atomic write. Any exception leaves the old output untouched. The CLI performs no network requests, Git pushes or deployments. Synthetic reports cannot receive production approval. A reviewer/hash is an audit boundary, not a digital signature; approved branch write access is the trust boundary.

Current restrictions: unresolved authority, stale fallback, incomplete programme, manual reference conflicts, cancellations and programme reductions are rejected. Cancellation/removal need a later explicit reviewed contract. Draw source metadata is taken from the existing liveApi heat observations; missing provenance rejects the export. Real session extraction still needs validation. Schedule-only approval is possible without athlete draws, but cannot invent them.

This implementation intentionally does not auto-approve collector candidates. A policy that automatically approves first publications/revisions must wait for Montreal populated-programme and pre-race draw validation. Production data-branch writing is not wired into either workflow.

## Browser refresh/fallback

Client disabled by default (`enabled:false`, empty URL). Once enabled it loads the bundled dataset immediately and polls one feed every five minutes while visible, plus pageshow, online and visibility changes. Worker cache is 60 seconds with ETag and correct CORS exposure. Browser uses conditional requests and an abortable five-second request. Both layers cap decoded JSON at 256KiB.

Valid, unexpired snapshots may restore from localStorage after reload. Each reload rechecks the schema, baseline digest and expiry. Revision rollback/reused-revision changes are rejected. Offline, conflict, empty or invalid responses keep the last accepted snapshot until expiry; after expiry the untouched bundled baseline returns. Feed freshness/status is shown in both languages. No unverified data deletion; snapshots are cumulative and merge existing rows. No stale feed is labelled current. Refreshes preserve filter/hash navigation and expanded event programmes.

The original homepage state machine remains byte-identical. It reads the same updated data object, preserving countdown, exclusive livestream windows, repechage breaks, owner-estimated endings and completion retention. Round-only changes do not alter these states; confirmed draws may update the national-team heading and start-time link. Separate explicit session evidence may update countdowns. Programme notice subscribes to the same update event.

## Preview and validation

Local preview: `/preview/isu-integration.html` in the separate unpublished Site worktree. Buttons demonstrate baseline -> programme with no names -> confirmed draws -> revised round -> explicit session -> conflict -> offline -> expiry; LV/EN use actual site renderers. All new Montreal values are synthetic and prominently labelled. Time is frozen at 29 October 15:00Z for reproducibility.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/*.test.mjs
PYTHONPATH=src python3 tests/offline_workflow.py out/workflow-rehearsal
python3 scripts/check-site-patch.py
```

Separate Site checkout: `node --test tests/*.test.mjs`. Historical byte-preservation tests normalize only exact SHA-pinned integration edits to their prior source; all existing behavior tests run the actual implementation. New feed/UI tests bypass normalization. An unrelated/future edit does not match the hash and fails historical assertions. The original verified races.json, homepage HTML and race-panel.mjs stay byte-identical.

## Future activation steps - do not execute yet

1. Validate real populated Montreal programme and real pre-race draws, including evidence authority, completeness and correct seeded starting rounds. Review failures/conflicts. Keep pilot running unchanged.
2. In Cloudflare select the existing account's **Workers Free** plan. No D1 setup or card/plan upgrade is required for this implementation. Create `sorttreks-approved-feed` only when approved. From repository worker directory with official Wrangler installed, `wrangler login`, then `wrangler deploy --config wrangler.delivery.jsonc`. It initially serves `/health` only; `/v1/calendar` remains 503 because `SERVE_APPROVED=false`. Do not place credentials in repository or browser code.
3. Create/restrict an `approved-data` branch, with `calendar.v1.json` produced by the exporter after review. Make changes append-only commits using normal fast-forward updates, never force. Add branch protections/review rules where available. Do not copy `pilot-data/latest.json` directly. No historical capture files belong on this branch. Revalidate/approve within six hours while an event is active; do not extend validUntil without source checks.
4. Once readiness is approved, change `vars.SERVE_APPROVED` to `true` and deploy the feed Worker. Test its exact returned workers.dev URL plus `/v1/calendar`, ETag/304, CORS from both production origins and failure behavior. No need to move sorttreks.lv DNS/hosting.
5. Apply `site-integration/changes.patch` to Site source commit `c5d4d83a8a02080b255b1d228d487f22d4e6725e` or carefully rebase onto newer source. Set `isu-feed-config.mjs` to `enabled:true`, `url: https://<actual-worker-host>/v1/calendar`, `baselineDigest: <sha256 of exact current races.json>`. Update/review feed digest if website baseline changed. Ensure Sites response CSP permits fetch to this exact endpoint if a restrictive connect-src policy exists.
6. Run Site/feed tests, preview both languages and secure approval for one initial Sites publication. That publication installs the reader only; later approved GitHub JSON updates require no Sites edit or republish.
7. Add a separately reviewed approval/promotion workflow after successful real-source validation. Keep monitoring and feed promotion independent, minimal permissions and production approval gates. No such workflow is activated by this branch.

Rollback: Worker `SERVE_APPROVED=false` returns503; visitors keep unexpired accepted data then revert to bundle. An emergency revocation is not instantaneous on already-open/offline tabs (maximum six-hour accepted lifetime). Disabling the browser reader requires a Sites publication. Do not delete verified competition data or the monitoring archive to roll back delivery.
