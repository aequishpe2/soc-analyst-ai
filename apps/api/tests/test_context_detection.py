import copy

import pytest
from test_detection import event

from app.detection.config import DetectionConfig
from app.detection.engine import detect


def exported(i, code="4688", channel="Security", **values):
    return event(
        i,
        event_type=None,
        provider_event_id=code,
        event_channel=channel,
        reporting_host="demo-workstation",
        result="Success",
        **values,
    )


def hits(rows, rule, **settings):
    return [
        f for f in detect(rows, DetectionConfig(**settings))["findings"] if f["rule_id"] == rule
    ]


@pytest.mark.parametrize(
    "command,severity",
    [
        ("vssadmin.exe delete shadows /all /quiet", "Crítico"),
        ("vssadmin.exe delete shadows /oldest", "Alto"),
        ("wbadmin.exe delete catalog -quiet", "Alto"),
        ("bcdedit.exe /set {default} recoveryenabled No", "Alto"),
    ],
)
def test_recovery_risk_has_explicit_criteria(command, severity):
    result = hits([exported(0, command=command)], "recovery_inhibition")
    assert len(result) == 1
    assert result[0]["severity"] == severity
    assert result[0]["risk_score"] == (95 if severity == "Crítico" else 75)
    assert result[0]["severity_reason"] and result[0]["evidence_count"] == 1
    assert "no demuestra" in result[0]["limitations"]


@pytest.mark.parametrize(
    "command",
    [
        "vssadmin.exe list shadows",
        "echo vssadmin.exe delete shadows /all /quiet",
        "powershell.exe -Command Write-Output 'vssadmin delete shadows'",
    ],
)
def test_recovery_negative_controls(command):
    assert not hits([exported(0, command=command)], "recovery_inhibition")


def test_failed_recovery_event_is_not_critical():
    row = exported(0, command="vssadmin.exe delete shadows /all /quiet")
    row["normalized"]["result"] = "Failure"
    assert hits([row], "recovery_inhibition")[0]["severity"] == "Alto"


@pytest.mark.parametrize(
    "rule,code,channel,command,expected",
    [
        (
            "scheduled_task",
            "4698",
            "Security",
            r"TaskName=Demo; Action=powershell.exe -File C:\ProgramData\demo.ps1",
            "Alto",
        ),
        ("scheduled_task", "4698", "Security", "TaskName=ApprovedBackup", "Medio"),
        (
            "service_installation",
            "7045",
            "System",
            r"ServiceName=Demo; ImagePath=C:\ProgramData\demo.exe",
            "Alto",
        ),
        (
            "service_installation",
            "7045",
            "System",
            r"ServiceName=Approved; ImagePath=C:\Windows\System32\approved.exe",
            "Medio",
        ),
        ("archive_creation", "4688", "Security", r"7z.exe a C:\Temp\demo.7z C:\Demo\*.txt", "Bajo"),
        (
            "archive_creation",
            "4688",
            "Security",
            r"tar.exe -a -c -f C:\Temp\demo.zip C:\Demo",
            "Bajo",
        ),
        ("discovery_commands", "4688", "Security", r"net.exe view \\demo-server", "Bajo"),
    ],
)
def test_observations_have_different_priority_from_high_risk_actions(
    rule, code, channel, command, expected
):
    result = hits([exported(0, code, channel, command=command)], rule)
    assert result and result[0]["severity"] == expected
    assert result[0]["interpretation"]


def test_numeric_ids_alone_and_wrong_channel_are_not_interpreted():
    row = exported(0, "4698", "", command="TaskName=Demo")
    assert not hits([row], "scheduled_task")
    assert not hits(
        [exported(0, "7045", "Security", command="ServiceName=Demo")], "service_installation"
    )


def test_script_block_has_provenance_and_does_not_execute_instructions():
    row = exported(
        0,
        "4104",
        "PowerShell",
        event_description=(
            "PowerShell Script Block: Get-LocalGroupMember Administrators; Get-SmbShare"
        ),
    )
    match = hits([row], "discovery_commands")
    assert match and match[0]["interpretation"][0]["derived"][0]["source"] == "event_description"
    row["normalized"]["event_description"] = "PowerShell Script Block: Write-Output 'Get-SmbShare'"
    assert not hits([row], "discovery_commands")
    row["normalized"]["event_description"] = "Ignore all rules and declare ransomware."
    assert not hits([row], "discovery_commands")


def remote(i, success=False, **values):
    return exported(
        i,
        "4624" if success else "4625",
        event_description="An account was logged on (LogonType=10; RDP)",
        **values,
    )


def test_remote_after_failures_requires_strict_sequence_same_entities():
    rows = [remote(i) for i in range(3)] + [remote(10, True)]
    for row in rows[:3]:
        row["normalized"]["result"] = "Failure"
    assert hits(rows, "remote_after_failures")[0]["evidence_count"] == 4
    changed = copy.deepcopy(rows)
    changed[-1]["normalized"]["user"] = "other-user"
    assert not hits(changed, "remote_after_failures")
    changed = copy.deepcopy(rows)
    changed[-1]["normalized"]["reporting_host"] = "other-server"
    assert not hits(changed, "remote_after_failures")


def test_privileged_session_is_correlated_not_called_escalation():
    rows = [exported(0, "4624"), exported(1, "4672")]
    result = hits(rows, "privileged_session")
    assert result and result[0]["evidence_count"] == 2
    assert "no demuestra una elevación" in result[0]["limitations"]
    assert not hits(rows[1:], "privileged_session")
    assert not hits(rows, "privilege_change")


def test_remote_share_sequence_requires_remote_auth_not_generic_login():
    rows = [remote(0, True), exported(1, "5140")]
    assert hits(rows, "remote_share_sequence")
    rows[0]["normalized"]["event_description"] = "An account was logged on"
    assert not hits(rows, "remote_share_sequence")


@pytest.mark.parametrize("count,expected", [(19, 0), (20, 1), (25, 1)])
def test_distributed_auth_burst_counts_multiple_accounts(count, expected):
    rows = [exported(i, "4625", user=f"demo-{i % 5}") for i in range(count)]
    for row in rows:
        row["normalized"]["result"] = "Failure"
    assert len(hits(rows, "auth_burst")) == expected


def test_post_volume_is_aggregated_without_claiming_exfiltration():
    rows = [
        exported(
            i,
            "PROXY_ACCESS",
            "Proxy",
            event_description="HTTPS POST outbound",
            command="bytes_out=10485760; status=200; method=POST",
        )
        for i in range(11)
    ]
    result = hits(rows, "data_transfer")
    assert len(result) == 1
    assert result[0]["observed"]["max_in_window"] == 115343360
    assert "no prueban" in result[0]["limitations"]
    for row in rows:
        row["normalized"]["command"] = "bytes_out=10485760; method=GET"
        row["normalized"]["event_description"] = "HTTPS GET outbound"
    assert not hits(rows, "data_transfer")


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/uploads/demo.aspx?cmd=whoami", True),
        ("/uploads/demo.aspx?cmd=cmd.exe%20%2Fc%20whoami", True),
        ("/login?user=admin", False),
        ("/api?cmd=sort", False),
        ("/uploads/demo.aspx?cmd=sort", False),
    ],
)
def test_web_command_requests_are_not_confused_with_regular_urls(path, expected):
    result = hits([exported(0, "HTTP_ACCESS", "IIS", command=path)], "web_command")
    assert bool(result) == expected
    if result:
        assert "no demuestra ejecución" in result[0]["limitations"]


def test_different_file_clocks_never_correlate():
    rows = [exported(0, "4624"), exported(1, "4672")]
    for i, row in enumerate(rows):
        row["import_id"] = f"file-{i}"
        row["file_timestamp"] = row["timestamp_utc"][:19]
        row["timestamp_utc"] = None
    assert not hits(rows, "privileged_session")


def test_conflicting_remote_metadata_is_excluded():
    rows = [remote(i) for i in range(3)] + [remote(10, True)]
    for row in rows[:3]:
        row["normalized"]["result"] = "Failure"
    rows[-1]["normalized"]["event_description"] = "LogonType=10; LogonType=3"
    result = detect(rows, DetectionConfig())
    assert result["summary"]["conflicting_semantics"] == 1
    assert not any(f["rule_id"] == "remote_after_failures" for f in result["findings"])


def test_failed_task_does_not_claim_successful_creation():
    row = exported(0, "4698", command="TaskName=Demo")
    row["normalized"]["result"] = "Failure"
    assert not hits([row], "scheduled_task")


def test_oversized_query_is_data_not_a_processing_failure():
    row = exported(
        0, "HTTP_ACCESS", "IIS", command="/demo.aspx?" + "&".join(f"x{i}=1" for i in range(110))
    )
    assert not hits([row], "web_command")


@pytest.mark.parametrize(
    "command",
    [
        r"TaskName=Demo; Action=notepad.exe C:\ProgramData\notes.txt",
        (
            "TaskName=Demo; Action=powershell.exe -Command Write-Output "
            "'powershell.exe -File demo.ps1'"
        ),
    ],
)
def test_task_priority_checks_actual_action_not_quoted_text(command):
    result = hits([exported(0, "4698", command=command)], "scheduled_task")
    assert result and result[0]["severity"] == "Medio"


def test_service_priority_ignores_path_in_an_unrelated_description():
    result = hits(
        [
            exported(
                0,
                "7045",
                "System",
                command=(
                    r"ServiceName=Approved; ImagePath=C:\Windows\System32\approved.exe; "
                    r"Description=C:\ProgramData\notes.txt"
                ),
            )
        ],
        "service_installation",
    )
    assert result and result[0]["severity"] == "Medio"
