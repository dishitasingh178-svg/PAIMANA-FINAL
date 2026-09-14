import os
import sys
import argparse

# Add project root to Python import path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from sqlalchemy import func
from database import SessionLocal
from api.models.models import Project, Prediction
from api.ml.feature_engineering import build_feature_snapshot
import ml_package.predictor as predictor


def latest_update_month(db, project_id):
    from api.models.models import ProjectUpdate
    return db.query(ProjectUpdate.report_month).filter(ProjectUpdate.project_id == project_id).order_by(ProjectUpdate.report_month.desc()).first()


def main():
    parser = argparse.ArgumentParser(description="Generate PAIMANA ML predictions for the latest snapshot of each project.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    db = SessionLocal()
    ok = failed = 0
    try:
        projects = db.query(Project).order_by(Project.project_id).all()
        if args.limit: projects = projects[:args.limit]
        for project in projects:
            pid = str(project.project_id).strip()
            month_row = latest_update_month(db, pid)
            if not month_row:
                failed += 1
                continue
            month = month_row[0]
            try:
                features = build_feature_snapshot(pid, month, db)
                result = predictor.predict_project_row(features)
                db.add(Prediction(project_id=pid, report_month=month, **result))
                ok += 1
                if ok % 100 == 0:
                    db.commit()
                    print(f"Generated {ok:,} predictions...")
            except Exception as exc:
                failed += 1
                print(f"[SKIP] {pid}: {exc}")
        db.commit()
        print(f"Done. successful={ok:,}, failed={failed:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
