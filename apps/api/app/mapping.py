"""Conservative header suggestions. Ambiguous fields remain unmapped for review."""

import ipaddress
import re

from app.normalization import FIELDS

ALIASES = {
    "timestamp": ["fecha", "date", "datetime", "time", "fecha_hora", "@timestamp"],
    "user": ["usuario", "username", "account"],
    "source_ip": ["src_ip", "ip_origen"],
    "destination_ip": ["dst_ip", "ip_destino"],
    "source_host": ["src_host"],
    "destination_host": ["dst_host"],
    "event_type": ["evento", "event"],
    "result": ["resultado", "outcome", "status"],
    "process": ["proceso", "process_name"],
    "command": ["comando", "commandline", "command_line", "process_commandline"],
    "provider_event_id": ["event_id", "eventid"],
    "event_provider": ["provider", "providername"],
    "logon_type": ["logontype"],
    "target_group": ["targetgroup", "groupname", "targetgroupname"],
    "target_user": ["targetusername", "membername"],
    "privilege": ["privileges", "role"],
}


def header(value):
    return re.sub(r"[\s_.-]+", "", value.strip().casefold())


def suggestions(manifest):
    sheets = []
    for sheet in (manifest or {}).get("sheets", []):
        mapping = {}
        used = set()
        for field in FIELDS:
            names = {header(v) for v in [field, *ALIASES.get(field, [])]}
            matches = [c for c in sheet["columns"] if header(c["label"]) in names]
            if len(matches) == 1 and matches[0]["id"] not in used:
                mapping[field] = matches[0]["id"]
                used.add(matches[0]["id"])
        # A bare Destination may hold hosts or IPs. Do not confuse mixed values.
        destinations = [c for c in sheet["columns"] if header(c["label"]) == "destination"]
        if len(destinations) == 1:
            column = destinations[0]["id"]
            index = int(column[1:])
            values = [
                r["values"][index].strip()
                for r in sheet.get("preview", [])
                if index < len(r["values"])
                and r["values"][index]
                and index not in r.get("formulas", [])
            ]
            kinds = set()
            for value in values:
                try:
                    ipaddress.ip_address(value)
                    kinds.add("destination_ip")
                except ValueError:
                    kinds.add("destination_host" if re.fullmatch(r"[\w.-]+", value) else "unknown")
            if len(kinds) == 1 and "unknown" not in kinds:
                field = kinds.pop()
                if field not in mapping:
                    mapping[field] = column
        sheets.append({"sheet": sheet["name"], "mapping": mapping})
    return sheets


def profile_hint(manifest):
    # Suggest a profile only from explicit provider or a known Windows export schema
    # with matching channel + event ID + official description. Numeric IDs alone do not suffice.
    descriptions = {
        "4625": "an account failed to log on",
        "4624": "an account was successfully logged on",
        "4688": "a new process has been created",
        "1102": "the audit log was cleared",
    }
    for sheet in (manifest or {}).get("sheets", []):
        columns = {header(c["label"]): int(c["id"][1:]) for c in sheet["columns"]}
        required = {"logsource", "eventid", "eventdescription"}
        for row in sheet.get("preview", []):
            values = row["values"]

            def cell(name, columns=columns, values=values, row=row):
                index = columns.get(name)
                return (
                    (values[index] or "").strip().casefold()
                    if (
                        index is not None
                        and index < len(values)
                        and index not in row.get("formulas", [])
                    )
                    else ""
                )

            if any(
                cell(name) == "microsoft-windows-security-auditing"
                for name in ("eventprovider", "provider", "providername")
            ):
                return "windows_security"
            if (
                required <= columns.keys()
                and cell("logsource") == "security"
                and (descriptions.get(cell("eventid")) == cell("eventdescription").rstrip("."))
            ):
                return "windows_security"
    return None
