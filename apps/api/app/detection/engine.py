"""Deterministic, evidence-only detection. No network access and no model calls."""

import shlex
from collections import Counter, defaultdict, deque
from datetime import time
from zoneinfo import ZoneInfo

from app.detection.config import ENGINE_VERSION, MAX_FINDINGS, MAX_LINKS, RULESET_VERSION
from app.detection.semantics import (
    duplicate_fingerprint,
    identifier,
    interpret,
    ip,
    privileged_target,
)
from app.fingerprints import config_digest

RULES = {
    "brute_force": ("Fallos repetidos de autenticación", "Medio", "Media", "T1110.001"),
    "password_spraying": (
        "Fallos contra múltiples cuentas: posible spraying",
        "Alto",
        "Media",
        "T1110.003",
    ),
    "success_after_failures": ("Acceso exitoso después de fallos", "Alto", "Media", "T1110"),
    "outside_hours": ("Acceso fuera del horario configurado", "Bajo", "Baja", None),
    "privilege_change": ("Asignación explícita de privilegios", "Medio", "Media", "T1098"),
    "suspicious_command": (
        "Comando o proceso registrado con patrón sospechoso",
        "Medio",
        "Baja",
        None,
    ),
    "lateral_movement": ("Accesos remotos a múltiples destinos", "Alto", "Media", "T1021"),
    "control_tampering": (
        "Registro explícito de desactivación o borrado de auditoría",
        "Alto",
        "Media",
        "T1562",
    ),
}
LIMITATIONS = {
    "brute_force": (
        "Fallos repetidos también pueden deberse a credenciales caducadas o "
        "automatización legítima. No demuestran acceso ni una contraseña "
        "adivinada."
    ),
    "password_spraying": (
        "Un proxy o servicio compartido puede explicar el origen. Los registros "
        "no demuestran reutilización de una misma contraseña."
    ),
    "success_after_failures": (
        "Una persona puede corregir su contraseña legítimamente. El éxito no "
        "confirma que el acceso sea del atacante."
    ),
    "outside_hours": (
        "El calendario es contexto aportado por el analista; viajes, turnos o "
        "mantenimiento pueden explicar el acceso."
    ),
    "privilege_change": (
        "La asignación puede estar autorizada. Verificar cambio aprobado, actor, "
        "cuenta afectada y grupo o privilegio concreto."
    ),
    "suspicious_command": (
        "Se observa el texto o nombre registrado; no se demuestra su ejecución "
        "exitosa, contenido decodificado ni intención maliciosa. Puede ser una "
        "prueba autorizada."
    ),
    "lateral_movement": (
        "El acceso remoto a varios destinos puede ser administración legítima. El"
        " abanico observado no demuestra una cadena de compromiso entre equipos."
    ),
    "control_tampering": (
        "El registro declara una acción sobre controles; no prueba que sea no "
        "autorizada ni que otros controles hayan quedado inactivos."
    ),
}
ACTIONS = {
    "brute_force": [
        "Revisar cuenta, origen, servicio y errores de autenticación.",
        "Buscar accesos posteriores y comprobar MFA o bloqueos.",
    ],
    "password_spraying": [
        "Investigar las cuentas y el origen compartido.",
        "Revisar MFA, exposición del servicio y política de bloqueo.",
    ],
    "success_after_failures": [
        "Validar el acceso con el titular y revisar actividad posterior.",
        "Si se confirma acceso no autorizado, revocar sesiones y restablecer credenciales.",
    ],
    "outside_hours": ["Contrastar el acceso con turnos, viajes y cambios autorizados."],
    "privilege_change": [
        "Comprobar la aprobación del cambio y la cuenta beneficiaria.",
        "Si no está autorizado, retirar el privilegio y revisar acciones de la cuenta.",
    ],
    "suspicious_command": [
        "Obtener proceso padre, argumentos completos, firma y resultado desde la fuente.",
        "Verificar si corresponde a administración o pruebas autorizadas antes de contener.",
    ],
    "lateral_movement": [
        "Revisar sesiones remotas y acciones en cada destino.",
        (
            "Si se confirma compromiso, limitar accesos y aislar los equipos "
            "afectados según el procedimiento del cliente."
        ),
    ],
    "control_tampering": [
        "Verificar cambios aprobados y restaurar el control si corresponde.",
        (
            "Preservar registros de otras fuentes y buscar actividad durante la "
            "pérdida de visibilidad."
        ),
    ],
}


def command_matches(observation):
    """Tokenize for inspection only; never execute or decode any command."""
    command = observation.values.get("command") or ""
    process = observation.values.get("process") or ""
    matches = []
    basename = process.strip().strip("\"'").replace("\\", "/").split("/")[-1].casefold()
    if basename in {"mimikatz", "mimikatz.exe"}:
        matches.append({"pattern": "credential_tool_name", "field": "process", "matched": process})
    try:
        tokens = [t.strip("\"'") for t in shlex.split(command, posix=False)]
    except ValueError:
        tokens = []
    if not tokens:
        return matches
    program = tokens[0].replace("\\", "/").split("/")[-1].casefold()
    args = [t.casefold() for t in tokens[1:]]
    pattern = None
    if program in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        stop = next(
            (i for i, a in enumerate(args) if a in {"-command", "-c", "-file", "-f", "--"}),
            len(args),
        )
        if any(
            a in {"-enc", "-encodedcommand"} and i + 1 < len(args) and args[i + 1]
            for i, a in enumerate(args[:stop])
        ):
            pattern = "powershell_encoded_argument"
    elif program in {"procdump", "procdump.exe", "procdump64.exe"}:
        if "-ma" in args and any(a in {"lsass", "lsass.exe"} for a in args):
            pattern = "lsass_dump_argument"
    elif program in {"wevtutil", "wevtutil.exe"}:
        if len(args) >= 2 and args[0] in {"cl", "clear-log"} and args[1] in {"security", "system"}:
            pattern = "audit_clear_command"
    elif program == "auditctl":
        if any(a == "-e" and i + 1 < len(args) and args[i + 1] == "0" for i, a in enumerate(args)):
            pattern = "audit_disable_command"
    elif program in {"mimikatz", "mimikatz.exe"}:
        pattern = "credential_tool_invocation"
    if pattern:
        # The full original command remains in event evidence; this is the matched field.
        matches.append({"pattern": pattern, "field": "command", "matched": command})
    return matches


def episodes(rows, window, threshold, distinct=None):
    """Sliding inclusive windows; coalesce overlapping qualifying windows in O(n)."""
    left = 0
    counter = Counter()
    result = []
    active = None
    for right, row in enumerate(rows):
        if distinct:
            counter[distinct(row)] += 1
        while (row.timestamp - rows[left].timestamp).total_seconds() > window:
            if distinct:
                key = distinct(rows[left])
                counter[key] -= 1
                if counter[key] == 0:
                    del counter[key]
            left += 1
        count = len(counter) if distinct else right - left + 1
        if count < threshold:
            continue
        if active is not None and left <= active["end"]:
            active["rows"].extend(rows[active["end"] + 1 : right + 1])
            active["end"] = right
            active["maximum"] = max(active["maximum"], count)
        else:
            active = {"rows": rows[left : right + 1], "end": right, "maximum": count}
            result.append(active)
    return result


def eligible(rule, row):
    if rule == "suspicious_command":
        return (
            None
            if row.values.get("command") or row.values.get("process")
            else "missing_command_or_process"
        )
    if row.conflict:
        return "conflicting_semantics"
    kind = (
        "grant"
        if rule == "privilege_change"
        else "control"
        if rule == "control_tampering"
        else "auth"
    )
    if row.kind != kind:
        return "not_applicable" if row.kind else "unknown_event_type"
    if kind in {"grant", "control"}:
        return None
    if row.outcome is None:
        return "unknown_outcome"
    if rule in {"brute_force", "password_spraying"} and row.outcome != "failure":
        return "not_applicable"
    if rule in {"outside_hours", "lateral_movement"} and row.outcome != "success":
        return "not_applicable"
    if rule == "lateral_movement" and not row.remote:
        return "remote_type_not_established"
    if not row.timestamp:
        return "missing_valid_timestamp"
    if not row.user:
        return "missing_user"
    if rule != "outside_hours" and not row.source:
        return "missing_valid_source"
    if rule == "lateral_movement":
        origin_host = identifier(row.values.get("source_host"), 253, True)
        dest_host = identifier(row.values.get("destination_host"), 253, True)
        origin_ip, dest_ip = ip(row.values.get("source_ip")), ip(row.values.get("destination_ip"))
        if (
            not row.destination
            or row.destination == row.source
            or origin_host
            and origin_host == dest_host
            or origin_ip
            and origin_ip == dest_ip
        ):
            return "missing_distinct_destination"
    return None


def detect(events, config):
    rows = []
    seen = {}
    duplicates = []
    exclusions = Counter()
    conflicts = 0
    # Stable representative selection independent of SQL ordering.
    for event in sorted(events, key=lambda e: e["id"]):
        key = duplicate_fingerprint(event)
        if key in seen:
            duplicates.append({"event_id": event["id"], "representative_id": seen[key]})
            continue
        seen[key] = event["id"]
        row = interpret(event, config)
        if row.user in config.excluded_users:
            exclusions["excluded_user"] += 1
            continue
        if ip(row.values.get("source_ip")) in config.excluded_source_ips:
            exclusions["excluded_source_ip"] += 1
            continue
        conflicts += row.conflict
        rows.append(row)
    rows.sort(key=lambda r: (r.timestamp.isoformat() if r.timestamp else "9999", r.id))
    # ISO strings with varying offsets/fractions must not be used for chronological ordering.
    dated = sorted([r for r in rows if r.timestamp], key=lambda r: (r.clock, r.timestamp, r.id))
    undated = [r for r in rows if not r.timestamp]
    rows = dated + undated
    by_id = {r.id: r for r in rows}
    findings = []
    coverage = []
    for rule, (title, severity, confidence, attack) in RULES.items():
        usable = []
        reasons = Counter()
        for row in rows:
            reason = eligible(rule, row)
            if rule == "outside_hours" and config.business_hours is None:
                reason = "calendar_not_configured"
            elif (
                rule == "outside_hours"
                and reason is None
                and config.business_hours.timezone is None
                and row.wall_time is None
            ):
                reason = "calendar_file_time_missing"
            if reason is None and rule == "privilege_change" and not privileged_target(row, config):
                reason = "missing_privileged_target"
            if reason:
                reasons[reason] += 1
            else:
                usable.append(row)
        excluded = sum(v for k, v in reasons.items() if k != "not_applicable")
        status = (
            "partial"
            if usable and excluded
            else "evaluated"
            if usable
            else "not_evaluable"
            if excluded or not rows
            else "not_applicable"
        )
        record = {
            "rule_id": rule,
            "title": title,
            "status": status,
            "eligible_events": len(usable),
            "excluded_reasons": dict(reasons),
            "findings": 0,
        }
        coverage.append(record)

        def emit(
            evidence,
            observed,
            reason,
            roles=None,
            *,
            rule=rule,
            title=title,
            severity=severity,
            confidence=confidence,
            attack=attack,
            record=record,
        ):
            if len(findings) >= MAX_FINDINGS:
                raise ValueError(
                    "El análisis supera 5000 hallazgos. Reduce el alcance; no se guardaron "
                    "resultados parciales."
                )
            ids = sorted(r.id for r in evidence)
            fingerprint = config_digest(
                {"rule": rule, "evidence": ids, "observed": observed, "clock": evidence[0].clock}
            )
            dates = [r.timestamp for r in evidence if r.timestamp]
            findings.append(
                {
                    "key": fingerprint,
                    "rule_id": rule,
                    "clock_basis": evidence[0].clock,
                    "title": title,
                    "severity": severity,
                    "confidence": confidence,
                    "attack_reference": attack,
                    "status": "requires_review",
                    "reason": reason,
                    "observed": observed,
                    "limitations": LIMITATIONS[rule],
                    "potential_impact": (
                        "Posible acceso no autorizado o pérdida de visibilidad; el impacto real "
                        "debe investigarse y no está demostrado por esta coincidencia."
                    ),
                    "actions": ACTIONS[rule],
                    "start": min(dates).isoformat() if dates else None,
                    "end": max(dates).isoformat() if dates else None,
                    "evidence_count": len(ids),
                    "evidence": [
                        {"event_id": i, "role": (roles or {}).get(i, "observed")} for i in ids
                    ],
                }
            )
            record["findings"] += 1

        if rule in {"brute_force", "password_spraying", "lateral_movement"}:
            grouped = defaultdict(list)
            for row in usable:
                key = (
                    (row.clock, row.source, row.user, row.destination)
                    if rule == "brute_force"
                    else (row.clock, row.source)
                    if rule == "password_spraying"
                    else (row.clock, row.source, row.user)
                )
                grouped[key].append(row)
            window = (
                config.brute_window
                if rule == "brute_force"
                else config.spray_window
                if rule == "password_spraying"
                else config.lateral_window
            )
            minimum = (
                config.brute_min
                if rule == "brute_force"
                else config.spray_min
                if rule == "password_spraying"
                else config.lateral_min
            )
            distinct = (
                None
                if rule == "brute_force"
                else (lambda r: r.user)
                if rule == "password_spraying"
                else (lambda r: r.destination)
            )
            for bucket in grouped.values():
                for episode in episodes(bucket, window, minimum, distinct):
                    sample = episode["rows"][0]
                    observed = {
                        "source": sample.source,
                        "window_seconds": window,
                        "minimum": minimum,
                        "max_in_window": episode["maximum"],
                        "sequence_events": len(episode["rows"]),
                    }
                    if rule != "password_spraying":
                        observed["user"] = sample.user
                    if rule == "brute_force":
                        observed["destination"] = sample.destination
                    unit = (
                        "fallos"
                        if rule == "brute_force"
                        else "usuarios distintos con fallos"
                        if rule == "password_spraying"
                        else "destinos distintos con acceso remoto exitoso"
                    )
                    emit(
                        episode["rows"],
                        observed,
                        f"Se observaron ventanas de {window} segundos con al menos {minimum} "
                        f"{unit}; máximo en una ventana: {episode['maximum']}. "
                        "La secuencia agrupada puede abarcar más de una ventana.",
                    )
        elif rule == "success_after_failures":
            grouped = defaultdict(list)
            for row in usable:
                grouped[(row.clock, row.source, row.user, row.destination)].append(row)
            for bucket in grouped.values():
                failures = deque()
                for row in sorted(
                    bucket, key=lambda r: (r.timestamp, 0 if r.outcome == "success" else 1, r.id)
                ):
                    while (
                        failures
                        and (row.timestamp - failures[0].timestamp).total_seconds()
                        > config.success_window
                    ):
                        failures.popleft()
                    if row.outcome == "failure":
                        failures.append(row)
                    else:
                        if len(failures) >= config.success_min:
                            evidence = list(failures) + [row]
                            emit(
                                evidence,
                                {
                                    "failures": len(failures),
                                    "window_seconds": config.success_window,
                                    "source": row.source,
                                    "user": row.user,
                                    "destination": row.destination,
                                },
                                f"Un acceso exitoso fue precedido por {len(failures)} fallos "
                                "con tiempo estrictamente anterior, mismo usuario, origen "
                                f"y destino disponible, en {config.success_window} segundos.",
                                {r.id: r.outcome for r in evidence},
                            )
                        failures.clear()
        elif rule == "outside_hours" and config.business_hours:
            schedule = config.business_hours
            begin, end = time.fromisoformat(schedule.start), time.fromisoformat(schedule.end)
            zone = ZoneInfo(schedule.timezone) if schedule.timezone else None
            for row in usable:
                local = (
                    (row.timestamp.astimezone(zone) if row.timestamp.tzinfo else row.timestamp)
                    if zone
                    else row.wall_time
                )
                if local.weekday() not in schedule.weekdays or not begin <= local.time() < end:
                    emit(
                        [row],
                        {
                            "local_time": local.isoformat(),
                            "timezone": schedule.timezone,
                            "weekdays": schedule.weekdays,
                            "start": schedule.start,
                            "end": schedule.end,
                        },
                        (
                            "El acceso exitoso queda fuera del calendario confirmado para este "
                            "análisis."
                        ),
                    )
        elif rule == "privilege_change":
            for row in usable:
                emit(
                    [row],
                    {
                        "target": privileged_target(row, config),
                        "event_type": row.values.get("event_type"),
                        "provider_event_id": row.values.get("provider_event_id"),
                        "target_user": row.values.get("target_user"),
                    },
                    (
                        "La fuente declara una asignación o adición de miembro y el "
                        "grupo/privilegio de destino está identificado explícitamente como "
                        "privilegiado."
                    ),
                )
        elif rule == "suspicious_command":
            for row in usable:
                matches = command_matches(row)
                if matches:
                    emit(
                        [row],
                        {"matches": matches},
                        (
                            "Se identificaron patrones concretos en campos de comando/proceso; se "
                            "requiere verificar contexto y resultado."
                        ),
                    )
        elif rule == "control_tampering":
            for row in usable:
                emit(
                    [row],
                    {
                        "event_type": row.values.get("event_type"),
                        "provider_event_id": row.values.get("provider_event_id"),
                    },
                    (
                        "El tipo explícito de evento o Windows Security 1102 declara "
                        "desactivación o borrado; no se deduce de un silencio en los logs ni de "
                        "un cambio genérico de política."
                    ),
                )
                declared = (row.values.get("event_type") or "").strip().casefold()
                windows = config.source_profile == "windows_security" or (
                    (row.values.get("event_provider") or "").strip().casefold()
                    == "microsoft-windows-security-auditing"
                )
                cleared = "cleared" in declared or (
                    windows and (row.values.get("provider_event_id") or "").strip() == "1102"
                )
                findings[-1]["attack_reference"] = "T1070" if cleared else "T1562"
    findings.sort(key=lambda f: (f["clock_basis"], f["start"] or "9999", f["rule_id"], f["key"]))
    if sum(f["evidence_count"] for f in findings) > 500_000:
        raise ValueError("Demasiadas referencias de evidencia. Reduce el alcance del análisis.")
    groups = correlate(findings, by_id, config.correlation_window)
    return {
        "findings": findings,
        "groups": groups,
        "duplicates": duplicates,
        "summary": {
            "engine_version": ENGINE_VERSION,
            "ruleset_version": RULESET_VERSION,
            "input_events": len(events),
            "unique_events": len(seen),
            "duplicate_events": len(duplicates),
            "excluded_events": sum(exclusions.values()),
            "exclusions": dict(exclusions),
            "conflicting_semantics": conflicts,
            "coverage": coverage,
            "findings": len(findings),
            "investigation_groups": len(groups),
            "by_severity": {
                s: sum(f["severity"] == s for f in findings)
                for s in ("Crítico", "Alto", "Medio", "Bajo")
            },
            "limitations": (
                "No hay confirmación automática de incidentes. Un análisis sin hallazgos "
                "no demuestra ausencia de compromiso; consulta la cobertura y los campos "
                "no evaluables."
            ),
        },
    }


def correlate(findings, observations, window):
    """Deterministic evidence-backed spanning forest, not an incident counter."""
    from datetime import datetime

    parent = list(range(len(findings)))
    starts = [datetime.fromisoformat(f["start"]) if f["start"] else None for f in findings]
    ends = [datetime.fromisoformat(f["end"]) if f["end"] else None for f in findings]
    links = []
    last_pair, last_event = {}, {}

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for index, finding in enumerate(findings):
        candidates = {}
        pairs = set()
        for ref in finding["evidence"]:
            event_id = ref["event_id"]
            if event_id in last_event:
                candidates[last_event[event_id]] = {"kind": "shared_event", "event_id": event_id}
            row = observations[event_id]
            pairs.update((row.clock, u, asset) for u in row.users for asset in row.assets)
        for pair in sorted(pairs):
            previous = last_pair.get(pair)
            if previous is not None and previous not in candidates:
                candidates[previous] = {
                    "kind": "shared_user_asset",
                    "user": pair[1],
                    "asset": pair[2],
                }
        for previous, reason in sorted(candidates.items(), reverse=True):
            a, b = root(previous), root(index)
            if a == b:
                continue
            begin = min(starts[a], starts[b]) if starts[a] and starts[b] else None
            end = max(ends[a], ends[b]) if ends[a] and ends[b] else None
            if reason["kind"] != "shared_event" and (
                begin is None or end is None or (end - begin).total_seconds() > window
            ):
                continue
            if len(links) >= MAX_LINKS:
                raise ValueError("Demasiadas relaciones. Reduce el alcance del análisis.")
            parent[b] = a
            starts[a], ends[a] = begin, end
            links.append({"from": findings[previous]["key"], "to": finding["key"], **reason})
        for pair in pairs:
            last_pair[pair] = index
        for ref in finding["evidence"]:
            last_event[ref["event_id"]] = index
    components = defaultdict(list)
    for index, finding in enumerate(findings):
        components[root(index)].append(finding["key"])
    result = []
    for members in components.values():
        member_set = set(members)
        key = config_digest({"members": sorted(members)})
        component_links = [link for link in links if link["from"] in member_set]
        result.append(
            {
                "key": key,
                "finding_keys": members,
                "links": component_links,
                "interpretation": (
                    "Grupo para investigar, no incidente confirmado. Los vínculos se "
                    "sustentan en eventos compartidos o usuario y activo coincidentes dentro "
                    "de la ventana configurada."
                ),
            }
        )
    return result
