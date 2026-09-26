"""Run inside the new image/container; verifies assets, schema and real API cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen
from sqlalchemy import inspect
from database import engine

ASSETS = ("early-warnings.html", "js/api.js", "js/warning-ui.js", "js/early-warnings.js", "js/project-warnings.js")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "frontend"
    assert os.environ.get("PAIMANA_REVISION") == args.revision, "Image revision mismatch"
    columns = {c["name"] for c in inspect(engine).get_columns("alerts")}
    assert {"status", "status_updated_at", "review_note", "evidence_updated_at"} <= columns, "Migration missing"
    for name in ASSETS:
        local = (root / name).read_bytes()
        with urlopen(args.base_url + "/" + name, timeout=20) as response:
            remote = response.read()
            assert response.status == 200 and hashlib.sha256(remote).digest() == hashlib.sha256(local).digest(), f"Stale asset: {name}"
        print("Asset verified:", name)
    with urlopen(args.base_url + "/health", timeout=20) as response:
        health = json.load(response)
    assert health.get("revision") == args.revision and health.get("early_warning_contract") == 3
    with urlopen(args.base_url + "/api/v1/alerts/summary", timeout=20) as response:
        summary = json.load(response)
    assert summary["new"] <= summary["total_cases"] <= summary["total_projects"]
    assert sum(summary[s] for s in ("new", "acknowledged", "under_review", "resolved", "dismissed")) == summary["total_cases"]
    with urlopen(args.base_url + "/api/v1/alerts/cases?status=NEW", timeout=20) as response:
        cases = json.load(response)
    assert len({c["project_id"] for c in cases}) == len(cases)
    assert all(c["workflow_status"] == "NEW" for c in cases)
    with urlopen(args.base_url + "/api/v1/alerts/workspace?status=NEW", timeout=20) as response:
        workspace = json.load(response)
    assert workspace['summary']['total_cases'] == summary['total_cases']
    assert all(c['dominant_classification'] in c['contributing_classifications'] for c in workspace['cases'])
    print(json.dumps(summary, indent=2))
    print("Deployment verified:", args.revision)


if __name__ == "__main__":
    main()
