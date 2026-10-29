# Activate Montreal read-only monitoring - v0.4.2

Prepared locally; **monitoring has not been activated**. The website and Cloudflare
are not involved. Use a separate **public** GitHub repository with standard Ubuntu
runners. No ISU API key, Cloudflare token, Sites credential or paid feature is needed.

HTML credential values are removed before public persistence; original-response hashes are retained. Use v0.4.2 or later for upload. See [PUBLIC-CAPTURE-SECURITY.md](PUBLIC-CAPTURE-SECURITY.md).

## Exact activation steps

1. Wait for **Actions > Offline pilot validation** to pass. Its `pilot-validation/result.json` must identify the current source commit. This workflow does not collect ISU data or activate monitoring.
2. Unpack the delivered ZIP. Open the inner `isu-data-pilot` directory. Confirm
   `.github/workflows/pilot.yml` is present; it must be uploaded too.
2. On GitHub create an empty repository named **`sorttreks-isu-data`**, visibility
   **Public**, default branch **`main`**. Do not enable Git LFS, Pages, paid runners,
   Codespaces, artifact uploads or cache services for this pilot. If that repository
   already exists, use it rather than creating a duplicate; preserve its existing
   `pilot-data` branch and apply these source files to `main`.
3. For a new repository, run from the unpacked directory, replacing `YOUR_USERNAME`:

   ```bash
   git init -b main
   git add .
   git commit -m "Read-only Montreal ISU monitoring"
   git remote add origin https://github.com/YOUR_USERNAME/sorttreks-isu-data.git
   git push -u origin main
   ```

   For an existing checkout, commit the updated source on `main` and push normally.
   **Do not overwrite or force-push the existing data branch.**
4. Repository **Settings > Actions > General**: allow GitHub Actions and the pinned
   official `actions/checkout` action. Under **Workflow permissions**, allow
   **Read and write permissions**. Leave PR creation/approval disabled. The workflow
   requests only `contents: write` in its collector job, to append `pilot-data`.
   GitHub's token cannot restrict that permission to one branch; the script itself
   pushes only `HEAD:refs/heads/pilot-data` and never force-pushes or pushes `main`.
5. Repository **Settings > Secrets and variables > Actions > Variables**: add:

   | Name | Exact value |
   | --- | --- |
   | `ENABLE_PILOT` | `true` |

   **This is the activation switch.** Once set, scheduled runs can begin. There are
   **no secrets to add**. Do not add Cloudflare or Sites credentials.
6. Open **Actions > Read-only ISU pilot > Run workflow**, choose **main**, then
   **Run workflow**. Check that it finishes and creates/appends `pilot-data`.
   The workflow refuses private repositories, other source branches or an unset
   enable variable. Do not remove these guards to work around a skipped run.
7. On `pilot-data`, inspect `latest.json`, `index.json` and `state/monitor-state.json`.
   The job summary displays programme status, first publication, authority and
   round-time changes. Source bodies are in `raw/<first-two-hash-characters>/...body.gz`;
   each check report is in `checks/YYYY-MM-DD/`. No email/issue notification is sent.

If Actions returns HTTP 403 while saving, verify the workflow permission and the
organization's policy for this repository. A policy or branch rule that blocks
`pilot-data` must be resolved by the repository owner; do not add a broad personal
access token or bypass protections. A failed remote fetch must fail the run instead
of resetting the evidence history.

To stop immediately, set **`ENABLE_PILOT=false`** or use **Actions > Read-only ISU
pilot > Disable workflow**. Collection also stops at the configured campaign end.

## Timing and campaign scope

`config/monitoring.json` contains the complete configuration:

| Setting | Value |
| --- | --- |
| Event | `2026-27-wt2` only |
| Campaign start | `2026-10-29T00:00:00Z` / 29 October 02:00 Latvia |
| Campaign end, exclusive | `2026-11-02T18:00:00Z` / 2 November 20:00 Latvia |
| Interval | Approximately 30 minutes, final pre-competition period and all active days |
| Cron wakeups | UTC minute 17 and 47, 29-31 October and 1-2 November |
| Source branch | `main` |
| Evidence branch | `pilot-data` |
| Runner | Standard `ubuntu-24.04` |
| Job / collection timeouts | 15 / 8 minutes |
| Network budget | 300 seconds, 30 seconds per request, at most 3 parallel queries |
| Download budget | 32 MiB per check, 12 MiB per response |
| Archive guard | 256 MiB with 48 MiB reserve; pause before further collection above 208 MiB |

The year and exact deadline are checked in Python because cron cannot express a
year. Future-year cron wakeups do not collect. Disable the workflow after this
campaign; do not leave it as a permanent multi-season archival service. General
collector cadence also now uses 30 minutes in the final 48 hours; the dedicated
Montreal campaign uses its fixed 30-minute interval throughout the stated window.

GitHub scheduled workflows run from the default branch and may be delayed or
dropped under load. The non-zero cron minutes reduce peak-hour contention, but
30 minutes is a target, not a guaranteed interval. A one-minute due tolerance
prevents small start-time differences from skipping an entire polling slot.

## What is archived and detected

The monitor restores source bodies, HTTP history, selected schedules, publication
state and first-publication evidence before fetching. It archives successful and
bounded HTTP error bodies as immutable, content-addressed deterministic gzip files.
Identical bodies are stored once. The per-request raw sink writes bodies as they
arrive; a final checkpoint saves state even after normal collector errors or step
timeouts. Abrupt runner loss or a failed Git push can still lose an unfinished
check; inspect failed jobs rather than treating them as successful observations.

Every completed check has an immutable compressed report and an index entry.
`latest.json` is a convenience view; previous reports and raw versions remain.
`state/source-history.json` retains 256 retrieval attempts per URL, and normalized
schedule history retains 64 versions per source. Immutable check reports/raw bodies
retain the campaign evidence even when those rolling views reach their limits.
The storage guard stops new collection instead of deleting the first publication,
verified snapshots or revision evidence. Review/export the archive if it pauses;
do not enable paid storage. Metadata/legacy migration may consume part of the
reserved headroom; the download budget bounds each check's new response volume.

No historical fixture is needed at runtime. A live empty response establishes
`emptyEvidence`; a later genuine programme then pins the empty-to-populated
transition. If the first live response is already populated, it is recorded as
`initial-populated-without-empty-baseline`; no prior empty state is invented.
Observed rows receive Riga labels, and subsequent revisions are recorded without
allowing retrieval timestamps to resolve source-authority conflicts. The first
structurally complete programme is tracked separately from the first round data.

The observed programme candidate and the selected schedule are distinct. A revised
API snapshot can be archived/reported while the authority decision retains the
previous selected schedule for review. Nothing becomes an approved website feed.

## Independent result/round IDs and draws

When the programme is empty/unsupported, the collector checks the public result
inventory using the official event slug and, if observed in the verified event
page, its matching Results-tab slug. It never generates numeric IDs.

For a supported inventory bound to the exact CMS event ID, it queries only the
returned result IDs, verifies returned round/event/result IDs, then archives heat
responses for those verified IDs. These independent probes remain **unvalidated
records** until the programme/distance/status mapping is established. They cannot
confirm a first starting round. Wrong-event identifiers, duplicates, excessive
arrays and unknown schemas stay in review. When the programme is populated, the
existing mapped round/heat adapter handles LAT matching and first-round coverage.

The one-off live monitoring smoke check still found an empty programme and HTTP
404 for both inventory routes. No event-specific heat identifiers were guessed.
A populated Montreal inventory/draw remains an outstanding real-source validation
case. New positive-ID probe tests are explicitly synthetic.

## Existing evidence branch migration

The earlier workflow saved parsed snapshots/metadata but omitted raw bodies.
Those missing historical raw bytes cannot be reconstructed. Existing flat JSON
state is preserved/migrated, with missing body hashes listed in
`legacy-archive-gaps.json`. Such sources must be refetched; they are not re-verified
from stale metadata. New raw responses are retained from activation onward. A
missing/corrupt body in the new archive fails closed instead of silently resetting.

If there is no prior `pilot-data` branch, the loader creates it. A remote/network
failure is distinguished from a genuinely absent branch. Data commits append to
existing history; no orphan-reset/force-push is used.

## €0 cost boundary and account setup

GitHub's documentation states that standard hosted runners in **public**
repositories remain free. Larger runners are chargeable, including in public
repositories. This workflow uses only a standard Ubuntu runner and normal Git
repository storage; **no Actions artifact, cache, Packages or LFS storage** is used.
It does not consume private-repository included minutes. Do not switch visibility
or runner type, or add storage actions. No plan upgrade, payment method, Cloudflare
account or token is required. The workflow does not change billing settings or buy extra quota.

This finite archive is an engineering tradeoff for a small validation campaign,
not an unlimited historical data warehouse. GitHub recommends keeping repositories
small and enforces 100 MB per Git object; each raw response is capped at 12 MiB.
The archive guard and campaign deadline prevent intentional unbounded collection.
If the push fails, stop and inspect it; do not enable Git LFS or paid services.

Official documentation checked 29 October 2026:
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits

## Local verification / replay

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/worker.test.mjs
# One check only. This does not activate GitHub scheduling:
PYTHONPATH=src python3 -m isu_pilot monitor --state .state --archive .archive --out out/monitor
```

Git integration tests use temporary **local bare repositories**, not GitHub, and
verify append-only history, unchanged `main` and fail-closed remote errors. Tests
also cover restart/304 recovery, archive integrity, first-publication pinning,
revisions, empty/failing sources, download/storage limits, campaign timing,
collector-error archiving and verified-ID-only probe behavior. Synthetic transition
fixtures remain clearly separate from the actual empty Montreal captures.
