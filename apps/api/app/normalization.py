import ipaddress
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

FIELDS = (
    "timestamp",
    "user",
    "source_ip",
    "destination_ip",
    "source_host",
    "destination_host",
    "event_type",
    "result",
    "process",
    "command",
    "provider_event_id",
    "event_provider",
    "logon_type",
    "target_group",
    "target_user",
    "privilege",
)
DATE_FORMATS = ("iso8601", "dmy", "mdy", "epoch_seconds", "epoch_milliseconds")


def timestamp(value, date_format, zone):
    if not value or not value.strip():
        return None, "timestamp_missing"
    value = value.strip()
    try:
        if date_format.startswith("epoch_"):
            number = float(value)
            parsed = datetime.fromtimestamp(
                number / (1000 if date_format.endswith("milliseconds") else 1), UTC
            )
        elif date_format == "iso8601":
            if not ("T" in value or " " in value) or ":" not in value:
                raise ValueError("Timestamp requires date and time")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            fmt = "%d/%m/%Y %H:%M:%S" if date_format == "dmy" else "%m/%d/%Y %H:%M:%S"
            parsed = datetime.strptime(value, fmt)
        if parsed.tzinfo is None:
            timezone = ZoneInfo(zone)
            candidates = [parsed.replace(tzinfo=timezone, fold=fold) for fold in (0, 1)]
            valid = [
                c
                for c in candidates
                if c.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) == parsed
            ]
            if not valid:
                return None, "timestamp_dst_nonexistent"
            if len({c.utcoffset() for c in valid}) > 1:
                return None, "timestamp_dst_ambiguous"
            parsed = valid[0]
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z"), None
    except (ValueError, OverflowError, OSError):
        return None, "timestamp_invalid"


def normalize(row, mapping, date_format, zone):
    values = row["values"]
    normalized = {field: None for field in FIELDS}
    warnings = []
    for field, column in mapping.items():
        index = int(column[1:])
        if index in row["formulas"]:
            warnings.append(f"formula_excluded:{field}")
            continue
        normalized[field] = values[index] if index < len(values) else None
    utc, warning = timestamp(normalized["timestamp"], date_format, zone)
    if warning:
        warnings.append(warning)
    for field in ("source_ip", "destination_ip"):
        if normalized[field]:
            try:
                ipaddress.ip_address(normalized[field].strip())
            except ValueError:
                warnings.append(f"invalid_ip:{field}")
    if row["formulas"]:
        warnings.append("formula_present")
    return normalized, utc, warnings
