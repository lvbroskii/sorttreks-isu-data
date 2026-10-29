# Public programme and heat-assignment adapter - v0.3

This is a read-only collector update, checked on 29 October 2026. No account, key,
GitHub scheduling, Cloudflare service or website publication was activated.
The original revision/authority tests remain in place.

## How the loading shell was resolved

The event pages serve a Next.js shell; the programme component then makes a public
JSON request to `https://front-api.isu.org`. Static inspection of the **actual
page-referenced** JavaScript established these routes:

| Data | Method and route | Parameters |
| --- | --- | --- |
| Programme | `GET /events/getschedule/{eventSlug}` | Slug from the registered official event URL |
| Round metadata | `POST /events/get-event-result-round` | `event_result_id`, discovered from the programme |
| Individual heat assignments/results | `POST /events/get-event-result-round-heats-stk-single` | `event_result_id`, `event_result_round_id`, `country_code=` |

These POSTs are read queries used by ISU's own results component. The collector
allows only those two exact POST paths and parameter sets. It cannot submit
arbitrary API mutations. No session cookie or authentication was needed.
`fixtures/real/live-api/endpoint-discovery.json` records module URLs, hashes and
route evidence. Modules were read as text, not executed. The frontend's optional
`GET /events/get-event-result/{slug}` returned HTTP 404 for the registered event
slugs during investigation; collection does not depend on it. The programme
already supplies the actual result/round identifiers.

## Actual validation versus synthetic tests

| Event | Actual response captured | Verified interpretation |
| --- | --- | --- |
| Vancouver World Tour #1 | Programme plus metadata for all 52 rounds and 44 individual-round heat lists | 52 round timestamps; all six opening LAT athlete/distance combinations reconstructable retrospectively |
| Montreal World Tour #2 | HTTP 200; `data.value: []` | Programme unpublished in this API snapshot; no confirmed starts extracted |
| Bormio Junior World Cup #1 | HTTP 200; `data.value: []` | Programme unpublished in this API snapshot; junior format not yet validated |
| Bormio Junior World Cup #2 | HTTP 200; `data.value: []` | Programme unpublished in this API snapshot; junior format not yet validated |

The complete collector run encountered one HTTP 503 on an individual heat-list query. A later bounded read succeeded. Both attempts are retained in `examples/v03/retrieval-attempts.json`; the captured replay uses the successful body.

Exact raw bodies and request/retrieval/hash metadata are in
`fixtures/real/live-api/manifest.json`. The event-page captures independently
verify season, dates and event IDs. The fixture replay checks every body hash.
`tests/test_live_api_real.py` uses these actual bodies without mutation.
`tests/test_live_api_synthetic.py` explicitly contains synthetic status changes,
malformed payloads and transport tests. Existing synthetic authority tests remain
in `tests/test_revisions.py`. Passing synthetic pre-race tests **does not validate
the actual pre-race status vocabulary** of the timing service.

Vancouver's captured heat records are `Finished` results, with starting positions
and event-specific federation codes retained. Reinis Bērziņš appears in the 500 m
preliminaries, Heat 8; Roberts Krūzbergs first appears in the heats, Heat 7. All
six reconstructed opening starts remain `confirmed: false` as pre-race evidence.
The adapter never labels post-race results as an archived pre-race draw.

## Normalization and completeness

- Programme timestamps are absolute ISO UTC instants. They are converted using
  the registry's venue IANA zone, then `Europe/Riga` for bilingual labels. Browser
  local-time rendering and unrelated CMS zone defaults are not used.
- Each programme row retains result/round IDs, raw UTC time and round-start time
  basis. Individual heat timestamps are separate `heatStartsAt` evidence.
- Round metadata must bind to the verified CMS event ID and exact result ID. Its
  complete round-ID set must equal the programme's set for that distance. Unknown
  rounds, missing/duplicate IDs, unscoped timestamps, out-of-event dates and
  incomplete first/last-day programme coverage prevent a complete candidate.
- Junior repeated-distance result IDs require an explicit occurrence mapping.
  Unsupported/repeated formats go to review instead of collapsing into race 1.
- Heat queries request **all countries**. Event representation uses
  `started_for_nf_code == LAT`, not a profile's nationality. The parser checks
  parent IDs, unique athletes, heat IDs, contiguous heat sequence and nonempty
  assignments. Missing draws do not prove absence. Unknown pagination envelopes
  are rejected. The current endpoint returns an unpaginated array without an
  independent total-heat count, so structural coverage cannot detect an omitted
  final heat that the source itself does not disclose. Likewise, without an
  independent result-group inventory it cannot detect a whole distance omitted
  from both the programme and its enumerated metadata. `programmeComplete` is
  a structural check of the returned groups, not an independent inventory audit.
- Explicit `Scheduled` / `Start List` round-and-heat states, valid positions and
  absent result fields are supported conservatively for future draws. Those
  positive states are currently **synthetic-tested only**. Any different real
  status requires inspection and a new captured fixture before confirmation.
- First-round confirmation requires complete pre-race draws for every earlier
  or equal opening-day round in that distance/occurrence. A later-round listing
  alone cannot establish a seeded athlete's first start. Generic entries and
  qualification lists are not substituted for heat assignments.
- All subsequent-day published heat assignments are matched chronologically.
  Unavailable or unknown-status rounds remain unconfirmed; relay athlete lineup
  extraction is not part of this individual-athlete adapter.

## Revisions and safeguards

Raw API response bodies are hashed and archived like PDFs. POST cache/history
keys include the canonical request form, so two round requests never share a
source entry. Retrieval attempts and source changes are retained. Parsed API
programmes enter the existing revision history as `online` versions; round-level
changes retain previous/new times and source URLs.

The programme payload currently has **no schedule-specific revision timestamp
or revision number**. Round metadata `created_at` / `updated_at` values are
preserved as import observations, not fed into `revisedAt`. A later retrieval or
a later timing import cannot establish supersession. Finished round timestamps
can also include seconds absent from the programme's minute-aligned values;
these observations remain separately visible in the report.

The current Vancouver API programme differs from both the archived C08 and the
manual website reference. There is no captured pre-race revised programme proving
which times superseded the other sources. The real-source replay therefore reports
`conflicting-schedules-without-proven-supersession`, leaves publication disabled
and preserves the website fallback. It does not conclude that the website was
incorrect or that today's API body is the missing pre-race revision.

An API failure, empty programme, incomplete metadata, unknown draw state or
unsupported format does not erase a previous verified snapshot. Official event
Documents/protocol/C08 extraction remains available alongside the online source.
If both are unavailable or conflict without explicit revision evidence, the
existing local/site reference remains the fallback and manual review is required.

## Run and reproduce

```bash
# Actual captured-source replay; no network:
PYTHONPATH=src python3 -m isu_pilot api-sample --out out/api-captures
# All tests (real and synthetic are separate files):
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/worker.test.mjs
# One-off live read; does not activate scheduling:
PYTHONPATH=src python3 -m isu_pilot collect --event 2026-27-wt2 --out out/montreal
```

Live reads have a 300-second per-client network budget, 30-second request timeout,
12 MiB per-body limit and at most three concurrent read queries. A budget failure
is recorded, never replaced with fabricated source content. JSON parsing uses
only the standard library; PDF fallback uses the existing free Poppler tool.

No setup is required beyond Python/Node and outbound HTTPS to the official ISU
hosts, including `front-api.isu.org`. If a runner blocks that host, permit HTTPS
443 for that exact hostname. No paid proxy/browser or scraping service is used.
Leave `ENABLE_PILOT` unset; do not run deployment commands. Existing optional
setup instructions are preparation for a later, separately approved activation.

## Still needs real-source review

1. Capture Montreal's actual programme and draws when populated; confirm the
   service's real pre-race status values and seeded-start coverage.
2. Capture both Bormio programmes and confirm how repeated distances/occurrences
   are encoded before accepting that junior format.
3. Obtain explicit revision evidence or an archived pre-race revised Vancouver
   programme to resolve the historical C08/manual/API differences.
4. Classifications and approved-feed publication remain separate unfinished
   stages; this adapter neither fills standings from race placings nor publishes.
