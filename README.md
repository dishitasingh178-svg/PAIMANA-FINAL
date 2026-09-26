# PAIMANA AI 🚀

## Predictive & Explainable Intelligence for Infrastructure Project Monitoring

> **From monitoring projects to identifying risk earlier.**

PAIMANA AI is a Smart India Hackathon (SIH) project concept for enhancing infrastructure project monitoring with an AI-assisted, risk-oriented interface.

The repository currently contains two main application layers:

- **Frontend:** a multi-page web dashboard for project monitoring, risk analytics, early warnings, project details, project ingestion, and an AI assistant interface.
- **Backend:** a **FastAPI** service exposing versioned project, dashboard, analytics, prediction, alert, and assistant API contracts.

The repository is structured as an integration/prototype layer. Several frontend screens are already designed and contain API integration hooks, while a number of backend endpoints currently return placeholder/empty responses. The trained ML artifacts and database implementation are **not present in this repository snapshot**.

---
#Deployed link : https://65.1.139.1:8443/
---
# 🎯 Problem

Large infrastructure projects involve substantial public investment and can run for many years. During implementation, projects may experience:

- Cost escalation
- Schedule and commissioning delays
- Increasing expenditure
- Slow milestone progress
- Revisions to project cost and timelines
- Financial and physical progress mismatches
- Difficulty prioritizing which projects need immediate attention

A monitoring system can show what has already happened, but decision-makers also need help answering:

> **Which projects may become risky, and where should monitoring attention be focused first?**

PAIMANA AI is designed around this shift from primarily **descriptive monitoring** toward **predictive and proactive risk intelligence**.

---

# 💡 Proposed Solution

PAIMANA AI brings project information, risk signals, analytics and AI-assisted interaction into one interface.

The application is designed around the following workflow:

```text
Project Monitoring Data
        │
        ▼
   Backend / APIs
        │
        ├──────────────► Project Portfolio
        │
        ├──────────────► Executive Dashboard
        │
        ├──────────────► Risk Analytics
        │
        ├──────────────► Early Warnings
        │
        ├──────────────► Project Intelligence
        │
        └──────────────► AI Assistant
                              │
                              ▼
                     Natural-language interaction
```

The broader project vision includes a predictive ML layer that can generate project-level risk signals and explain the factors behind those predictions.

---

# 🚀 Key Features

## 1. Executive Dashboard

The dashboard provides a high-level monitoring view intended for decision-makers.

It includes UI components for:

- Total projects
- High-risk projects
- Delayed projects
- Revised project cost
- Geographic project visualization across India
- Risk distribution
- Recent alerts

The dashboard uses:

- **Chart.js** for charts
- **Leaflet** for the map
- OpenStreetMap tiles for map visualization

The current frontend contains API calls for live dashboard/map/risk data, while the corresponding backend implementation is not yet fully connected in this repository snapshot.

---

## 2. Project Portfolio

The **Project Portfolio** page is designed to allow users to:

- Search projects
- Filter by status
- Filter by sector
- View implementing agencies
- View project IDs
- View original and anticipated costs
- View milestone progress
- View AI risk score and risk label
- Open detailed project views

The page currently calls a backend project endpoint and renders returned project data dynamically.

---

## 3. Project Intelligence

The project details screen is designed as a project-level drill-down.

It contains UI elements for:

- Project name
- Project ID
- Sector
- Implementing agency
- State
- Risk score
- Risk level
- Original cost
- Anticipated cost
- Cost escalation
- Delay
- Physical progress
- Milestone progress
- Financial/expenditure progress
- Approval and commissioning dates
- ML risk-driver attribution

This is intended to be the main place where a user moves from a portfolio-level warning to the underlying project-level explanation.

---

## 4. Project Ingestion & Analysis

The **Add New Project** screen provides a form for entering project information.

The form currently collects:

### Project identity

- Project name
- Implementing agency
- Sector
- State

### Timeline

- Date of approval
- Original commissioning date
- Anticipated commissioning date

### Financial and physical progress

- Original cost
- Cumulative expenditure
- Milestones achieved
- Total milestones

After submission, the frontend sends the project information to a prediction API and expects an ML response containing:

- Risk score
- Risk label

The current repository contains the frontend integration contract, but the corresponding `/api/predict` endpoint is **not implemented by the current FastAPI backend**.

---

## 5. Risk Analytics

The **Portfolio Risk Analytics** page is designed to provide deeper portfolio-level analysis.

Current UI sections include:

- Risk distribution by sector
- Top AI cost-escalation drivers
- Historical risk trend over time

The page uses **Chart.js** and contains a dynamic API integration for sector risk analytics.

A fallback dataset is also present in the frontend for UI demonstration when the live endpoint is unavailable.

---

## 6. Early Warning Center

The **Early Warning Center** is designed to surface projects requiring attention.

The UI contains:

- Critical alert count
- High-risk alert count
- Alert cards
- Project names
- Links to project details
- Risk-related warning information

The backend currently exposes an alerts endpoint, but it returns an empty alert collection in this repository snapshot.

---

## 7. PAIMANA Intelligence Assistant

The AI Assistant screen provides a conversational interface for natural-language questions about the infrastructure portfolio.

Example questions shown in the UI include:

```text
Show me all Railway projects with critical risk
```

and:

```text
Summarize delays for project ID 120100075
```

The frontend sends chat messages to:

```text
POST /api/chat
```

and expects a response containing a `reply` field.

The FastAPI backend currently exposes a separate versioned assistant contract:

```text
POST /api/v1/assistant/
```

The current backend response explicitly indicates that the AI assistant is not connected yet.

Therefore, the conversational UI is present, but the LLM/database reasoning layer is **not implemented in this repository snapshot**.

---

# 🧠 AI / Machine Learning Vision

The broader PAIMANA AI work developed alongside this application includes a predictive risk architecture based on:

- **XGBoost** for cost-risk prediction
- **XGBoost** for schedule/time-risk prediction
- **Cox Proportional Hazards** for supplementary time-to-risk analysis
- **SHAP** for model explainability

The intended model flow is:

```text
PAIMANA Project Snapshot
          │
          ▼
   Feature Engineering
          │
          ├───────────────┐
          ▼               ▼
   Cost XGBoost     Schedule XGBoost
          │               │
          ▼               ▼
      Cost Risk       Schedule Risk
          │               │
          └───────┬───────┘
                  ▼
        Cox Survival Signal
                  │
                  ▼
          Risk Score Fusion
                  │
                  ▼
          Project Risk Score
                  │
                  ▼
       Risk Tier + Explanations
```

### Unified risk score

The ML architecture developed for the project uses:

```text
40% → Cost Risk
40% → Schedule Risk
20% → Cox Time-to-Risk Signal
```

with the following risk tiers:

| Score | Risk Tier |
|---:|---|
| 0–24.99 | LOW |
| 25–49.99 | WATCH |
| 50–74.99 | ELEVATED |
| 75–100 | CRITICAL |

### Explainability

SHAP is used to identify the major model features contributing to an individual prediction.

Important:

> SHAP values describe model attribution. They should not be interpreted as proof that a feature causally created the risk.

### Important repository note

The **trained ML model files, feature-engineering pipeline and `predictor.py` are not included in the uploaded repository snapshot**.

Therefore, this README describes the ML architecture as part of the overall PAIMANA project, but the current Git repository should **not** be presented as containing the trained inference implementation.

---

# 📊 Model Development Results

The predictive modelling work associated with the project produced the following chronological held-out results.

## Cost Risk Model

| Metric | Result |
|---|---:|
| PR-AUC | **0.4368** |
| ROC-AUC | **0.7932** |
| F1 | **0.4566** |
| Precision | **0.5865** |
| Recall | **0.3738** |

## Schedule Risk Model

| Metric | Result |
|---|---:|
| PR-AUC | **0.8091** |
| ROC-AUC | **0.8954** |
| F1 | **0.7211** |
| Precision | **0.7387** |
| Recall | **0.7044** |

## Cox Survival Model

The supplementary Cox model achieved a concordance index of approximately:

```text
0.586
```

These figures belong to the project's ML development work and should be interpreted as model-development results rather than production guarantees.

---

# 🏗️ Current Architecture

The repository currently follows a simple two-layer structure:

```text
                    PAIMANA AI
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
      Frontend                     Backend
   Static HTML/JS                 FastAPI
          │                           │
          │                           ├── Projects
          │                           ├── Dashboard
          │                           ├── Analytics
          │                           ├── Predictions
          │                           ├── Alerts
          │                           └── Assistant
          │
          ▼
   REST API integration
```

The intended end-state architecture can be extended to:

```text
┌─────────────────────────────────────────────┐
│                 PAIMANA UI                  │
│                                             │
│ Dashboard │ Projects │ Analytics │ Alerts   │
│ Project Intelligence │ AI Assistant        │
└──────────────────────┬──────────────────────┘
                       │ REST APIs
                       ▼
┌─────────────────────────────────────────────┐
│              FastAPI Backend                │
│                                             │
│ Projects │ Dashboard │ Analytics            │
│ Predictions │ Alerts │ Assistant            │
└───────────────┬───────────────┬─────────────┘
                │               │
                ▼               ▼
        Project Data       ML / AI Layer
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
                  Cost       Schedule      Cox
                 XGBoost     XGBoost      Model
                    │           │           │
                    └───────────┼───────────┘
                                ▼
                           Risk Fusion
                                │
                                ▼
                         Risk + Drivers
```

A production database and fully connected ML/LLM services are **not implemented in the current repository snapshot**.

---

# 📁 Repository Structure

The uploaded repository currently contains:

```text
Paimana/
│
├── README.md
│
├── api/
│   ├── main.py
│   ├── config.py
│   ├── .gitignore
│   │
│   ├── models/
│   │   └── __init__.py
│   │
│   ├── routers/
│   │   ├── alerts.py
│   │   ├── analytics.py
│   │   ├── assistant.py
│   │   ├── dashboard.py
│   │   ├── predictions.py
│   │   └── projects.py
│   │
│   ├── schemas/
│   │   ├── assistant.py
│   │   ├── prediction.py
│   │   └── project.py
│   │
│   └── services/
│       └── __init__.py
│
└── frontend/
    ├── index.html
    ├── login.html
    ├── dashboard.html
    ├── projects.html
    ├── add-project.html
    ├── project-details.html
    ├── risk-analytics.html
    ├── early-warnings.html
    ├── ai-assistant.html
    │
    └── assets/
        ├── css/
        │   └── custom.css
        │
        └── js/
            ├── api.js
            └── theme.js
```

---

# 🛠️ Technology Stack

## Frontend

- HTML5
- JavaScript
- Tailwind CSS via CDN
- Chart.js
- Leaflet
- Lucide Icons
- Inter font
- Browser `fetch()` API
- `localStorage` for theme preference

## Backend

- Python
- FastAPI
- Pydantic
- Uvicorn-compatible ASGI application
- `python-dotenv` for environment configuration
- FastAPI CORS middleware

## AI / ML Layer

The associated ML development uses:

- XGBoost
- Cox Proportional Hazards
- SHAP
- pandas
- NumPy
- scikit-learn
- joblib

The ML artifacts themselves are not part of the current Git repository snapshot.

---

# 🔌 Backend API

The FastAPI application is created in:

```text
api/main.py
```

The API is configured with:

```text
APP_NAME
APP_VERSION
DEBUG
```

through environment variables.

## Root

```http
GET /
```

Example response:

```json
{
  "message": "PAIMANA Backend is running",
  "version": "1.0.0"
}
```

---

## Projects

### List projects

```http
GET /api/v1/projects/
```

Supported query parameters:

```text
page
page_size
sector
state
```

### Get a project

```http
GET /api/v1/projects/{project_id}
```

The current implementation returns a `404` because project persistence has not yet been connected.

---

## Dashboard

```http
GET /api/v1/dashboard/
```

Current response structure:

```json
{
  "summary": {},
  "sector_distribution": [],
  "state_distribution": [],
  "risk_distribution": [],
  "trend": []
}
```

---

## Analytics

### Sector analytics

```http
GET /api/v1/analytics/sectors
```

### State analytics

```http
GET /api/v1/analytics/states
```

### Trend analytics

```http
GET /api/v1/analytics/trends
```

The current implementations return empty data structures.

---

## Predictions

```http
POST /api/v1/predictions/
```

Request:

```json
{
  "project_id": "PROJECT_ID"
}
```

Response schema:

```json
{
  "project_id": "PROJECT_ID",
  "cost_overrun_prediction": null,
  "delay_prediction_months": null,
  "risk_score": null,
  "risk_level": null
}
```

The prediction endpoint currently defines the API contract but does not yet execute the trained ML models.

---

## Alerts

```http
GET /api/v1/alerts/
```

Current response:

```json
{
  "alerts": [],
  "total": 0
}
```

---

## Assistant

```http
POST /api/v1/assistant/
```

Request:

```json
{
  "user_id": null,
  "query": "Show me all Railway projects with critical risk",
  "voice": false
}
```

The current backend returns:

```json
{
  "answer_text": "AI Assistant is not connected yet.",
  "answer_audio_url": null,
  "structured_data": null
}
```

---

# ⚠️ Current Integration Status

One of the most important things to understand when running this repository is that the frontend and backend are **not completely synchronized yet**.

For example, the frontend currently references endpoints such as:

```text
/api/projects
/api/predict
/api/chat
/api/v1/ongoing-high-risk
/api/v1/risk-distribution
/api/v1/analytics/sector-breakdown
```

while the current FastAPI backend exposes versioned routes such as:

```text
/api/v1/projects/
/api/v1/predictions/
/api/v1/assistant/
/api/v1/analytics/sectors
```

This indicates that the repository is currently at an **integration/prototype stage** rather than a fully connected production application.

Before deployment, the frontend API calls and backend routes should be aligned.

---

# ▶️ Running the Backend

From the repository root:

```bash
cd api
```

Create a Python virtual environment:

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the backend dependencies:

```bash
pip install fastapi uvicorn python-dotenv
```

Start the API:

```bash
uvicorn main:app --reload
```

The backend will normally be available at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive API documentation will be available at:

```text
http://127.0.0.1:8000/docs
```

The current repository does not include a `requirements.txt` or `pyproject.toml`, so dependencies are currently not pinned in the repository.

---

# ▶️ Running the Frontend

The frontend is a collection of static HTML pages.

The easiest development approach is to serve the `frontend` directory using a local static HTTP server.

From the `frontend` directory:

```bash
python -m http.server 5500
```

Then open:

```text
http://127.0.0.1:5500/
```

You can navigate through:

```text
index.html
login.html
dashboard.html
projects.html
add-project.html
project-details.html
risk-analytics.html
early-warnings.html
ai-assistant.html
```

Because the frontend currently contains hard-coded localhost API URLs, the backend should normally be running on:

```text
http://127.0.0.1:8000
```

---

# 🔐 Configuration

The backend reads environment variables using `python-dotenv`.

Supported variables in the current implementation include:

```env
APP_NAME=PAIMANA Backend
APP_VERSION=1.0.0
DEBUG=false
```

Create a `.env` file inside the `api` directory if needed.

**Never commit real API keys, passwords, database credentials or other secrets to GitHub.**

---

# 🎨 UI / Design

The interface uses a clean monitoring-oriented design with:

- Light and dark modes
- Responsive layouts
- Orange accent styling
- Dashboard cards
- Risk badges
- Charts
- Maps
- Project tables
- Alert cards
- Conversational assistant UI

Theme state is stored in the browser using:

```text
localStorage
```

The shared theme functionality is implemented in:

```text
frontend/assets/js/theme.js
```

---

# 🔒 Data & Privacy

PAIMANA project data can contain sensitive government/project-monitoring information.

The repository intentionally does not include the large cleaned PAIMANA CSV/Parquet datasets used during ML development.

Do not add:

- Private datasets
- Credentials
- API keys
- Database passwords
- `.env` files containing secrets
- Government-confidential information

to the public repository.

---

# 🧪 Prototype vs Production

This repository should currently be considered a **prototype/integration codebase**.

### Present in the repository

- FastAPI application structure
- API router structure
- Pydantic request/response schemas
- Static frontend
- Dashboard UI
- Project portfolio UI
- Project detail UI
- Risk analytics UI
- Early warning UI
- AI assistant UI
- Project ingestion form
- Chart and map integrations
- Dark mode
- Frontend/backend API contracts

### Not yet fully implemented in this repository

- Persistent project database
- Database models and migrations
- Fully populated project APIs
- Connected trained ML inference service
- End-to-end feature engineering service
- Working prediction endpoint using the trained models
- Production AI/LLM assistant
- LLM-to-database query layer
- Production authentication/authorization
- Production deployment configuration
- Complete frontend/backend endpoint synchronization

These items can be added as the project moves from prototype to deployment.

---

# 🔮 Future Scope

The architecture can be extended with:

## 1. Database Integration

Connect the FastAPI backend to a persistent database containing:

- Projects
- Reporting snapshots
- Costs
- Expenditure
- Milestones
- Dates
- Risk predictions
- Alerts
- Agencies
- Sectors
- States

## 2. ML Integration

Connect the prediction API to the trained PAIMANA ML package:

```text
Project Data
     ↓
Feature Engineering
     ↓
predictor
     ↓
Cost Risk
Schedule Risk
Cox Risk
     ↓
Unified Risk Score
```

## 3. Automated Early Warnings

Generate alerts when:

- Risk crosses a threshold
- Cost growth accelerates
- Schedule deterioration increases
- Expenditure and physical progress diverge
- Milestone progress stalls
- Risk changes significantly between reporting periods

## 4. AI Assistant

Connect the assistant to:

```text
User Question
     ↓
Intent / Query Understanding
     ↓
Database / Analytics Layer
     ↓
Relevant Project Data
     ↓
LLM Explanation
     ↓
Natural-language Answer
```

The LLM should explain retrieved/validated information rather than inventing project facts.

## 5. Explainable Project Intelligence

Project pages can combine:

- Risk score
- Cost risk
- Schedule risk
- Time-to-risk signal
- SHAP drivers
- Historical trends
- Agency benchmarks
- Sector benchmarks

into one decision-support view.

---

# 🎯 Expected Impact

The objective is not simply to produce another dashboard.

The intended impact is to help monitoring teams:

1. **Identify potentially risky projects earlier**
2. **Prioritize projects requiring closer attention**
3. **Understand the major factors behind model predictions**
4. **Compare risk across sectors, states and agencies**
5. **Move from retrospective monitoring toward proactive intervention**

Actual monetary savings or avoided cost escalation should only be estimated after validation through a real-world operational pilot.

---

# 🧑‍💻 Development Philosophy

PAIMANA AI is designed around a human-in-the-loop approach.

The system should:

```text
Detect
  ↓
Explain
  ↓
Prioritize
  ↓
Support human investigation
  ↓
Enable informed intervention
```

AI predictions are intended as **decision-support signals**, not automatic replacements for domain experts or government monitoring processes.

---

# ⚠️ Limitations

Current limitations include:

- The repository is not yet connected to a persistent project database.
- Several backend routes are placeholders.
- Frontend and backend endpoint naming is not fully synchronized.
- The AI assistant is not connected to an actual LLM/database reasoning pipeline.
- The prediction API does not currently load the trained ML models.
- Authentication is represented by a frontend login page but is not implemented as backend authentication.
- Current frontend fallback/demo values should not be interpreted as live government data.
- ML performance results come from historical model evaluation and do not guarantee future operational performance.
- Production use would require security, governance, validation, monitoring and domain-expert oversight.

---

# 📌 Project Status

**Current stage: Prototype / SIH development**

The repository establishes the application shell and API contracts for an AI-assisted infrastructure monitoring platform.

The next major integration step is to connect:

```text
Frontend
   ↕
FastAPI Backend
   ↕
Database
   ↕
Feature Engineering
   ↕
ML Prediction Package
   ↕
Risk + Explainability
   ↕
AI Assistant
```

---

# 🏁 Vision

PAIMANA AI aims to evolve infrastructure monitoring from:

> **“What happened to the project?”**

to:

> **“What is likely to happen next, why is the project at risk, and where should attention be focused first?”**

By combining project monitoring, predictive analytics, explainable AI, early warnings and natural-language interaction, the platform can provide a foundation for more proactive infrastructure project oversight.

---

## 📜 Disclaimer

This project is developed as a **Smart India Hackathon prototype** demonstrating the feasibility of applying AI/ML techniques to infrastructure project monitoring.

The repository currently contains prototype frontend and backend components. Production deployment would require integration with authorized operational data, security and privacy controls, database infrastructure, model validation, model monitoring, domain-expert review, governance and appropriate human oversight.

**No specific monetary savings or operational outcomes should be assumed until validated through a real-world pilot.**

## Actionable Early Warning Center

Open `http://127.0.0.1:8000/early-warnings.html` locally, or `/early-warnings.html`
on the deployed PAIMANA host. Project details link to a project-filtered warning queue.

### Migration and deployment

No new application environment variable is required. The existing `DATABASE_URL`
must point to PostgreSQL and its role must be allowed to alter `alerts`. Plain
`postgresql://` URLs are normalized to the installed psycopg2 driver, preserving
compatibility with SQLAlchemy 2.1. Explicit driver URLs are left unchanged.

For the existing Docker deployment, from the repository directory on the server:

```sh
docker compose build paimana-api
docker compose run --rm paimana-api python -m scripts.migrate_alert_workflow
docker compose up -d paimana-api
```

For a non-Docker server with its environment already configured:

```sh
python -m scripts.migrate_alert_workflow
```

The migration is also run automatically during FastAPI startup, after `create_all`.
Existing tables are migrated explicitly; `create_all` alone is not used as a migration.
It is transactional, serialized across workers, and repeatable. Existing resolved rows
become RESOLVED and other legacy rows become NEW. No rows are removed. Historical
workflow timestamps are left unknown rather than inventing resolution dates.
The standalone SQL alternative is:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -f scripts/migrate_alert_workflow.sql
```

For psql use a plain `postgresql://` connection URL, not a SQLAlchemy `+psycopg2` URL.

### Local verification (PowerShell)

From the project root with Python 3.11+ installed and the existing `.env` configured:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest tests -q
node --check frontend/js/api.js
node --check frontend/js/early-warnings.js
node --check frontend/js/project-warnings.js
node --test tests/test_early_warnings_ui.cjs
.venv/Scripts/python.exe -m scripts.migrate_alert_workflow
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Unit/API tests use disposable in-memory SQLite and never the application database.
To also test the additive migration and workflow persistence on PostgreSQL, set the
optional **test-only** variable `TEST_POSTGRES_URL` to a disposable PostgreSQL database
whose role can create schemas, then run the same pytest command. The test creates a
randomly named schema, migrates legacy rows twice, verifies all statuses/notes, and
removes only its own schema. Without this variable that integration test is skipped.

To exercise the existing batch prediction pipeline against a populated local database
(this writes real predictions and alerts):

```powershell
.venv/Scripts/python.exe scripts/generate_predictions.py --limit 5
```

### API examples (bash/curl)

Use an alert ID returned by the list call; no demo IDs are hardcoded:

```sh
BASE=http://127.0.0.1:8000
curl -fsS "$BASE/api/v1/alerts"
curl -fsS "$BASE/api/v1/alerts/priority?limit=10"
curl -fsS "$BASE/api/v1/alerts/summary"
read -r -p 'Alert ID from the list: ' ALERT_ID
curl -fsS -X PATCH "$BASE/api/v1/alerts/$ALERT_ID/status" -H 'Content-Type: application/json' -d '{"status":"ACKNOWLEDGED","review_note":"Agency contacted. Awaiting clarification."}'
curl -fsS -X PATCH "$BASE/api/v1/alerts/$ALERT_ID/status" -H 'Content-Type: application/json' -d '{"status":"UNDER_REVIEW","review_note":"Reviewing the latest execution report."}'
curl -fsS -X PATCH "$BASE/api/v1/alerts/$ALERT_ID/status" -H 'Content-Type: application/json' -d '{"status":"RESOLVED","review_note":"Review completed."}'
curl -fsS -X PATCH "$BASE/api/v1/alerts/$ALERT_ID/status" -H 'Content-Type: application/json' -d '{"status":"DISMISSED","review_note":"Reporting discrepancy verified."}'
```

`GET /alerts` preserves the original array shape and fields, defaults to active rows,
and accepts `status`, `severity`, `alert_class`, `min_priority`, `project_id`,
`include_closed`, `limit` (1–500, default 100), and `offset`. Filtering and priority
sorting happen before pagination. Summary counts cover the whole portfolio; Immediate
counts unique active projects. Priority returns unique projects with active warnings.

### Calculation and interpretation

Priority = 40% stored composite risk + 25% deterioration + 20% financial exposure
+ 15% urgency. Deterioration is `clamp(delta * 5, 0, 100)`. The prior prediction is
from the immediately previous distinct available report month, not the most recently
executed job. Same-month reruns are selected by generated_at and prediction ID.
Missing prediction/history/cost is explicitly unavailable and contributes zero.

Exposure prefers positive anticipated, then revised, then original cost. It is
normalized against the linearly interpolated 95th percentile of all current portfolio
project exposures, capped at 100. Exposure is project cost, **not expected financial
loss**. Alert urgency is 100/70/40 for CRITICAL/ELEVATED/WATCH. Project priority uses
the highest active alert severity. Priority labels are IMMEDIATE >=80, HIGH >=65,
MEDIUM >=45, otherwise ROUTINE. The ML artifacts, feature ordering and 40/40/20 model
fusion are unchanged.

Freshness compares project reports with the maximum report_month in project_updates,
never today's date: current is HIGH, one calendar reporting month behind is MEDIUM,
and two or more behind is LOW, subject to relevant field/history completeness.
Data confidence measures evidence quality, not calibrated model confidence.

The actual engine shares COST_ESCALATION for anticipated/revised cost rules and
SCHEDULE_SLIPPAGE for delay/date movement. Classification follows these actual types.
The original alert message remains the recorded trigger. Evidence and priority use
latest available data, with each reporting month displayed separately; a continuing
alert is not a claim that its condition was re-triggered this month. Rule cost baselines
retain the engine's existing revised/anticipated/original preference, distinct from
financial exposure's requested anticipated/revised/original preference.

Unresolved signals deduplicate by project and type, including dismissed rows. Higher
severity preserves an acknowledged/under-review project workflow; a dismissed condition
can reopen as New when it escalates.
Same/lower severity preserves the original message and review state; latest risk
increases of at least 10 points are surfaced in the derived explanation. Resolved
conditions may generate a new alert when evidence changes; unchanged resolved signals
are not recreated on replay. Existing duplicate rows are retained as contributing signals;
all operational queues and counters group one case per project. No full event-history table is added.
All five statuses are accepted; reopening is supported. `is_resolved` is true only
for RESOLVED. Dashboard and assistant active queries also exclude DISMISSED.

### Validation performed for this iteration

- 34 passing tests, including focused calculations/API coverage, constant query count,
  and a real PostgreSQL 18 additive migration/persistence test.
- Existing feature engineering and prediction service run against 578 real CSV updates
  for eight projects: 16 April/May 2024 predictions and 22 rule-generated alerts.
- Application startup/model loading and live alerts, priority, summary, dashboard,
  project, SHAP and analytics endpoints verified locally; frontend JavaScript syntax checked.
- Browser workflow verified for acknowledgement, review, resolution, dismissal, filters,
  empty states, project details and literal rendering of markup in review notes.
- Existing batch prediction script completed five real projects with zero failures.

The verification database is isolated from deployment. No production credentials,
model artifacts, synthetic demo records or external APIs were added. Example priority
92 is not forced: actual project data determines whether any IMMEDIATE projects exist.
Deploying the live site and recording a submission video remain deployment/demo steps.


### Project-case corrective release

The Early Warning Center defaults to **New**, with exclusive project workflow queues.
Use `GET /api/v1/alerts/cases` and `PATCH /api/v1/alerts/projects/{project_id}/status`
for operational cases; the raw-alert endpoint above remains backward compatible.
Summary counts are distinct projects. Actions transition all open signals and save
the officer note transactionally. See [the corrective validation report](EARLY_WARNING_VALIDATION.md)
for current test results, real-data counts, deployment commands and known blockers.
