import os
import sys
import argparse

# Add project root to Python import path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from database import SessionLocal
from api.models.models import Project, ProjectUpdate
from api.services.prediction_service import generate_prediction


def latest_update_month(
    db,
    project_id,
):

    row = (
        db.query(
            ProjectUpdate.report_month
        )
        .filter(
            ProjectUpdate.project_id
            == project_id
        )
        .order_by(
            ProjectUpdate.report_month.desc()
        )
        .first()
    )

    return row[0] if row else None


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate PAIMANA ML predictions "
            "and populate Early Warning alerts "
            "for the latest snapshot of each project."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    db = SessionLocal()

    successful = 0
    failed = 0

    try:

        projects = (
            db.query(Project)
            .order_by(Project.project_id)
            .all()
        )

        if args.limit:
            projects = projects[:args.limit]

        total = len(projects)

        print()
        print("=" * 60)
        print("PAIMANA EARLY WARNING BATCH")
        print("=" * 60)
        print(
            f"Projects to process: {total:,}"
        )
        print("=" * 60)

        for index, project in enumerate(
            projects,
            start=1,
        ):

            project_id = str(
                project.project_id
            ).strip()

            try:

                month = latest_update_month(
                    db,
                    project_id,
                )

                if not month:

                    failed += 1

                    print(
                        f"[SKIP] {project_id}: "
                        f"no project update."
                    )

                    continue

                # ------------------------------------------------
                # Canonical prediction pipeline.
                #
                # generate_prediction() also runs the Early
                # Warning Engine, so predictions and alerts
                # cannot become inconsistent.
                # ------------------------------------------------

                generate_prediction(
                    db,
                    project_id,
                    month,
                )

                successful += 1

                if successful % 100 == 0:

                    print(
                        f"[{index:,}/{total:,}] "
                        f"processed | "
                        f"successful={successful:,} | "
                        f"failed={failed:,}"
                    )

            except Exception as exc:

                db.rollback()

                failed += 1

                print(
                    f"[FAILED] "
                    f"{project_id}: {exc}"
                )

        print()
        print("=" * 60)
        print("BATCH COMPLETE")
        print("=" * 60)
        print(
            f"Successful : {successful:,}"
        )
        print(
            f"Failed     : {failed:,}"
        )
        print("=" * 60)

    finally:

        db.close()


if __name__ == "__main__":
    main()