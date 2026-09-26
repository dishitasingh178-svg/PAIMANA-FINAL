# Classification, first navigation and performance validation

This follow-up starts from clean branch `paimana-earlyWarning`, commit `9f7cc32` (the prior workflow correction). It retains that correction and its deployment procedure in [EARLY_WARNING_VALIDATION.md](EARLY_WARNING_VALIDATION.md). The delivery message supplies this follow-up's exact commit SHA. No changes were made to the ML package/artifacts, feature ordering or fusion.

## Root causes and changes

| Issue | Evidence and fix |
|---|---|
| Same cases in classification tabs | Both API and frontend used membership in **all** contributing classifications. Now a case has one dominant class, chosen by highest signal priority score, then PREDICTIVE, DETERIORATION, OBSERVED_ISSUE on ties. Further tie-breaks choose a stable signal within that class. All classes and evidence remain in the case. Cards show Primary reason and Other signals. |
| Repeated refresh work | Cases, summary and priority each constructed a portfolio context and evidence. The page now calls `/api/v1/alerts/workspace` once, aggregating once and computing p95 once. Four batch queries plus two counts serve the complete response, versus 14 queries and three p95 calculations previously. Priority cards receive only their displayed fields; full case evidence remains available. |
| First-load/reload reliability | Scripts already load in dependency order after the DOM. No separate DOM-ready race was reproduced. Fresh dashboard navigation passed without reload. An initialization guard prevents duplicate binding; the request has a 15-second deadline; every failure clears the in-flight lock and stale panels, and Refresh retries. Loading state is synchronous. A failed-first-request recovery test proves it is not permanently poisoned. |
| Stale responses | Tab switches/mutations are blocked during refresh; refreshes coalesce. Mutations block other actions. Tests verify an old request cannot overwrite a newer tab or mutation. |
| Unsafe API values | Existing safe helpers retained; malformed classification objects/prototype-property names now also normalize safely. Original crash was the unguarded `a.alert_type.replaceAll` on line 30 of the old live script, as recorded in the previous report. No exact offending production row was recovered. |
| Deployment mismatch | Existing parity checks retained and extended to the workspace/dominant contract. Health contract is **3**, versioned assets are `cases-3`. No-store is now limited to warning-related pages/scripts/API, not every HTML/JS file. Image revision remains available in health and response headers. |
| Counts/status/notes | Prior project-level aggregation and transactional transitions retained and retested. Raw signals are not project counts. The default is New, state queues are exclusive, and notes are escaped and persisted with the case transition. |

No claim is made that a slow production SQL query or a DOM initialization race was reproduced: local measurements show fast individual endpoints on the eight-project copy. The confirmed avoidable work was repeated portfolio calculation and duplicate evidence transfer. No Redis or cross-request data cache was added, so Refresh reads current data.

## Measured performance

HTTP timing uses `perf_counter`, six requests per endpoint, first recorded separately and median of the other five. The before sample was taken before edits; after sample used the same eight-project database before additional browser state transitions. Values fluctuate at this scale.

| Endpoint | Before median ms | After median ms |
|---|---:|---:|
| summary | 30.23 | 30.13 |
| cases | 25.24 | 31.74 |
| priority | 36.88 | 31.32 |
| workspace (new combined refresh) | unavailable | 27.70 |

There is no across-the-board individual-endpoint speedup. The new page avoids calling those three endpoints separately. On the revised server, a concurrently fetched legacy three-endpoint refresh measured **37.95 ms median and 127,558 bytes**, versus **27.70 ms and 72,723 bytes** for workspace, about 43% fewer response bytes. No hidden tabs or per-project detail endpoints are fetched.

Actual browser automation timings, including locator/tool overhead:

- Fresh dashboard → Early Warnings navigation, until visible completed case list: **443 ms**.
- Refresh until visible completed case list: **319 ms**.
- Acknowledge until the case disappears from New: **303 ms**.
- Loading controls are set synchronously before the network request (regression tested); no independent sub-100-ms paint measurement was taken.

Browser timings were not captured before this follow-up, so no before/after browser speedup is claimed. These local results do not establish full-production-scale latency.

Reproduce HTTP timings with:

```powershell
.venv/Scripts/python.exe -m scripts.benchmark_warnings --base-url http://127.0.0.1:8000 --samples 6
```

## Tests and browser workflow

**43 Python tests passed, zero skipped**, including the real PostgreSQL 18 migration/idempotence test. **10 JavaScript tests passed**. New coverage includes class tie-breaking independent of row order, disjoint groups, all contributing classes preserved, one percentile calculation/six SQL queries per workspace, first-request failure recovery, synchronous loading, duplicate initialization, stale-response prevention and malformed classification objects. Existing tests continue covering workflow/status/count/notes/deduplication/legacy rows.

Browser verification used existing real records in the isolated local database:

1. Fresh navigation from dashboard loaded six New cases, counts and priority without reload.
2. Classification sets were Predictive `{N22000399}`, Deteriorating `{}`, Observed `{N22000085, N22000180, 220100303, N22000476, N22000256}`. They were pairwise disjoint. An empty class is legitimate; no values were fabricated to fill it.
3. N22000399 moved New → Acknowledged (`Testing acknowledgement persistence.`) → Under Review (`Execution report requested.`) → Resolved (`Issue verified and closed.`). Each source queue lost the case; each destination displayed its note. Refresh retained Acknowledged.
4. N22000085 separately moved New → Dismissed with a saved note.
5. API process restarted; browser reloaded; resolved note/state persisted. Browser error log was empty. Screenshot saved locally at `.venv/dominant-workflow-verified.png`.
6. Dashboard, project list/details/explanation and all three analytics endpoints returned 200. Prediction generation ran twice for one unchanged real project with zero failures; no duplicate case/alert was generated.
7. Served frontend bytes, database columns and health/workspace contract passed the deployment verifier locally. Docker image verification was not run: Docker remains unavailable.

## Final real-data counts

| Metric | Count |
|---|---:|
| Total projects | 8 |
| Real project updates | 578 |
| Predictions | 16 |
| Raw alerts | 22 |
| Unique cases | 8 |
| New | 4 |
| Acknowledged | 0 |
| Under Review | 0 |
| Resolved | 2 |
| Dismissed | 2 |
| Immediate | 0 |
| Predictive dominant, all workflow states | 0 |
| Deterioration dominant, all workflow states | 2 |
| Observed dominant, all workflow states | 6 |

After closure actions the remaining four open cases are Observed. Classification tabs exclude closed cases. Closed cases may include previously closed signals of the same closure status, so their strongest signal can differ from the former open case. The tables report actual final results; the earlier browser classification sets were measured before the closure actions. New <= total projects holds.

## Files changed in this follow-up

- `api/services/alert_cases.py`: deterministic dominant class and contributing classes.
- `api/routers/alerts.py`: dominant filters, shared summary helper and combined workspace response.
- `api/main.py`: contract 3 and scoped warning cache policy.
- `frontend/js/api.js`: workspace request with timeout.
- `frontend/js/early-warnings.js`: one refresh cycle, initialization guard, dominant filters and primary/secondary labels.
- `frontend/js/warning-ui.js`: safe dominant/contributing classification normalization.
- `frontend/early-warnings.html`, `frontend/project-details.html`: `cases-3` asset URLs.
- `scripts/verify_warning_deployment.py`: contract 3/workspace validation.
- `scripts/benchmark_warnings.py`: reproducible read-only endpoint and refresh benchmark.
- `.github/workflows/early-warning-checks.yml`: updated expected asset version in image check.
- `tests/test_alert_cases.py`, `tests/test_early_warnings_ui.cjs`: regression coverage.
- `README.md`, `EARLY_WARNING_VALIDATION.md`, `EARLY_WARNING_PERFORMANCE.md`: current semantics, results and deployment instructions.

## Exact local commands

```powershell
$env:DATABASE_URL='postgresql+psycopg2://triage_test@127.0.0.1:55432/postgres'
$env:TEST_POSTGRES_URL=$env:DATABASE_URL
$env:PAIMANA_REVISION='dominant-local-validation'
.venv/Scripts/python.exe -m scripts.migrate_alert_workflow
.venv/Scripts/python.exe -m pytest -q
node --test tests/test_early_warnings_ui.cjs
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
# Second terminal, same DATABASE_URL and PAIMANA_REVISION:
.venv/Scripts/python.exe -m scripts.verify_warning_deployment --revision dominant-local-validation
.venv/Scripts/python.exe -m scripts.benchmark_warnings
git diff --check
```

## Production deployment and outstanding external blockers

The current read-only HTTPS check of `https://65.1.139.1:8443` fails with **certificate verify failed: certificate has expired**. No insecure bypass was used. The earlier inspection found the old JS and no case endpoint; the current deployed SHA cannot now be verified. A server administrator must renew the site's configured TLS certificate, with the correct existing certificate paths, before secure live verification. The repository's old-IP certificate paths must not be blindly substituted.

There is still no configured SSH server connection/key and no local Docker executable. Therefore production migration, running-container asset inspection, Docker build and post-deploy browser tests could not be executed. Exact existing-server commands (after publishing the fix commit and restoring valid HTTPS):

```bash
set -e
cd ~/paimana
test -z "$(git status --porcelain)"
git fetch origin
read -r -p 'Exact fix commit SHA from delivery: ' FIX_SHA
git cat-file -e "$FIX_SHA^{commit}"
git checkout --detach "$FIX_SHA"
export GIT_COMMIT=$(git rev-parse HEAD)
test "$GIT_COMMIT" = "$FIX_SHA"
docker compose build --pull paimana-api
docker compose run --rm --no-deps paimana-api python -m scripts.migrate_alert_workflow
docker compose up -d --no-deps --force-recreate paimana-api
docker compose exec -T paimana-api ls -l /app/frontend/js/
docker compose exec -T paimana-api python -m scripts.verify_warning_deployment --revision "$GIT_COMMIT"
docker compose exec -T paimana-api python -m scripts.verify_warning_deployment --revision "$GIT_COMMIT" --base-url https://65.1.139.1:8443
```

The existing automated workflow deploys main, not this feature branch. Review/merge the fix into main and set `EC2_HOST` to the current host for that route; the workflow deploys its exact triggering SHA. No push or merge was performed by this local validation.

Exact live checks after TLS renewal/deployment:

```bash
BASE=https://65.1.139.1:8443
curl -fsS "$BASE/health"
curl -fsSI "$BASE/js/early-warnings.js?v=cases-3"
curl -fsS "$BASE/api/v1/alerts/summary"
curl -fsS "$BASE/api/v1/alerts/workspace?status=NEW"
curl -fsS "$BASE/api/v1/alerts/cases?classification=PREDICTIVE"
curl -fsS "$BASE/api/v1/alerts/cases?classification=DETERIORATION"
curl -fsS "$BASE/api/v1/alerts/cases?classification=OBSERVED_ISSUE"
curl -fsS "$BASE/api/v1/alerts/priority?limit=5"
```

Health must report the expected SHA and contract 3. Follow the browser workflow above on authorized production cases: fresh dashboard navigation; verify disjoint classification tabs and retained evidence; acknowledge/review/resolve with notes; separately dismiss; Refresh and browser reload; restart only API and recheck persistence. Measure production timings with the benchmark script. Do not apply local test notes to production cases without an appropriate review decision.
