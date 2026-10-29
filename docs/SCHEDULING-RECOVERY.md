# Native scheduling recovery - 29 October 2026

Confirmed before recovery: default main at c70c4c438d3f4e4ac99bb2ce13009b5596418439; pilot workflow400665651 active; exactly one collector run40892839928 (workflow_dispatch, 14:34:32Z / 16:34 Latvia); no schedule runs. The manual job collected and persisted evidence. Other offline workflow successes are not source collection. Cron syntax/date windows were valid. The last cron file commit is attributed to lvbroskii, not an unidentified bot. No root cause is established.

Current repository variable/administration reads are not exposed by this GitHub connection. Direct supported-URL reads of the non-secret ENABLE_PILOT setting and Actions permissions were rejected as unsupported endpoints. No access restriction was bypassed. The successful manual job proves the variable condition and required action/persistence permissions were effective at that time, not a fresh settings inspection.

Recovery attempt: rewrite the equivalent minute list `17,47` as POSIX `17/30`, preserving the existing UTC minute slots, finite month/day windows, main/public/ENABLE_PILOT guards, concurrency, collector, state and append-only pilot-data history. A default-branch commit may resynchronize a stale registration; this is a bounded recovery attempt, not proof of an invalid old cron or a known GitHub incident. Add a temporary native cron slot for29Oct16:03Z (18:03 Latvia) to observe a genuine schedule event without manually dispatching collection. Remove this diagnostic after observation. Python's existing year/end guards apply even if the date expression matches in a future year.

The job summary now identifies the actual event, cron, run ID and source commit. Proof requires all of: event schedule, successful collector step, successful persistence, a new pilot-data commit/check and new official response retrieval timestamps. A green offline test or workflow_dispatch run is insufficient.

Collection still stops 2Nov2026 at18:00Z /20:00 Latvia, with the same archive limits, source-authority rules and fallbacks. No change to sorttreks.lv or integration/feed-v1.

GitHub documents best-effort schedules with possible delays/drops. The public APIs expose created runs, not the internal schedule queue; zero runs cannot establish delay versus dropped delivery or registration failure.

If native scheduling remains silent, an independent Cloudflare Workers Free Cron Trigger can call this existing workflow's dispatch API. It must be a separate small scheduler, not the data delivery Worker. It requires account access plus a narrowly scoped GitHub credential (single repository, Actions write, Metadata read, short expiry). No such credential exists here and no alternative scheduler is activated by this change. External cron dispatches have event workflow_dispatch in GitHub, so proof must correlate the Cloudflare scheduled invocation with the resulting run and archive. Do not relabel them as native GitHub schedule events. Cloudflare scheduling and GitHub runner availability are also best effort; no free option provides an absolute timing guarantee.

References:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
