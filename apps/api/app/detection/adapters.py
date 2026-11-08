"""Bounded, source-specific interpretation with explicit derivation provenance."""

import ipaddress
import re
from urllib.parse import parse_qs, urlsplit

SECURITY = {
    "4624": ("auth", "success"),
    "4625": ("auth", "failure"),
    "4634": ("other", None),
    "4647": ("other", None),
    "4688": ("process", None),
    "4689": ("other", None),
    "4672": ("privileged_session", None),
    "4719": ("other", None),
    "4720": ("account", None),
    "4726": ("account", None),
    "4728": ("grant", "success"),
    "4732": ("grant", "success"),
    "4756": ("grant", "success"),
    "1102": ("control", "success"),
    "4663": ("file", None),
    "5140": ("share", None),
    "5145": ("share", None),
    "5156": ("network", None),
    "4698": ("task", "success"),
    "4702": ("task", "success"),
    "4697": ("service", "success"),
}


def adapt(values, profile):
    values = dict(values)
    code = (values.get("provider_event_id") or "").strip()
    channel = (values.get("event_channel") or "").strip().casefold()
    provider = (values.get("event_provider") or "").strip().casefold()
    description = values.get("event_description") or ""
    derived = []
    native = None
    adapter = None
    explicit = provider == "microsoft-windows-security-auditing"
    if explicit or profile == "windows_security" and channel in {"", "security"}:
        native, adapter = SECURITY.get(code), "windows_security"
    elif channel == "security" and profile == "auto":
        native, adapter = SECURITY.get(code), "windows_security_channel"
    if profile in {"auto", "windows_security"}:
        if channel == "system" and code in {"7045", "7036"}:
            native, adapter = (
                (("service", "success") if code == "7045" else ("other", None)),
                "windows_system",
            )
        elif (
            channel in {"powershell", "microsoft-windows-powershell/operational"} and code == "4104"
        ):
            native, adapter = ("process", None), "windows_powershell"
            prefix = "PowerShell Script Block:"
            if description.startswith(prefix):
                values["script_block"] = description[len(prefix) :].strip()
                derived.append(
                    {
                        "field": "script_block",
                        "source": "event_description",
                        "method": "4104_prefix",
                    }
                )
        elif channel == "proxy" and code == "PROXY_ACCESS":
            native, adapter = ("proxy", None), "proxy_export"
        elif channel == "iis" and code == "HTTP_ACCESS":
            native, adapter = ("web", None), "iis_export"
        elif channel == "firewall" and code == "5156" and profile == "auto":
            native, adapter = ("network", None), "firewall_export"
    if adapter and code in {"4624", "4625"} and native and native[0] == "auth":
        logon_types = set(
            re.findall(r"\bLogonType\s*=\s*(\d{1,2})(?=[\s;,)\]]|$)", description, re.I)
        )
        if len(logon_types) > 1:
            values["derivation_conflict"] = True
        if len(logon_types) == 1 and not values.get("logon_type"):
            values["logon_type"] = next(iter(logon_types))
            derived.append(
                {
                    "field": "logon_type",
                    "source": "event_description",
                    "method": "explicit_LogonType_key",
                }
            )
    dest = values.get("destination_host")
    if dest and not values.get("destination_ip"):
        try:
            values["destination_ip"] = str(ipaddress.ip_address(dest.strip()))
            values["destination_host"] = None
            derived.append(
                {"field": "destination_ip", "source": "destination_host", "method": "ip_literal"}
            )
        except ValueError:
            pass
    if native and native[0] in {"proxy", "web"}:
        raw = values.get("command") or ""
        for key, field in (
            ("bytes_out", "bytes_out"),
            ("status", "http_status"),
            ("method", "http_method"),
        ):
            match = re.search(r"(?:^|[;\s])" + key + r"=([^;\s]+)(?=[;\s]|$)", raw, re.I)
            if match:
                values[field] = match[1]
                derived.append(
                    {"field": field, "source": "command", "method": "explicit_key_value"}
                )
        if (
            native[0] == "proxy"
            and description.strip().casefold() == "https post outbound"
            and not values.get("http_method")
        ):
            values["http_method"] = "POST"
            derived.append(
                {
                    "field": "http_method",
                    "source": "event_description",
                    "method": "exact_proxy_POST_description",
                }
            )
        if not values.get("http_status") and re.fullmatch(
            r"[1-5]\d\d", str(values.get("result") or "")
        ):
            values["http_status"] = values["result"]
        if native[0] == "web" and raw.startswith(("/", "http://", "https://")):
            try:
                url = urlsplit(raw[:32768])
                values["http_path"] = url.path
                values["http_query"] = parse_qs(url.query, max_num_fields=100)
                derived.append({"field": "http_path", "source": "command", "method": "url_parse"})
            except ValueError:
                values["http_parse_error"] = True
    return values, native, {"adapter": adapter or "canonical_or_unknown", "derived": derived}
