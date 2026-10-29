# Validation performed - 29 October 2026

- 25 Python unit tests pass using the standard library.
- 4 Node Worker route tests pass; no Cloudflare deployment is involved.
- `python -m compileall -q src` succeeds.
- Offline Vancouver sample executed from captured official C08/result extracts; 77 timetable rows, six retrospective opening starts, six timing discrepancies against the separate current-site snapshot.
- Live collector executed against all four configured events and four official classification URLs: 25 successful source fetches, no source transport failures in that run. Vancouver's detailed protocol was discovered and parsed. No verified detailed timetable was found for Montreal or either Bormio event by the current adapter. This is an adapter/public-source finding, not proof that no schedule exists elsewhere.
- `.github/workflows/pilot.yml` parsed as YAML. The public-repository/ENABLE_PILOT guards, standard runner, lack of artifact/cache uploads and lack of cloud/website publishing steps were inspected. It has not been executed in GitHub Actions because no GitHub account connection/repository exists yet.
- Worker tests cover read-only methods, default-disabled approved endpoint, unconfigured database, exact-origin CORS, ETag/304, candidate-only selection and D1 failure fallback. D1 schema tested using in-memory SQLite; approval rows require a reviewer.
- Timezone tests cover Riga midnight/DST, Montreal November DST, invalid clocks and ambiguous/nonexistent wall times. Athlete matching tests cover exact names/nation, direct-entry proof, no ranking inference, no heat-time invention, incomplete opening lists, DNS, missing/duplicate/cancelled rounds and separate repeated junior distances.
- Real HTML and protocol extracts are distinguished from explicitly synthetic start-list/junior-format inputs. Bormio real format parsing, full live start-list extraction, standings row completeness and authenticated remote ingestion remain unvalidated/unimplemented as described in README.
- The existing `/workspace/sites/latvijas-sorttreks` checkout remained clean. No site files, hosting configuration, live data, schedules, paid plans or services were changed.

## Revision-tracking update

55 Python plus 4 Worker tests pass (59 total). Detailed new coverage and current limitations are in REVISION-TRACKING.md. The real 29 October Vancouver captures were replayed end-to-end through the updated collector, producing 77 rows and explicitly flagging the incomplete online programme; see `examples/revision-capture-replay.json`. The preceding live fetch report is retained separately.
