import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_analysis_api import prepare, start_analysis

from app.models import Analysis, Event, Finding, FindingEvidence


def ready(client):
    case_id, _, run, _ = prepare(client, extra_duplicate=True)
    result = start_analysis(client, case_id, [run])
    assert result["status"] == "succeeded"
    return f"/api/v1/analyses/{result['id']}", result


def assert_consistent(client, base, query=""):
    response = client.get(f"{base}/dashboard?{query}")
    assert response.status_code == 200, response.text
    data = response.json()
    findings = client.get(f"{base}/findings?limit=100&{query}").json()
    assert data["total"] == findings["total"]
    assert data["total"] == sum(i["count"] for i in data["by_severity"])
    assert data["total"] == sum(i["count"] for i in data["by_rule"])
    assert data["total"] == sum(i["count"] for i in data["timeline"]) + data["undated"]
    return data


def test_complete_dashboard_agrees_with_analysis_and_deduplicates_evidence(client):
    base, result = ready(client)
    data = assert_consistent(client, base)
    assert data["total"] == result["summary"]["findings"] == 2
    assert data["groups"] == 1
    assert data["evidence_events"] == 11
    assert data["top_users"] == [{"value": "alice", "count": 2}]
    assert data["top_hosts"] == [{"value": "server-1", "count": 2}]
    assert data["timeline"] == [{"value": "2026-11-02", "count": 2}]
    assert data["undated"] == 0


@pytest.mark.parametrize(
    "query,expected",
    [
        ("severity=Alto", 1),
        ("rule_id=brute_force", 1),
        ("user=alice", 2),
        ("user=ali", 0),
        ("host=server-1", 2),
        ("host=192.0.2.10", 0),
        ("user=alice&host=server-1&severity=Alto", 1),
        ("date_from=2026-11-02&date_to=2026-11-02", 2),
        ("date_from=2026-11-03", 0),
        ("date_to=2026-11-01", 0),
    ],
)
def test_identical_filters_for_charts_and_findings(client, query, expected):
    base, _ = ready(client)
    data = assert_consistent(client, base, query)
    assert data["total"] == expected
    if not expected:
        assert data["evidence_events"] == data["groups"] == 0
        assert data["top_users"] == data["top_hosts"] == []


def test_aggregates_include_other_pages_and_undated_findings(client):
    base, result = ready(client)
    with Session(client.app.state.engine) as db:
        source = db.scalar(select(Finding).where(Finding.analysis_id == result["id"]))
        refs = db.scalars(
            select(FindingEvidence.event_id).where(FindingEvidence.finding_id == source.id)
        ).all()
        # Synthetic aggregation fixture: additional findings reuse linked evidence.
        for i in range(35):
            identifier = str(uuid.uuid4())
            db.add(
                Finding(
                    id=identifier,
                    analysis_id=source.analysis_id,
                    group_id=source.group_id,
                    rule_id=source.rule_id,
                    severity=source.severity,
                    confidence=source.confidence,
                    payload={
                        **source.payload,
                        "start": None if i == 0 else source.payload["start"],
                    },
                )
            )
            db.flush()
            db.add_all(
                [FindingEvidence(finding_id=identifier, event_id=e, role="observed") for e in refs]
            )
        db.commit()
    first = client.get(f"{base}/findings").json()
    assert len(first["items"]) == 20 and first["total"] == 37
    data = assert_consistent(client, base)
    assert data["total"] == 37
    assert data["evidence_events"] == 11
    assert data["undated"] == 1
    assert assert_consistent(client, base, "date_from=2026-11-02")["total"] == 36


def test_entities_must_match_same_evidence_event(client):
    base, result = ready(client)
    with Session(client.app.state.engine) as db:
        event = db.scalar(
            select(Event)
            .join(FindingEvidence)
            .join(Finding)
            .where(Finding.analysis_id == result["id"], Finding.rule_id == "brute_force")
        )
        event.normalized = {**event.normalized, "user": "bob", "destination_host": "server-2"}
        db.commit()
    assert assert_consistent(client, base, "user=bob&host=server-1")["total"] == 0
    assert assert_consistent(client, base, "user=bob&host=server-2")["total"] == 2


@pytest.mark.parametrize(
    "query",
    [
        "severity=Invalid",
        "rule_id=invalid",
        "date_from=invalid",
        "date_from=2026-11-03&date_to=2026-11-02",
        "user=",
    ],
)
def test_invalid_filters_fail_explicitly(client, query):
    base, _ = ready(client)
    assert client.get(f"{base}/dashboard?{query}").status_code == 422
    assert client.get(f"{base}/findings?{query}").status_code == 422


def test_foreign_group_missing_analysis_and_incomplete_analysis(client):
    base, result = ready(client)
    other, _ = ready(client)
    group = client.get(f"{other}/groups").json()["items"][0]["id"]
    assert client.get(f"{base}/dashboard?group_id={group}").status_code == 404
    assert client.get(f"/api/v1/analyses/{uuid.uuid4()}/dashboard").status_code == 404
    with Session(client.app.state.engine) as db:
        db.get(Analysis, result["id"]).status = "failed"
        db.commit()
    assert client.get(f"{base}/dashboard").status_code == 409


def test_entity_summary_excludes_missing_values_and_deduplicates_roles(client):
    base, result = ready(client)
    with Session(client.app.state.engine) as db:
        for event in db.scalars(select(Event).where(Event.case_id == result["case_id"])):
            event.normalized = {
                **event.normalized,
                "source_host": " server-1 ",
                "target_user": "alice",
            }
        db.commit()
    data = assert_consistent(client, base)
    assert data["top_users"] == [{"value": "alice", "count": 2}]
    assert data["top_hosts"] == [{"value": "server-1", "count": 2}]
