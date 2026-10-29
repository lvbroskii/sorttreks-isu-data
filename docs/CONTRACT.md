# Pilot contract and review boundary

`schemaVersion: 1`; UTF-8 JSON; ISO 8601 venue timestamps with explicit offsets; IANA venue zone supplied in event registry; display zone Europe/Riga.

Source records: requested/final URL, SHA-256, MIME type, first-seen/fetched times, ETag/Last-Modified if present, changed flag, HTTP status/error. The exact SHA is a content revision, not proof of sporting authority. Raw bodies stay in `.state/<sha>.body` on a local run. Keep `.state` private/untracked; no credentials are collected.

Event report: `verificationStatus`, `issues`, discovered documents/tabs, timetable rows, first/later athlete round observations, comparison, and `calendarPatchCandidate`. `approvedForWebsite` remains false in every collector result. No ranking-derived seeding, name-only nationality inference, fixed-hour timezone offsets, or unverified heat times.

A start requires matching event/date, LAT code, exact normalized athlete identity, distance, gender, occurrence, round, and exactly one uncancelled matching timetable row. Entry evidence is insufficient. For an opening-day FIRST start, the normalized evidence must additionally assert complete opening-day list coverage or an explicit event-specific direct-entry confirmation; a single later-round list cannot establish that the athlete bypassed earlier rounds. Without that proof the first-start candidate stays unconfirmed. Historical results can validate which round was raced but cannot masquerade as a start list published beforehand. Dates for grouping remain venue dates; Riga may be the next day.

Patch allowlist: `id`, `athleteFirstStarts`, `athleteRoundStarts`, `conditionalRounds`, `startListsUrl`, `startListsVerified`. Session starts/ends and all homepage-related fields are intentionally excluded from this initial pilot. Current UI uses `confirmed===true`; only start-list evidence may produce those athlete rows, and no candidate is externally served as approved.

Later approval must independently check source event identity/revision, source completeness, cancellation scope, missing/removed athletes, round-vs-heat interpretation and manual locks. Unknowns cannot overwrite known data. Any reduction/removal or schedule conflict requires review. A successful HTTP response or generic Results/Schedule tab is not verified sporting data.

The Worker scaffold permits GET only. Its approved calendar route is disabled in configuration. The collector contains no remote writer and the GitHub workflow has no Cloudflare/Sites credentials or deployment steps. The SQL schema requires a reviewer for approved snapshots but is not a complete authorization system: an eventual ingest/review implementation must enforce it server-side, with atomic revision selection and retention caps.

Revision authority and history are implemented in `revisions.py`; see REVISION-TRACKING.md. Local resolved selection is never website approval. Raw retrieval dates, Last-Modified and upload times do not determine schedule authority. The parsed source history is bounded and persisted by the isolated data branch.

Integration addition: `docs/INTEGRATION.md` and `integration/feed.mjs` define a separate approved `sorttreks.calendar.v1` delivery contract. This does not change the collector's always-false `approvedForWebsite` boundary or enable Stage D. The offline reviewer/exporter is `python -m isu_pilot.feed`; the read-only delivery Worker is `worker/delivery.mjs` and remains disabled. The legacy pilot/D1 scaffold is retained for compatibility.
