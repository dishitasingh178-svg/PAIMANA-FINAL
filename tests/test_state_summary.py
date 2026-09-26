from datetime import date, timedelta

from api.models.models import Prediction, Project, ProjectUpdate
from api.routers.analytics import get_state_summary


def _prediction(pid, score, month="2024-01"):
    return Prediction(project_id=pid, report_month=month, cost_risk_probability=0.5,
                      schedule_risk_probability=0.5, cox_risk=1, cox_risk_probability=0.5,
                      composite_risk_score=score, risk_tier="X")


def test_state_summary_counts_costs_and_ongoing(db):
    future, past = date.today() + timedelta(days=90), date.today() - timedelta(days=90)
    db.add_all([
        Project(project_id="a", project_name="A", state="Maharashtra", original_cost_crore=100),
        Project(project_id="b", project_name="B", state="MAHARASHTRA ", original_cost_crore=50),
        Project(project_id="c", project_name="C", state=None, original_cost_crore=10),
        Project(project_id="d", project_name="D", state="Kerala", original_cost_crore=5),
    ])
    db.flush()
    db.add_all([
        # older update must be ignored in favour of the latest report month
        ProjectUpdate(project_id="a", report_month="2023-01", anticipated_cost_crore=999, anticipated_commissioning_date=past),
        ProjectUpdate(project_id="a", report_month="2024-01", anticipated_cost_crore=120, anticipated_commissioning_date=future),
        ProjectUpdate(project_id="b", report_month="2024-01", revised_cost_crore=60, revised_commissioning_date=past),
    ])
    db.add_all([_prediction("a", 80), _prediction("b", 55), _prediction("c", 10)])
    db.commit()

    body = get_state_summary(db=db)
    rows = {r["state"]: r for r in body["data"]}
    assert set(rows) == {"MAHARASHTRA", "KERALA", None}
    mh = rows["MAHARASHTRA"]
    assert (mh["projects"], mh["ongoing"]) == (2, 1)             # b's commissioning date has passed
    assert mh["original_cost_crore"] == 150
    assert mh["latest_cost_crore"] == 180                        # 120 (a, latest anticipated) + 60 (b, revised)
    assert mh["ongoing_latest_cost_crore"] == 120
    assert (mh["high_risk"], mh["critical"], mh["ongoing_high_risk"]) == (2, 1, 1)
    # no update -> ongoing (date not reported), cost falls back to the original sanction
    assert rows["KERALA"]["ongoing"] == 1 and rows["KERALA"]["latest_cost_crore"] == 5
    assert rows["KERALA"]["unscored"] == 1
    # blank state is kept separate, never reassigned
    assert rows[None]["projects"] == 1
    assert body["data"][-1]["state"] is None
    assert "commissioning" in body["ongoing_definition"]
