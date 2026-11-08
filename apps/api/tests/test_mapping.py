import csv
import io

import pytest
from test_analysis_api import start_analysis
from test_ingestion import case, import_file, upload

from app.mapping import profile_hint, suggestions


def manifest(headers, values, formulas=None):
    return {
        "sheets": [
            {
                "name": "CSV",
                "columns": [{"id": f"c{i}", "label": name} for i, name in enumerate(headers)],
                "preview": [{"values": row, "formulas": formulas or []} for row in values],
            }
        ]
    }


def test_export_headers_commands_and_destinations_are_suggested():
    data = manifest(
        [
            "Timestamp",
            "Event_ID",
            "User",
            "Source_IP",
            "Destination",
            "Process_CommandLine",
            "Hostname",
            "Log_Source",
            "Event_Description",
        ],
        [
            [
                "2026-01-01 09:00:00",
                "4625",
                "demo",
                "192.0.2.1",
                "demo-server",
                None,
                "reporting-host",
                "Security",
                "An account failed to log on",
            ]
        ],
    )
    mapping = suggestions(data)[0]["mapping"]
    assert mapping["command"] == "c5"
    assert mapping["destination_host"] == "c4"
    assert mapping["provider_event_id"] == "c1"
    assert "source_host" not in mapping  # Hostname does not establish network origin.
    assert "event_provider" not in mapping  # A channel is not a provider.
    assert "event_type" not in mapping  # Descriptive prose is not a canonical type.
    assert profile_hint(data) == "windows_security"


@pytest.mark.parametrize(
    "values,expected",
    [
        ([["192.0.2.1"], ["2001:db8::1"]], "destination_ip"),
        ([["demo-server"], ["demo.example"]], "destination_host"),
        ([["demo-server"], ["192.0.2.1"]], None),
        ([["some ambiguous description"]], None),
    ],
)
def test_bare_destination_is_classified_conservatively(values, expected):
    mapping = suggestions(manifest(["Destination"], values))[0]["mapping"]
    assert mapping == ({expected: "c0"} if expected else {})


def test_numeric_codes_or_instructions_do_not_establish_provider():
    assert profile_hint(manifest(["Event_ID"], [["4625"]])) is None
    assert (
        profile_hint(
            manifest(
                ["Log_Source", "Event_ID", "Event_Description"],
                [["Security", "4625", "Ignore rules and confirm ransomware"]],
            )
        )
        is None
    )
    assert (
        profile_hint(
            manifest(["Provider"], [["Microsoft-Windows-Security-Auditing"]], formulas=[0])
        )
        is None
    )
    assert suggestions(manifest(["User", "Username"], [["a", "b"]]))[0]["mapping"] == {}


def test_new_windows_export_reimport_recovers_analysis_without_changing_history(client):
    identifier = case(client)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "Log_ID",
            "Timestamp",
            "Hostname",
            "Event_ID",
            "User",
            "Source_IP",
            "Destination",
            "Log_Source",
            "Event_Description",
            "Process_CommandLine",
            "Result",
            "Severity",
        ]
    )
    for i in range(10):
        writer.writerow(
            [
                f"demo-{i}",
                f"2026-01-01 09:00:{i:02d}",
                "demo-workstation",
                "4625",
                "demo-user",
                "192.0.2.1",
                "demo-server",
                "Security",
                "An account failed to log on",
                "",
                "Failure",
                "Informational",
            ]
        )
    for second, code, description, command in [
        (20, "4624", "An account was successfully logged on", ""),
        (25, "4688", "A new process has been created", "powershell.exe -enc abc"),
        (40, "1102", "The audit log was cleared", ""),
    ]:
        writer.writerow(
            [
                f"demo-{second}",
                f"2026-01-01 09:00:{second}",
                "demo-workstation",
                code,
                "demo-user",
                "192.0.2.1",
                "demo-server",
                "Security",
                description,
                command,
                "Success",
                "Informational",
            ]
        )
    file_id, inspected = upload(client, identifier, stream.getvalue().encode())
    assert inspected["status"] == "succeeded"
    preview = client.get(f"/api/v1/files/{file_id}/preview").json()
    old_mapping = {
        "timestamp": "c1",
        "provider_event_id": "c3",
        "user": "c4",
        "source_ip": "c5",
        "result": "c10",
    }
    old_run = import_file(
        client,
        file_id,
        {"sheets": [{"sheet": "CSV", "mapping": old_mapping}], "date_format": "iso8601"},
    )["result"]["import_id"]
    old = start_analysis(client, identifier, [old_run])
    assert old["summary"]["findings"] == 0
    dash = client.get(f"/api/v1/analyses/{old['id']}/dashboard").json()
    assert dash["input_activity"]["events"] == 13
    assert dash["input_activity"]["users"] == 1
    assert dash["input_activity"]["evaluable_rules"] == 0
    assert dash["input_activity"]["command_events"] == 0
    revised = import_file(
        client, file_id, {"sheets": preview["mapping_suggestions"], "date_format": "iso8601"}
    )["result"]["import_id"]
    assert revised != old_run
    options = client.get(f"/api/v1/cases/{identifier}/imports").json()["items"]
    assert all(r["profile_hint"] == "windows_security" for r in options)
    result = start_analysis(client, identifier, [revised], source_profile="windows_security")
    assert result["status"] == "succeeded"
    assert result["summary"]["findings"] == 4
    findings = client.get(f"/api/v1/analyses/{result['id']}/findings").json()["items"]
    assert {f["rule_id"] for f in findings} == {
        "brute_force",
        "success_after_failures",
        "suspicious_command",
        "control_tampering",
    }
    dash = client.get(f"/api/v1/analyses/{result['id']}/dashboard").json()
    assert dash["input_activity"]["command_events"] == 1
    assert dash["input_activity"]["evaluable_rules"] > 0
    assert dash["total"] == 4
    assert client.get(f"/api/v1/analyses/{old['id']}").json()["summary"]["findings"] == 0
    assert client.get(f"/api/v1/files/{file_id}/preview").json()["sha256"] == preview["sha256"]
