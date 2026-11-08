"""Exact source semantics; no arbitrary log text is interpreted as instructions."""

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime

from app.fingerprints import config_digest
from app.normalization import FIELDS

AUTH = {"login", "logon", "authentication", "auth", "user_login", "inicio_sesion"}
OTHER = {
    "process",
    "process_create",
    "process_start",
    "command_execution",
    "file_access",
    "network_connection",
    "dns_query",
}
REMOTE = {"remote_login", "remote_logon", "ssh_login", "rdp_login", "smb_login", "winrm_login"}
FAIL_TYPES = {
    "login_failed",
    "login_failure",
    "failed_login",
    "failed_logon",
    "authentication_failure",
    "auth_fail",
}
SUCCESS_TYPES = {"login_success", "authentication_success", "successful_logon", "auth_success"}
GRANTS = {
    "privileged_group_member_added",
    "group_member_added",
    "privileged_role_assigned",
    "privilege_elevated",
    "privilege_escalation",
}
CONTROLS = {
    "audit_log_cleared",
    "security_log_cleared",
    "security_control_disabled",
    "edr_disabled",
    "audit_disabled",
}
SUCCESS = {"success", "successful", "succeeded", "exito", "éxito", "ok", "allowed", "permitido"}
FAILURE = {"failure", "failed", "fail", "denied", "denegado", "error"}
MISSING = {"", "-", "n/a", "null", "none", "unknown", "(null)"}


def identifier(value, max_length=256, folded=False):
    text = (value or "").strip()
    if len(text) > max_length or text.casefold() in MISSING:
        return None
    return text.casefold() if folded else text


def ip(value):
    try:
        address = ipaddress.ip_address((value or "").strip())
        if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
            return None
        return str(address)
    except ValueError:
        return None


def token(value):
    return (value or "").strip().casefold().replace(" ", "_").replace("-", "_")


@dataclass
class Observation:
    id: str
    values: dict
    timestamp: datetime | None
    user: str | None
    source: str | None
    destination: str | None
    outcome: str | None
    kind: str | None
    remote: bool
    conflict: bool
    users: set
    assets: set


def interpret(row, config):
    values = row["normalized"]
    raw_result = (values.get("result") or "").strip().casefold()
    outcome = "success" if raw_result in SUCCESS else "failure" if raw_result in FAILURE else None
    declared = token(values.get("event_type"))
    kind = (
        "auth"
        if declared in AUTH | REMOTE | FAIL_TYPES | SUCCESS_TYPES
        else "grant"
        if declared in GRANTS
        else "control"
        if declared in CONTROLS
        else "other"
        if declared in OTHER
        else None
    )
    expected = (
        "failure"
        if declared in FAIL_TYPES
        else "success"
        if declared in SUCCESS_TYPES | GRANTS | CONTROLS
        else None
    )
    remote = declared in REMOTE
    provider = (values.get("event_provider") or "").strip().casefold()
    windows = (
        config.source_profile == "windows_security"
        or provider == "microsoft-windows-security-auditing"
    )
    code = (values.get("provider_event_id") or "").strip()
    # No interpretation of numeric IDs without an explicit provider/profile.
    native = (
        {
            "4624": ("auth", "success"),
            "4625": ("auth", "failure"),
            "4728": ("grant", "success"),
            "4732": ("grant", "success"),
            "4756": ("grant", "success"),
            "1102": ("control", "success"),
            "4672": ("other", None),
            "4719": ("other", None),
        }.get(code)
        if windows
        else None
    )
    conflict = False
    if native:
        native_kind, native_outcome = native
        conflict = bool(kind and kind != native_kind or expected and expected != native_outcome)
        kind, expected = native_kind, native_outcome
        remote = kind == "auth" and (values.get("logon_type") or "").strip() in {"3", "10"}
    if expected:
        conflict |= outcome is not None and outcome != expected
        if outcome is None:
            outcome = expected
    if conflict:
        kind, outcome = None, None
    user = identifier(values.get("user"))
    origin_ip = ip(values.get("source_ip"))
    origin_host = identifier(values.get("source_host"), 253, True)
    dest_host = identifier(values.get("destination_host"), 253, True)
    dest_ip = ip(values.get("destination_ip"))
    source = "ip:" + origin_ip if origin_ip else "host:" + origin_host if origin_host else None
    destination = "host:" + dest_host if dest_host else "ip:" + dest_ip if dest_ip else None
    assets = {
        prefix + value
        for prefix, value in (
            ("host:", origin_host),
            ("host:", dest_host),
            ("ip:", origin_ip),
            ("ip:", dest_ip),
        )
        if value
    }
    users = {v for v in (user, identifier(values.get("target_user"))) if v}
    when = (
        datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
        if row["timestamp_utc"]
        else None
    )
    return Observation(
        row["id"],
        values,
        when,
        user,
        source,
        destination,
        outcome,
        kind,
        remote,
        conflict,
        users,
        assets,
    )


def duplicate_fingerprint(row):
    return config_digest(
        {
            "timestamp_utc": row["timestamp_utc"],
            "raw_invalid_time": row["normalized"].get("timestamp")
            if row["timestamp_utc"] is None
            else None,
            "normalized": {key: row["normalized"].get(key) for key in FIELDS if key != "timestamp"},
        }
    )


def privileged_target(observation, config):
    group = identifier(observation.values.get("target_group"))
    privilege = identifier(observation.values.get("privilege"))
    named = {v.casefold() for v in config.privileged_groups}
    if group and (
        group.casefold() in named
        or group.casefold() == "s-1-5-32-544"
        or re.fullmatch(r"S-1-5-21-\d+-\d+-\d+-(512|518|519)", group, re.I)
    ):
        return {"field": "target_group", "value": group}
    if privilege and privilege.casefold() in {"root", "administrator", "admin", "system", "sudo"}:
        return {"field": "privilege", "value": privilege}
    return None
