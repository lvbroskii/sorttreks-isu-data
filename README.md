# sorttreks.lv ISU automation pilot - public-safe v0.4.2

Read-only Montreal monitoring code, separate from sorttreks.lv. Monitoring remains
inactive until the owner enables `ENABLE_PILOT`. No Cloudflare deployment or paid
service is involved.

**Historical ISU captures are local only.** This repository contains no historical
HTML, PDF extracts, raw source snapshots or compressed capture archives. Public CI
uses small, hand-authored synthetic contracts. Passing it does not establish live
ISU availability, historical supersession or the service's real pre-race status
vocabulary.

## Validate without historical files or ISU network access

Python 3.12+, Node 20+ and Git are sufficient; no Python dependencies or keys:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/worker.test.mjs
PYTHONPATH=src python3 -m isu_pilot synthetic-sample --out out/synthetic
PYTHONPATH=src python3 tests/offline_workflow.py out/rehearsal
```

`Offline pilot validation` runs this on GitHub pushes to `main`. It rehearses four
checks with synthetic HTTP and a local bare Git repository: empty, populated,
revised/conflicting, then failed. It also verifies GitHub token permissions by
appending **only a small synthetic result summary** to `pilot-validation`.
It performs no ISU collection and does not activate the monitoring workflow.

## Activation

Wait for the **Offline pilot validation** job to pass. Then follow
[ACTIVATE-MONTREAL.md](docs/ACTIVATE-MONTREAL.md). The monitoring workflow uses only
live source responses for its empty baseline, current programme and athlete draws.
It never imports the synthetic contracts. If the first live response is already
populated, it records an initial populated observation without claiming an
empty-to-populated transition.

Read [PUBLIC-VALIDATION.md](docs/PUBLIC-VALIDATION.md) for the dependency audit,
public/local test split and validation limits. Source authority, athlete identity,
coverage, time conversion and fallback checks have not been relaxed.
