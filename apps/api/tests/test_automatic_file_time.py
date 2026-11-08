import pytest
from test_analysis_api import start_analysis
from test_ingestion import case, import_file, upload

from app.normalization import timestamp


def test_no_clock_configuration_is_required_or_advertised(client):
    created = client.post("/api/v1/cases", json={"title": "Cliente sin configuración horaria"})
    assert created.status_code == 201
    assert "timezone" not in created.json()
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("CaseInput", "ImportInput", "BusinessHours"):
        assert "timezone" not in schema[name]["properties"]
        assert "timezone" not in schema[name].get("required", [])


@pytest.mark.parametrize("value", ["2026-10-25T02:30:00", "2026-03-29T02:30:00"])
def test_unqualified_times_are_preserved_without_assuming_a_location(value):
    assert timestamp(value, "iso8601") == (value, None)


def test_file_import_and_schedule_work_without_a_zone(client):
    identifier = case(client)
    data = (
        b"timestamp,user,source_ip,event_type,result\n"
        b"2026-11-02T20:30:00,ana,192.0.2.10,login,success\n"
    )
    file_id, inspected = upload(client, identifier, data)
    assert inspected["status"] == "succeeded"
    imported = import_file(
        client,
        file_id,
        {
            "sheets": [
                {
                    "sheet": "CSV",
                    "mapping": {
                        "timestamp": "c0",
                        "user": "c1",
                        "source_ip": "c2",
                        "event_type": "c3",
                        "result": "c4",
                    },
                }
            ],
            "date_format": "iso8601",
        },
    )
    run = imported["result"]["import_id"]
    result = client.get(f"/api/v1/cases/{identifier}/events?import_id={run}").json()["items"][0]
    assert result["timestamp"] == "2026-11-02T20:30:00"
    assert result["timestamp_utc"] is None
    analysis = start_analysis(
        client,
        identifier,
        [run],
        business_hours={"weekdays": [0, 1, 2, 3, 4], "start": "08:00", "end": "18:00"},
    )
    assert analysis["status"] == "succeeded", analysis
    assert analysis["summary"]["findings"] == 1
    finding = client.get(f"/api/v1/analyses/{analysis['id']}/findings").json()["items"][0]
    assert finding["rule_id"] == "outside_hours"
    assert finding["start"] == "2026-11-02T20:30:00"


@pytest.mark.parametrize(("suffix", "expected"), [("", 0), ("Z", 1)])
def test_separate_unqualified_file_clocks_are_not_silently_combined(client, suffix, expected):
    identifier = case(client)
    imports = []
    for batch in range(2):
        data = "timestamp,user,source_ip,event_type,result\n" + "".join(
            f"2026-11-02T09:00:{batch * 6 + i:02d}{suffix},ana,192.0.2.10,login,failure\n"
            for i in range(6)
        )
        file_id, job = upload(client, identifier, data.encode())
        assert job["status"] == "succeeded"
        result = import_file(
            client,
            file_id,
            {
                "sheets": [
                    {
                        "sheet": "CSV",
                        "mapping": {
                            "timestamp": "c0",
                            "user": "c1",
                            "source_ip": "c2",
                            "event_type": "c3",
                            "result": "c4",
                        },
                    }
                ],
                "date_format": "iso8601",
            },
        )
        imports.append(result["result"]["import_id"])
    analysis = start_analysis(client, identifier, imports)
    assert analysis["status"] == "succeeded", analysis
    rows = client.get(f"/api/v1/analyses/{analysis['id']}/findings?rule_id=brute_force").json()
    assert rows["total"] == expected
    assert analysis["summary"]["duplicate_events"] == 0
