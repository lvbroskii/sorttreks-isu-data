# sorttreks.lv ISU data pilot

Working read-only collector, separate from the ChatGPT Sites website. Initial implementation based on `sorttreks-isu-automation-feasibility-2026-10-20.md` (20 October assessment). No Sites publication, Cloudflare deployment, paid service, remote database, or scheduled task was activated.

## Montreal monitoring preparation - v0.4

Read-only GitHub monitoring is ready for activation. It checks Montreal roughly
every 30 minutes during the finite campaign, archives compressed raw responses,
pins the first empty-to-round-data transition and reports subsequent revisions.
Existing verified data and unresolved authority conflicts remain protected.
See [the precise activation steps](docs/ACTIVATE-MONTREAL.md).

Nothing has been activated. No website/Cloudflare credentials or paid services
are needed. Use a separate public repository and standard Ubuntu runners only.

## Montreal publication stages - v0.3.1

The focused 29 October check confirms a visible Schedule tab but an empty
programme API. Roberts' and Reinis' draws remain unverified because no usable
Montreal result/round identifiers were discoverable. Publication stages now
track tab visibility, explicit session evidence, detailed round times and
confirmed athlete draws independently. Read [the check and exact responses](docs/MONTREAL-PUBLICATION.md).

```bash
PYTHONPATH=src python3 -m isu_pilot publication --event 2026-27-wt2 --out out/montreal-publication
```

## Live programme adapter - v0.3

The collector now reads the public JSON endpoints used by ISU's own programme
and results components. Vancouver validates 52 real round timestamps and all six
opening athlete/distance combinations retrospectively. Montreal and both Bormio
programmes returned successful empty arrays on 29 October; no pre-race starts
are invented. Read [docs/LIVE-API.md](docs/LIVE-API.md) for endpoint evidence,
completeness checks, actual versus synthetic tests and remaining validation.
See [the validation results](examples/v03/VALIDATION.md) and
[actual captured-source output](examples/v03/captured-source-report.json).

```bash
# Replays exact official captures without network access:
PYTHONPATH=src python3 -m isu_pilot api-sample --out out/api-captures
```

No GitHub scheduling, Cloudflare deployment or website integration was activated.

## Revision tracking update

Schedule version history, conservative source authority selection, round-level change reports and adaptive polling are now implemented. Read [docs/REVISION-TRACKING.md](docs/REVISION-TRACKING.md). The Vancouver archive cannot establish the exact superseding online revision; website differences remain unresolved source/revision differences rather than a finding that the manually updated website was wrong. See `examples/vancouver-revision-validation.json`.

## Run now

Python 3.12+ and Node 20+ are sufficient for the deterministic sample and tests; no Python packages or API keys are required. Live PDF extraction also requires the free Poppler `pdftotext` command (`sudo apt-get install poppler-utils` on Ubuntu).

```bash
PYTHONPATH=src python3 -m isu_pilot sample --out out/sample
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/worker.test.mjs
# Reads public official sources only; creates local evidence and JSON:
PYTHONPATH=src python3 -m isu_pilot collect --out out/live
# Or collect one event:
PYTHONPATH=src python3 -m isu_pilot collect --event 2026-27-wt2 --out out/montreal
```

The 29 October live run fetched 25 official URLs successfully: Vancouver yielded 77 timetable rows and six opening starts; Montreal and both Bormio events had no verified detailed C08. See `examples/live-report-2026-10-29.json`.

Open `examples/vancouver.json`, `examples/report.json`, and `examples/summary.md` for the already generated, reproducible sample. Actual fetched source pages and reduced protocol extracts are in `fixtures/real`. The text extractor and website comparator have independent inputs; expected website times are never supplied to the extractor.

## What works in this delivery

- Official HTTPS allowlist, bounded downloads/timeouts, SHA-256 change detection, first-seen/fetched timestamps, local raw evidence and conditional requests when the corresponding local body exists. Unavailable sources do not re-verify stale evidence.
- Discovers event tabs and labelled PDF documents from actual rendered HTML and Next Flight JSON. It never executes downloaded JavaScript or fabricates event/result identifiers.
- Retrieves and extracts real Swiss Timing C08 PDF timetables; retains round start, distance, gender, round, relay/individual distinction, heat count, page, source text, cancellations and explicit breaks/day ends.
- Normalizes exact LAT athlete identities, handles athletes entering at later rounds, rejects DNS/unknown identities/ambiguous matches, keeps round times separate from heat times. Retrospective result-book participation remains explicitly unconfirmed as pre-race start-list evidence.
- Emits LV/EN Riga time labels with IANA zones, including Riga's October change and Montreal's November change; rejects ambiguous/nonexistent wall times.
- Generates calendar-shaped **candidate** arrays and compares Vancouver against the current manual site reference. No candidate is approved or applied.
- Includes four event registry entries: Vancouver, Montreal, Bormio #1 and #2. Collects availability/changes of the four actual World Tour Classification source URLs separately from event results.
- Disabled-by-default adaptive GitHub workflow, retained source/schedule versions, and locally tested read-only Worker/D1 schema scaffold. Neither contains a Sites publishing credential or code to publish the website.

## Vancouver result

The official protocol's C08 was printed **21 October 2026**; the protocol document was linked with publication date **26 October** when retrieved on 29 October. We cannot establish when this exact C08 was publicly available before the races.

All six opening athlete/distance combinations were reconstructed retrospectively. Their first rounds agree with the manual reference, but **all six times differ**:

| Athlete | Distance | Round | Website venue time | C08 venue time |
| --- | --- | --- | --- | --- |
| Roberts Krūzbergs | 500 m | Heats | 23 Oct 13:53 | 23 Oct 13:39 |
| Roberts Krūzbergs | 1000 m | Heats | 23 Oct 15:11 | 23 Oct 14:50 |
| Roberts Krūzbergs | 1500 m | Quarterfinals | 23 Oct 16:41 | 23 Oct 16:17 |
| Reinis Bērziņš | 500 m | Preliminaries | 23 Oct 09:39 | 23 Oct 09:21 |
| Reinis Bērziņš | 1000 m | Heats | 23 Oct 15:11 | 23 Oct 14:50 |
| Reinis Bērziņš | 1500 m | Quarterfinals | 23 Oct 16:41 | 23 Oct 16:17 |

The comparison is **needs-review**, not a finding that the website was wrong or a successful equivalence claim. The owner reports a subsequently revised online programme, but that revised timetable is absent from the archived source capture. The protocol and manual programme may represent different revisions; this pilot does not resolve that by choosing the newest fetch time. `approvedForWebsite` is always false. Historical matches have `evidenceKind: retrospective-result`, `confirmed: false`, and `heatStartsAt: null`. The compatible first-start patch is consequently empty.

The C08 also contains explicit lunch and day-end times. These are sporting timetable boundaries, not broadcast status. They are retained as evidence only; no homepage session/estimate/end fields are exported or changed.

## Deliberate limits / next adapters

This is a functioning Stage A pilot with Stage B/C foundations, not a completed unattended publishing system.

- The current Vancouver programme HTML is a `loading_schedule` shell. No programme is invented from that page. The pilot uses the discoverable detailed protocol instead. A tested rich-text/API programme adapter is still needed where no C08 is published.
- Live HTML/JSON start-list extraction has not yet been validated against the current timing frontend. The PDF C51-style start-list path is tested with explicitly synthetic fixtures; real Vancouver observations use results and are marked retrospective. Entries alone never confirm an athlete's first starting round; complete opening-day coverage or event-specific direct-entry proof is required in addition to the matching start list.
- Repeated junior distances must carry an explicit occurrence. Normalized matching supports them; ambiguous duplicate rows go to review. Bormio-specific real start lists/programmes must be captured and adapter-tested when published. Never assume a junior has entered every distance.
- Standings source discovery/hash monitoring works. Complete classification-row extraction, season selection and pagination/completeness validation are **not yet implemented**. Positions remain null; no World Rankings or race placements are substituted.
- No website approval, review UI, remote ingestion or site feed integration is enabled. Local authority selection can resolve explicitly evidenced revisions; ambiguous conflicts retain the previous snapshot. A conflict, identity mismatch, unsupported/scanned PDF, missing list, cancellation or unavailable source requires review. An adapter failure must not become a negative participation claim.
- Snapshot `config/site-reference.json` is a read-only copy of the current website data. It is a fallback/reference, not fresh collector evidence. The site itself still reads its own existing bundled files.
- The generated `calendarPatchCandidate` has the site's existing field names but is not a complete `races.json`. Future integration must merge only approved fields into the bundled data. Junior occurrence-aware display and future data refresh require separate integration work.

See [docs/SETUP.md](docs/SETUP.md) for exact GitHub and optional later Cloudflare setup, and [docs/CONTRACT.md](docs/CONTRACT.md) for review/feed boundaries.
