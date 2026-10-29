# Public validation without historical captures - v0.4.2

## Dependency audit and resolution

| Previously capture-dependent area | Public replacement | Historical validation |
| --- | --- | --- |
| `test_pilot.py`: C08 parsing, matching, shell/document discovery and patch boundary | Ten-row hand-authored synthetic C08, synthetic result observations and minimal generated Next Flight HTML | Original source-based cases remain local |
| `test_revisions.py`: timetable rows, printed revision and archived-shell comparison | Same authority/retention assertions against synthetic C08 and shells | Historical Vancouver conclusions are not reproduced by CI |
| `test_live_api_synthetic.py`: synthetic mutations previously loaded full real API fixtures | Nine-round/three-result-group synthetic contract and three heats per round | No live-status claim |
| `test_live_api_real.py`: eight actual-source cases | Eight labelled synthetic API contract cases in `test_public_contract.py` | Actual-source test module remains local only |
| `test_publication_real.py`: six Montreal capture cases | Six labelled synthetic publication contract cases in `test_public_contract.py` | Actual-source test module remains local only |
| `test_publication_synthetic.py`: transitions previously reused Vancouver capture rows | Generated synthetic programme, explicit empty shape and malformed cases | None claimed |
| `test_monitoring.py`: empty body, event pages and replay transport | Fully synthetic HTTP, hash/304/error/archive/restart contracts | None claimed |
| Monitoring runtime's historical `baselineManifest` | Removed; only a genuine live empty response establishes the empty baseline | Initial already-populated source is labelled without inferring a transition |
| Workflow `api-sample` command | `synthetic-sample`, prominently labelled `synthetic-not-official` | Historical replay remains optional local-only code |

No tests are skipped to get a green build. Actual-capture modules are not shipped
and are not falsely relabelled as real validation. Their logic has synthetic public
counterparts, but **synthetic tests do not replace the evidential value of actual
captured sources**. The count is not a measure of new live-source validation.

All source-adapter identity binding, absolute timestamps, round/heat distinction,
complete-group checks, strict draw states, federation/athlete matching, opening-day
coverage and explicit supersession rules are unchanged. Only fixture providers,
test/sample plumbing and the live baseline initialization were changed. Unknown
IDs, unsupported schemas, partial sources and conflicts still go to review.

## Complete offline workflow rehearsal

`tests/offline_workflow.py` uses the real collector, HTTP client, authority history,
archive, fresh-runner restoration and data-branch scripts. It supplies a synthetic
HTTP transport, with no ISU network requests, and a temporary local bare Git remote.
It asserts:

1. An empty programme creates no confirmed starts or first-publication claim.
2. A populated programme is validated, has Riga labels and pins its first observation.
3. A round-time revision is recorded while an unresolved authority conflict retains
   the selected snapshot.
4. A source failure retains both the selected snapshot and first-publication evidence.
5. Four evidence commits append across fresh runner/working directories.

GitHub's separate `Offline pilot validation` workflow additionally checks checkout,
standard Ubuntu tooling, tests and the same rehearsal. It appends a tiny summary
with `validationType: synthetic-not-official`, `monitoringActivated: false` and the
source commit/run ID to **`pilot-validation`**, never `pilot-data`. No capture bodies
are uploaded. The branch script has an exact `pilot-data` / `pilot-validation`
allowlist and cannot push `main` or force-push.

## Activation decision

A successful GitHub offline validation proves the test package is complete and
that the selected runner/token can append evidence. It does **not** prove Montreal
has published a programme or confirm the real service's pre-race states.

After that green result, controlled read-only Montreal monitoring can be activated
within the existing public-repository/free-runner guards and finite campaign. It
must still retain verified fallback data and flag uncertain live content. Leave
`ENABLE_PILOT` unset until the owner explicitly activates it. No sorttreks.lv or
Cloudflare connection is made by either workflow.
