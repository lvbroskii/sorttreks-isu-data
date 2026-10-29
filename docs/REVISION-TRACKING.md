# Schedule revision tracking - implementation update, 29 October 2026

The pilot now stores normalized source versions and resolves schedule revisions before matching athlete times. It remains read-only: no Sites files, approved feed, remote database or paid services are changed.

## Authority rules implemented

| Evidence | Decision |
| --- | --- |
| Explicit schedule-specific revised/updated date, later than the other schedule's revision or older C08 print stamp, with complete overlapping event coverage | Select the revised schedule |
| Higher numeric revision within the same event/document series (for example C08 2.0 vs C08 1.0) | Select the higher edition |
| Conflicting sources without a reliably orderable revision | Review; preserve previous selected data |
| Later retrieval, HTTP Last-Modified, protocol upload date or generic CMS page edit | Never used as schedule authority |
| Same-day date-only stamps | Review because order cannot be established |
| Missing known rounds, mixed C08 page editions, invalid event identity or partial retrieval | Cannot replace the last complete schedule |
| Identical round times/status in different wrappers | Treated as agreement; source formatting does not create a sporting conflict |

Scope matters: revision numbers compare only within the same schedule series. A print stamp without a stated clock zone is bounded conservatively across UTC offsets of +/-14 hours; a venue offset is not invented for it. A later PDF print date alone cannot override an explicitly revised online programme. A revised source must preserve known keyed rounds; cancellations stay explicit, not inferred from missing rows. Changes to dates, genders, distances, rounds or occurrence identifiers that would remove known keys go to review.

A full resolved schedule is a **local pilot selection**, not approval to publish. Athlete starting-round evidence remains separate; updating a heat round from 13:39 to 13:53 does not change the athlete's starting round or upgrade retrospective result evidence into a pre-race start list.

## Vancouver archived evidence

`examples/vancouver-revision-validation.json` is the actual archive assessment. It records:

- Official C08 edition 1.0, printed 21 October 2026 at 21:32 (print clock timezone unspecified in the PDF), extracted from its own C08 pages. The result book's 26 October publication date is not the schedule revision date.
- A saved online programme capture containing `loading_schedule`; it has no extracted revised timetable rows or schedule-scoped revision stamp.
- The owner's explanation that the online programme was revised later and the website was manually updated.
- Six athlete/distance time differences, affecting four unique race rounds. The manually updated website values are retained as the reference; they are not judged incorrect.

**The archive does not independently establish the exact revised programme version or its supersession of C08.** The result is `needs-review`, `supersessionEstablished: false`, `websiteTimesIncorrect: null`. There is no invented historical revision date.

`examples/synthetic-revision-demo.json` and `fixtures/synthetic/revised-programme.html` are explicitly synthetic. They exercise both directions of supersession using invented revision stamps and must never be cited as historical Vancouver proof. Generate them with:

```bash
PYTHONPATH=src python3 scripts/revision_examples.py
```

## What is monitored and retained

- Official online programme URL discovered from that event's HTML, plus labelled timetable/protocol PDF URLs.
- HTTP source attempts in `.state/source-history.json`: retrieval timestamp, status/error, content hash, ETag and Last-Modified. The latest 256 attempts per URL are retained.
- Parsed schedule versions in `.state/schedules.json`: event identity, raw hash, normalized semantic hash, exact rows, scoped revision evidence and per-check changes. Latest 64 versions and 256 checks per source retained, with `prunedVersions` accounting when bounded retention removes older versions.
- Selected local snapshots and retained athlete observations in the same state file, restored across GitHub runs.
- Raw source bytes locally under `.state/<sha>.body`. Raw bodies are not committed to GitHub; normalized versions, hashes and revision evidence are persisted instead. This preserves timetable versions while avoiding large, repeatedly stored PDFs. It does not provide a permanent byte-for-byte archive of every remote document.
- Every report remains `approvedForWebsite: false`.

Changes show `previousTime`, `updatedTime`, date, gender, distance, round, occurrence, previous/current source and source version IDs. `sourceChanges` describes changes within a source; `selectedChanges` describes a resolved local schedule replacement. On first observation, rows are labelled additions, not falsely reported as changed race times.

On failure/conflict, prior athlete rows and selected schedule remain available and marked stale/review as appropriate. New matching programme times can retime retained confirmed athlete observations; missing/cancelled/ambiguous matches remain in review rather than deleting the observations.

## Original v0.2 online adapter limitation (resolved in v0.3)

The adapter reads explicit rendered timetable tables with Date/Time/Event/Round columns, supports mixed relays and repeated junior occurrences, and requires event identity plus explicit completeness evidence. Schedule-scoped revision wording is parsed; global page timestamps are ignored.

This adapter is tested against clearly labelled synthetic HTML. The v0.2 live ISU programme capture returned a client-rendered loading shell. At that stage its dynamic API was not yet validated. See [LIVE-API.md](LIVE-API.md) for the subsequently implemented real API adapter. The earlier limitation is historical; current incomplete/unpublished responses still stay in review. PDF collection/parsing and change/version tracking function with the real Vancouver protocol. This is the main remaining collection gap, alongside the previously documented live start-list and standings-row adapters.

## Adaptive monitoring

The general collector uses these intervals; the current disabled GitHub workflow is scoped to the finite Montreal campaign described in [ACTIVATE-MONTREAL.md](ACTIVATE-MONTREAL.md):

| Event proximity | Target interval |
| --- | --- |
| Active local competition days | 30 minutes |
| Final 48 hours | 30 minutes |
| 48-72 hours away | 2 hours |
| Within 14 days | 4 hours |
| Distant or past event | 24 hours |

A one-minute due-time tolerance avoids repeatedly skipping an entire interval due to small runner start delays. Due checks, source history and selected versions survive in the isolated `pilot-data` branch. Workflow wakeups can be delayed by GitHub; these are approximate polling intervals, not guaranteed deadlines or race-start clocks.

The workflow still requires a public repository and `ENABLE_PILOT=true`, uses standard `ubuntu-24.04` runners, and uploads no Actions artifacts/caches. No private runner minutes, larger runners, Cloudflare deployments or paid services are activated. GitHub documents free standard hosted runner usage for public repositories: https://docs.github.com/en/billing/concepts/product-billing/github-actions .

## Validation

The v0.2 baseline passed 55 Python tests plus 4 Worker tests (59 total); later deliveries add API, publication and monitoring tests. New tests cover both supersession directions, unordered conflicts, same-day ambiguity, later fetch/print/upload rejection, unchanged starting-round identity with revised time, empty/partial retrieval retention, no removal of known rounds, source-version persistence, layout-only changes, history bounds and adaptive polling across Montreal DST. Workflow YAML and cron/public guard were parsed/checked. GitHub scheduling itself has not been activated.
