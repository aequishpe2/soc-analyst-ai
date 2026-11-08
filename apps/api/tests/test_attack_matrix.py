import uuid

from test_analysis_api import prepare, start_analysis

from app.attack_matrix import catalog, matrix
from app.detection.engine import RULES


def finding(identifier, reference, severity="Medio"):
    return {
        "id": identifier,
        "attack_reference": reference,
        "severity": severity,
        "rule_id": "test",
    }


def test_official_catalog_and_empty_matrix():
    data = catalog()
    result = matrix([])
    assert data["release"] == "20.1"
    assert {r[3] for r in RULES.values() if r[3]} <= set(data["techniques"])
    assert len(result["tactics"]) == 15
    assert len({t["id"] for t in result["tactics"]}) == 15
    assert result["total_findings"] == result["mapped_findings"] == 0
    assert result["techniques"] == []
    assert all(t["techniques"] == [] for t in result["tactics"])
    assert all(t["url"].startswith("https://attack.mitre.org/") for t in result["tactics"])


def test_multiple_tactics_do_not_multiply_unique_finding_counts():
    result = matrix([finding("1", "T1078", "Alto"), finding("2", "T1078")])
    assert result["total_findings"] == result["mapped_findings"] == 2
    assert len(result["techniques"]) == 1
    technique = result["techniques"][0]
    assert technique["count"] == 2
    assert technique["severity"] == "Alto"
    assert technique["by_severity"] == {"Crítico": 0, "Alto": 1, "Medio": 1, "Bajo": 0}
    columns = [t for t in result["tactics"] if t["techniques"]]
    assert len(columns) == len(catalog()["techniques"]["T1078"]["tactics"])
    assert all(t["techniques"][0]["finding_ids"] == ["1", "2"] for t in columns)


def test_unknown_missing_and_retired_references_are_not_assigned_new_techniques():
    result = matrix([finding("1", None), finding("2", "T9999"), finding("3", "T1562")])
    assert result["mapped_findings"] == 0
    assert result["unmapped_findings"] == 3
    assert result["techniques"] == []
    assert result["unmapped_reasons"] == {
        "missing_reference": 1,
        "unknown_reference": 1,
        "inactive_reference": 1,
    }


def test_matrix_api_shared_filters_pagination_and_evidence(client):
    case_id, _, run, _ = prepare(client)
    analysis = start_analysis(client, case_id, [run])
    path = f"/api/v1/analyses/{analysis['id']}"
    data = client.get(path + "/attack-matrix?limit=1").json()
    assert data["total_findings"] == 2
    assert data["mapped_findings"] == 2
    technique = next(t for t in data["techniques"] if t["id"] == "T1110")
    query = "?technique_id=T1110&severity=Alto"
    subset = client.get(path + "/attack-matrix" + query).json()
    findings = client.get(path + "/findings" + query).json()
    dashboard = client.get(path + "/dashboard" + query).json()
    assert subset["total_findings"] == findings["total"] == 1
    assert dashboard["total"] == 1
    assert findings["items"][0]["id"] in technique["finding_ids"]
    evidence = client.get(path + f"/findings/{findings['items'][0]['id']}/evidence").json()
    assert evidence["total"] >= 1
    assert client.get(path + "/attack-matrix?technique_id=T9999").json()["total_findings"] == 0
    assert client.get(path + "/attack-matrix?technique_id=invalid").status_code == 422
    assert client.get(path + "/attack-matrix?severity=Crítico").json()["total_findings"] == 0
    assert client.get(path + "/attack-matrix?user=not-present").json()["total_findings"] == 0


def test_matrix_scope_isolation_and_report_snapshot(client):
    first_case, _, first_run, _ = prepare(client)
    first = start_analysis(client, first_case, [first_run])
    second_case, _, second_run, _ = prepare(client)
    second = start_analysis(client, second_case, [second_run])
    first_path = f"/api/v1/analyses/{first['id']}"
    data = client.get(first_path + "/attack-matrix").json()
    other = client.get(f"/api/v1/analyses/{second['id']}/attack-matrix").json()
    ids = {f for t in data["techniques"] for f in t["finding_ids"]}
    other_ids = {f for t in other["techniques"] for f in t["finding_ids"]}
    assert ids.isdisjoint(other_ids)
    report = client.get(first_path + "/report").json()
    assert report["attack_matrix"] == data
    assert client.get(f"/api/v1/analyses/{uuid.uuid4()}/attack-matrix").status_code == 404
    with client.app.state.engine.begin() as connection:
        from sqlalchemy import update

        from app.models import Analysis

        connection.execute(
            update(Analysis).where(Analysis.id == first["id"]).values(status="failed")
        )
    assert client.get(first_path + "/attack-matrix").status_code == 409
