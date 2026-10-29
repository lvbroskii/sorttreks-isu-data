# Disabled Cloudflare delivery - infrastructure validation

Target: `integration/feed-v1`, Worker `sorttreks-approved-feed`, `worker/wrangler.delivery.jsonc` with `SERVE_APPROVED=false`. No D1, KV, R2, cron, site route, API secrets, approved-data publication or paid observability. The deployment requires an authenticated Cloudflare account with Workers Free selected; the configuration file does not set an account's billing plan.

## Preflight completed 29 October 2026

- Official Wrangler 4.155.0 deployment dry run passed. Compiled upload: 11.80KiB, gzip 4.10KiB. Only binding: `SERVE_APPROVED` string `false`.
- 35 JavaScript regression tests passed, including disabled gating before upstream/cache reads, allowed/rejected CORS preflights, both production origins, bodyless HEAD, read-only methods, expiry, ETag/cache mocks and failed upstream responses.
- Found and fixed a real cross-origin refresh defect: `If-None-Match` triggers OPTIONS preflight. Exact production origins now receive read-only GET/HEAD preflight permission for this header. Unknown origins, write methods and extra headers are rejected. Credentials remain omitted.
- Local Wrangler runtime could not start in the current environment: `uv_interface_addresses returned Unknown system error 1`. A subsequent local smoke test therefore failed with connection refused and zero executed checks. This is not a passed runtime test and not evidence of an edge deployment failure.
- Live Cloudflare deployment/results must be recorded after authentication and actual deployment. Do not label a dry run, local mock or guessed workers.dev address as a live deployment.

## Reproduce preflight

```bash
node --test tests/*.test.mjs
WRANGLER_SEND_METRICS=false npx wrangler@4.155.0 deploy --dry-run --config worker/wrangler.delivery.jsonc --outdir out/cloudflare-disabled
```

## Account/deployment steps

1. Sign in to Cloudflare and choose the intended account. Confirm Workers Free, with no plan upgrade or paid feature activation. If a new account or workers.dev subdomain requires acceptance of terms, the owner must complete that setup.
2. Use secure Wrangler login on an authorized computer, or the authenticated Cloudflare dashboard. Never paste API tokens into chat or commit them. No GitHub Actions Cloudflare secrets are needed for this disabled infrastructure test.
3. From this branch's repository root deploy the existing code:

```bash
WRANGLER_SEND_METRICS=false npx wrangler@4.155.0 login
WRANGLER_SEND_METRICS=false npx wrangler@4.155.0 deploy --config worker/wrangler.delivery.jsonc
```

4. Record the exact workers.dev URL returned by the deployment. Preserve `SERVE_APPROVED=false`; do not connect sorttreks.lv or its DNS. If using dashboard upload, use the exact bundled `worker/out/cloudflare-disabled/delivery.js`, with the string variable `SERVE_APPROVED=false` and no resource bindings.
5. Run the live read-only smoke checker using that actual origin:

```bash
python3 scripts/test-disabled-delivery.py https://ACTUAL_DEPLOYED_WORKER.workers.dev
```

Expected: health200 with enabledfalse/databasefalse; feed503 with explicit fallback error and no-store; both sorttreks.lv origins have correct CORS; OPTIONS permits conditional read requests; untrusted preflight403; unknown route404; POST405; HEAD has no body; repeated disabled/conditional requests remain503 without ETags. The smoke test sends no data updates and creates no resources.

## What disabled testing can establish

The deployed disabled route deliberately bypasses upstream fetches and the cache. Validate its no-store/error semantics live. Successful-feed edge-cache hits, ETag304, expiry and upstream-failure handling while enabled cannot be tested through that disabled public route. These remain local regression tests until a separate approved non-production test or genuine approved feed is authorized. Do not toggle production serving or upload synthetic data to test these paths.

Montreal `pilot.yml`, `pilot-data`, its cadence/end guard and the existing Site remain untouched.

## Current account blocker

The selected Google authentication flow reached Cloudflare, but Cloudflare returned: `Unable to sign in. Try again or use your email and password.` A fresh dashboard check also remained signed out. The account and Workers plan therefore could not be inspected, no actual Worker was created, no live workers.dev URL exists from this attempt and no live smoke checks passed. Manual account authentication is required before continuing. Do not infer a missing account or a specific failure cause from this generic message. No credentials or authentication callback values are included in the repository.
