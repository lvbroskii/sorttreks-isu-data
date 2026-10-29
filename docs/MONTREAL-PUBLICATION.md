> Historical implementation notes: the referenced source captures are kept locally and are not included in public CI. See [PUBLIC-VALIDATION.md](PUBLIC-VALIDATION.md).

# Montreal publication check - 29 October 2026, 14:53 Latvia time

This is a one-off read-only check of the official Montreal World Tour #2 event
page, Schedule and Results tabs and the public endpoints used by the frontend.
The check completed at 12:53:42 UTC / 14:53:42 Europe/Riga.

| Publication stage | Actual evidence | Interpretation |
| --- | --- | --- |
| Schedule tab visible | Active `schedule_16272` in the event's tab registry; dynamic schedule block; loading shell in HTML | Visible tab, independently of programme publication |
| Daily session starts/ends | No verified session rows in the checked tab or programme response | Not verified; do not derive sessions or end times from race rounds |
| Detailed race-round times | Programme endpoint HTTP 200, `data.value: []` | No published round rows in this response; no times to convert |
| Roberts Krūzbergs' draw | No verified result/round IDs from the checked programme or Results page; result inventory HTTP 404 | Unverified, not proof of absence or withdrawal |
| Reinis Bērziņš' draw | Same identifier limitation | Unverified, not proof of absence or withdrawal |

The exact programme response was:

```json
{"status":200,"message":"Event schedule fetched successfully","data":{"discipline":{"discipline_id":3,"title":"SHORT TRACK"},"value":[]}}
```

Source:
`https://front-api.isu.org/events/getschedule/isu-short-track-world-tour-2-montreal`

It is byte-for-byte identical to the earlier empty Montreal capture. The tab's
visibility does not establish that session or round times are now available.
The captured Schedule block has `content: {"is_dynamic": true}`; it contains no
embedded session timetable or schedule-document requirement. No PDF was fetched
by this focused check.

The independent inventory probe was:
`GET https://front-api.isu.org/events/get-event-result/isu-short-track-world-tour-2-montreal`

It returned HTTP 404 with the exact body:

```json
{"code":404,"message":"Not Found"}
```

The checked Results page also exposed no `event_result_id` or
`event_result_round_id` values. Accordingly **no heat-list POST was made**:
querying those endpoints would require guessing identifiers or reusing another
event's IDs. This is an identifier-discovery limitation, not a verified finding
that the athletes have no published draw anywhere. Diagnostic probes using the
observed child slugs returned an empty, discipline-null schedule and an inventory
404 respectively; neither was treated as an authoritative programme.

## Implementation

The collector now emits independent `publication.stages` for the tab, session
evidence, round times and each athlete's draws. It stores stage changes separately
from schedule revision decisions. A stage change cannot approve publication,
resolve an authority conflict or erase verified fallback data.

The new focused command reads the event page, discovered Schedule/Results tabs
and the programme API. If the programme is empty or unsupported, it separately
probes the public result inventory. If a genuine supported programme appears,
the existing round/heat adapter handles extraction and Riga time conversion.
A newly populated inventory with an unseen schema still requires validation;
it is not promoted to a confirmed draw automatically.

```bash
PYTHONPATH=src python3 -m isu_pilot publication --event 2026-27-wt2 \
  --state .state/montreal-publication --out out/montreal-publication
```

This command does not activate polling, fetch PDFs, deploy services or emit a
website patch. It saves raw response versions and local publication observations.
Repeated calls compare stages within the same event. HTTP error bodies are now
archived with a separate `errorBodySha256`, without replacing the previous
successful source body or treating an error response as verified data.

## Fixtures and tests

`fixtures/real/montreal-publication-2026-10-29/` contains five fresh raw captures:
event page, Schedule page, Results page, empty programme and inventory error,
plus method/URL/retrieval/status/hash provenance. The actual report and summary
are in `examples/montreal-publication/`.

- `tests/test_publication_real.py`: six tests of actual captures, page visibility,
  unchanged empty response, draw-discovery limitation, repeated checks and fallback.
- `tests/test_publication_synthetic.py`: thirteen tests of separate publication
  stages, explicit normalized session evidence, Riga DST conversion, confirmed
  draws versus first-round coverage, failed retrieval, HTTP error archiving and
  an **explicitly synthetic** Montreal empty-to-populated programme transition.
- No populated Montreal programme, session-only ISU payload or pre-race Montreal
  draw was captured. Synthetic session evidence tests the normalized report
  contract; it does not establish a live session-payload adapter.

Run all tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/worker.test.mjs
```

The website's existing verified fallback stays in place. No sorttreks.lv changes,
scheduling activation, Cloudflare deployment or paid service activation occurred.
