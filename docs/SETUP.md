# Setup - zero additional monthly cost

## A. GitHub Montreal read-only monitoring

Use [ACTIVATE-MONTREAL.md](ACTIVATE-MONTREAL.md) for the current exact activation
steps, configuration, permissions, persistence, cost boundaries and stop controls.
The previous workflow's raw-body omission and force-pushed data snapshots have
been replaced by compressed immutable raw evidence and append-only data commits.
No workflow has been activated from this workspace. Keep the repository public,
use standard `ubuntu-24.04` and leave `ENABLE_PILOT` unset until activation is intended.

## B. Cloudflare - later Stage D, not needed to run this collector

Do not deploy or connect this endpoint to sorttreks.lv until the collector is validated and the owner approves the integration. The following are preparation instructions only; nothing below has been executed.

Stay on **Workers Free**. Create D1 database `sorttreks-isu-pilot`. Use the Workers-provided `workers.dev` hostname; do not buy a domain or enable paid plans, R2, Queues, Workers Paid, paid build features or other add-ons.

The draft configuration is `worker/wrangler.example.jsonc`; copy it to `worker/wrangler.jsonc` when approved and use the exact database UUID Cloudflare returns. Do not invent a UUID.

| Setting | Value |
| --- | --- |
| Worker name | `sorttreks-isu-data-pilot` |
| D1 database | `sorttreks-isu-pilot` |
| D1 binding | `DB` |
| `SERVE_APPROVED` | `false` |
| Migration | `migrations/0001.sql` |
| Pilot read route | `/v1/pilot/latest` |
| Future calendar route | `/v1/calendar` (503 until explicitly enabled) |
| Allowed browser origins | `https://sorttreks.lv`, `https://www.sorttreks.lv` |
| Public write routes | None |

No credentials are required for offline unit tests. A later operator can authenticate Wrangler locally or use a narrowly scoped account token. If a future CI deployment/ingest is authorized, add secrets `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and database id variable `CLOUDFLARE_D1_DATABASE_ID` to **this collector repository only**. Token permissions: Account > Workers Scripts > Edit and Account > D1 > Edit, restricted to the selected Cloudflare account. Never put them in website/browser code. An ingestion-only token should have only D1 Edit.

After approval, normal CLI configuration would use `npx wrangler d1 create sorttreks-isu-pilot`, then apply `migrations/0001.sql` and deploy the configured worker. The scaffold has no ingest endpoint; approved snapshot creation/transactional publishing and reviewer authorization still need implementing before site integration. Do not treat a deployed empty scaffold as a working data feed.

Current documented free allowances (checked 29 October 2026): Workers 100,000 requests/day; D1 5 million rows read/day, 100,000 rows written/day, 5 GB total storage. Free-plan quota exhaustion fails requests instead of buying paid capacity. Preserve the bundled site data when the endpoint returns 503, is stale, has a schema error, or times out. Stay on Free; the code cannot prevent an account owner from later upgrading.

Sources:
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## C. Before future site integration

Validate Montreal against actual public programme/start lists, capture Bormio repeated-distance formats, complete classification-row extraction and pagination checks, and approve a clear revision/source-priority policy. Then implement authenticated candidate ingestion, manual review, atomic approved revisions and bounded retention (for example 20 candidates), without overwriting manual locks.

Only after that, make a separately approved one-time Sites change to fetch the approved calendar feed with a timeout/schema/age guard and preserve its current local fallback. Keep homepage countdown/livestream estimates, breaks and completion logic untouched. A remote JSON refresh does not update already published fallback HTML for Google/no-JavaScript visitors.

Schedule-revision implementation and archive limitations are detailed in [REVISION-TRACKING.md](REVISION-TRACKING.md).
