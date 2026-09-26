# Early Warning corrective validation — 26 September 2026

## Outcome and root causes

The operational unit is now one case per project. Raw alert rows remain contributing signals and retain backward-compatible endpoints. The default queue is New; New, Acknowledged, Under Review, Resolved and Dismissed are mutually exclusive. Priority/classification views intentionally include open reviewed cases and display their state.

| Failure | Cause | Correction |
|---|---|---|
| Deployed parity | Live `https://65.1.139.1:8443` serves JavaScript identical to pre-fix `ad5817a5da6270785059570cc8a6036aa9080362`; `/api/v1/alerts/cases` returns 404. CI deploys main, while this work is on paimana-earlyWarning. | Image revision in health/header, versioned scripts, no-store responses, and deployment verifier checking exact served asset hashes and migrated columns. Deployment must still be performed. |
| replaceAll crash | Old live JS line 30 calls `a.alert_type.replaceAll` without checking its type. | Central safe normalization for strings, numbers, arrays, objects and missing fields; malformed records cannot crash the list. The particular production row that triggered the reported crash was not identified. |
| New count exceeds projects | Summaries count signal rows, while a project can have several signals. | All operational summary counts use distinct project cases. Raw count is separate. |
| Status duplicates / stays active | UI uses a broad active view and transitions one signal; sibling signals stay New. | Project endpoint locks the project and signals, transitions all open signals in one transaction; UI immediately removes the case from its previous queue and refreshes all panels. |
| Refresh unreliable | Refresh/rendering is vulnerable to overlapping requests and malformed data. | Single in-flight refresh; disable controls; refetch cases, summary and priority; retain filter; clear stale results on failure; restore controls. |
| Note disappears | A per-signal note is not consistently carried into project rendering/destination views. | Persist the note transactionally with workflow status, aggregate it into the case, escape and display it with update time in all queues and project details. |
| New evidence resets review | Escalation previously resets workflow to New. | New/escalated signals inherit/preserve reviewed project state and note; evidence timestamp flags new evidence separately. Unchanged resolved signals are not recreated on replay. |

No ML model, feature pipeline, model artifact or fusion formula changed. No full workflow event-history table was introduced; the latest note/state is retained and earlier closed signals are preserved.

## Verification results

- Python: **40 passed, zero skipped**, including real PostgreSQL 18 migration, idempotence and case-note persistence across fresh sessions/connections.
- JavaScript: **5 passed**, exercising the actual UI script with malformed payloads, all workflow states, escaped notes, refresh coalescing, counts and failures.
- Browser on isolated localhost database: N28000105 moved New → Acknowledged → Under Review → Resolved. Each source queue emptied for that case; destination displayed the respective saved note. Refresh retained Acknowledged. N22000279 separately moved New → Dismissed. Browser reload and API restart preserved closure/note. Browser error log was empty.
- Actual served frontend hashes, revision health contract and database columns passed the deployment verifier locally. This is **not** a Docker or production validation.
- Existing dashboard, project list/detail, explanation/SHAP and sectors/states/trends endpoints returned HTTP 200.
- Existing prediction batch ran twice for one real project, each successful with zero failures; alert and prediction counts stayed unchanged.
- Compose/workflow YAML parsed; `git diff --check` passed. Docker build and image inspection remain unrun because Docker is absent. CI now includes both.

The isolated real CSV database contains **8 projects, 578 updates, 16 predictions and 22 raw alerts**. Before browser actions: 8 New cases. After validation:

| Queue | Unique projects |
|---|---:|
| New | 6 |
| Acknowledged | 0 |
| Under Review | 0 |
| Resolved | 1 |
| Dismissed | 1 |
| Total cases | 8 |
| Immediate | 0 |

These are local verification counts, not production counts. Intermediate acknowledgement/review counts were each 1. No synthetic projects were inserted into the application database; unit tests use disposable fixtures.

## Local verification commands (PowerShell, repository root)

```powershell
$env:DATABASE_URL='postgresql+psycopg2://triage_test@127.0.0.1:55432/postgres'
$env:TEST_POSTGRES_URL=$env:DATABASE_URL
$env:PAIMANA_REVISION='case-workflow-local-validation'
.venv/Scripts/python.exe -m scripts.migrate_alert_workflow
.venv/Scripts/python.exe -m pytest -q
node --test tests/test_early_warnings_ui.cjs
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
# In another terminal with the same DATABASE_URL and PAIMANA_REVISION:
.venv/Scripts/python.exe -m scripts.verify_warning_deployment --revision case-workflow-local-validation
.venv/Scripts/python.exe scripts/generate_predictions.py --limit 1
git diff --check
```

The test URL above is the existing local test cluster, not a production credential. The integration test creates/removes only its own randomly named schema.

## Production migration and deployment (bash on existing server)

First make the fix commit available on the remote, review/merge it into main for the existing CI workflow, and ensure GitHub's `EC2_HOST` points to **65.1.139.1**. CI deploys the exact triggering SHA. Manual alternative below prompts for the exact fix SHA printed in the delivery message. It requires a clean deployment checkout and preserves the existing database/nginx containers. Preserve the working server TLS configuration: repository nginx/compose still reference the old certificate path; its replacement cannot be inferred from the URL alone.

```bash
set -e
cd ~/paimana
test -z "$(git status --porcelain)"
git fetch origin
read -r -p 'Exact fix commit SHA: ' FIX_SHA
git cat-file -e "$FIX_SHA^{commit}"
git checkout --detach "$FIX_SHA"
export GIT_COMMIT=$(git rev-parse HEAD)
test "$GIT_COMMIT" = "$FIX_SHA"
docker compose build --pull paimana-api
# Exact additive migration; repeatable and transactional:
docker compose run --rm --no-deps paimana-api python -m scripts.migrate_alert_workflow
docker compose up -d --no-deps --force-recreate paimana-api
docker compose ps
docker compose exec -T paimana-api python -m scripts.verify_warning_deployment --revision "$GIT_COMMIT"
# Check the actual public proxy serves exactly the same image assets:
docker compose exec -T paimana-api python -m scripts.verify_warning_deployment --revision "$GIT_COMMIT" --base-url https://65.1.139.1:8443
```

If the API is still starting, retry the verifier once startup completes. It fails on mismatched revision, missing migration, stale asset bytes or invalid case-count invariants. No volume deletion or database reset is required.

## Exact live read-only checks

```bash
BASE=https://65.1.139.1:8443
curl -fsS "$BASE/health"
curl -fsSI "$BASE/js/early-warnings.js?v=cases-2"
curl -fsS "$BASE/api/v1/alerts/summary"
curl -fsS "$BASE/api/v1/alerts/cases?status=NEW"
curl -fsS "$BASE/api/v1/alerts/cases?status=ACKNOWLEDGED&include_closed=true"
curl -fsS "$BASE/api/v1/alerts/cases?status=UNDER_REVIEW&include_closed=true"
curl -fsS "$BASE/api/v1/alerts/cases?status=RESOLVED&include_closed=true"
curl -fsS "$BASE/api/v1/alerts/cases?status=DISMISSED&include_closed=true"
curl -fsS "$BASE/api/v1/alerts/priority?limit=5"
```

Health must contain the fix SHA and `early_warning_contract: 2`; case endpoints must return 200 and exclusive project IDs. New must not exceed total projects. No certificate verification bypass is needed.

## Browser acceptance after deployment

1. Hard reload `/early-warnings.html`; New should be selected with one card per project. Confirm summary counts against the API.
2. Select a real case appropriate for authorized review. Save an acknowledgement note and click Acknowledge: case leaves New, appears in Acknowledged with the note; counts update.
3. Refresh twice: selected tab remains, cards are unique, controls recover. Reload browser and check the saved note.
4. Enter a review note and click Under Review: case leaves Acknowledged, appears in Under Review.
5. Enter a closure note and Resolve: case leaves Under Review and priority, appears in Resolved. Separately Dismiss another suitable case and check Dismissed.
6. Restart only the API container and reload: states and notes remain. Check project details and browser console. Use real authorized workflow decisions on production; local test note text is not a recommendation to alter production records.

## Changed files

- `.dockerignore`, `Dockerfile`, `docker-compose.yml`: image content/revision and build arguments.
- `.github/workflows/deploy.yml`, `.github/workflows/early-warning-checks.yml`: exact-revision deploy verification and backend/frontend/image CI checks.
- `api/main.py`: revision health contract and response cache headers.
- `api/models/models.py`, `schema.sql`, `scripts/migrate_alert_workflow.sql`: additive evidence timestamp.
- `api/routers/alerts.py`: project-case routes, unique counts and priority.
- `api/services/alert_cases.py`: aggregation and transactional case transitions.
- `api/services/alert_engine.py`, `api/services/alert_priority.py`: preserve reviewed states, evidence timestamps and legacy normalization.
- `frontend/early-warnings.html`, `frontend/project-details.html`: helper loading, versioned assets and case wording.
- `frontend/js/api.js`: fresh case/summary/priority requests and project mutations.
- `frontend/js/warning-ui.js`: shared defensive rendering helpers.
- `frontend/js/early-warnings.js`, `frontend/js/project-warnings.js`: case queues, refresh, safe fields and persisted notes.
- `scripts/verify_warning_deployment.py`: image/schema/served-asset/API checks.
- `tests/test_alert_cases.py`, `tests/test_alert_postgres.py`, `tests/test_alert_triage.py`, `tests/test_early_warnings_ui.cjs`: case, migration and rendering regression coverage.
- `README.md`, `EARLY_WARNING_VALIDATION.md`: corrected semantics and verification/deployment instructions.

## Remaining blockers

No configured SSH key/server connection was available, and Docker is not installed locally. Therefore production migration, container rebuild/image inspection and post-deploy browser validation were not executed. The supplied URL enables read-only inspection but does not grant a server shell. The live deployment still requires the fix. The exact fix commit SHA is supplied in the delivery message (a commit cannot contain its own SHA).
