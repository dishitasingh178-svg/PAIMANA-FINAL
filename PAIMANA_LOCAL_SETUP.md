# PAIMANA AI: Local Setup After Integration Fixes

## Data pipeline (do not collapse these stages)

```text
Raw government dataset (~7–8 columns)
        ↓
Cleaning / standardization script
        ↓
sushi_superClean.csv  ← 20 columns, database import stage
        ↓
api/ml/feature_engineering.py
        ↓
47 engineered ML features
        ↓
Pre-trained XGBoost + Cox artifacts
```

`5-star edible sushi.csv` is a 52-column modeling dataset containing the 47 engineered features plus target/validity columns. It is **not** used as the database import source by `pipeline.py`.

## 1. Environment

Use Python 3.11. Do not use the bundled Windows `venv` from the archive.

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Database

Create a PostgreSQL database named exactly:

```text
infrastructure_db
```

Set `DATABASE_URL` in `.env` to your local PostgreSQL credentials.

## 3. Put the correct CSV in the project root

The import script expects:

```text
sushi_superClean.csv
```

It intentionally refuses files that do not have exactly 20 columns. This prevents accidentally importing the 52-column modeling dataset.

Validate it first:

```powershell
python scripts\validate_clean_dataset.py
```

## 4. Import the portfolio

```powershell
python pipeline.py
```

The pipeline creates the four tables and imports one project row plus all historical monthly updates. Re-running it resets those four application tables first so the import remains deterministic.

## 5. Start the API

```powershell
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000/
```

Health:

```text
http://127.0.0.1:8000/health
```

## 6. Generate the initial AI risk portfolio

The dashboard intentionally does not invent risk values. After importing the historical data, generate a prediction for the latest stored snapshot of each project:

```powershell
python scripts\generate_predictions.py
```

For a quick smoke test first:

```powershell
python scripts\generate_predictions.py --limit 10
```

Then refresh the dashboard.

## Important

- Models are loaded from the existing `ml_package` artifacts. They are not retrained at runtime.
- Project IDs are identifiers, not ML features.
- Historical lookbacks use exact calendar-month keys. Missing months stay missing rather than silently using a neighboring month.
- Dashboard numbers are data-derived. There are no fabricated 1,981/247/183/42.78 fallback values.

## Early Warning workflow upgrade

Before starting against an existing PostgreSQL database, run from the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.migrate_alert_workflow
```

The same additive migration also runs during API startup. It preserves existing alerts.
No new application environment variables are required. See README.md, “Actionable Early
Warning Center”, for Docker deployment, exact verification/curl commands, priority rules,
and optional PostgreSQL integration tests. Demo page: `/early-warnings.html`.
