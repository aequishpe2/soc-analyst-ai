"""Additional evidence-based detections and conditional response guidance."""

import re
import shlex
from bisect import bisect_right
from collections import defaultdict, deque

CATALOG = {
    "auth_burst": (
        "Ráfaga de fallos distribuida entre cuentas o destinos",
        "Alto",
        "Media",
        "T1110",
    ),
    "remote_after_failures": ("Acceso remoto exitoso tras fallos", "Alto", "Media", "T1078"),
    "privileged_session": (
        "Sesión con privilegios asociada a un inicio de sesión",
        "Medio",
        "Media",
        "T1078",
    ),
    "scheduled_task": (
        "Creación o modificación de tarea programada",
        "Medio",
        "Media",
        "T1053.005",
    ),
    "service_installation": ("Instalación de un servicio", "Medio", "Media", "T1543.003"),
    "recovery_inhibition": (
        "Orden de desactivación o eliminación de recuperación",
        "Alto",
        "Media",
        "T1490",
    ),
    "archive_creation": ("Compresión de archivos registrada", "Bajo", "Baja", "T1560.001"),
    "data_transfer": ("Transferencia POST de gran volumen registrada", "Alto", "Media", "T1041"),
    "web_command": (
        "Solicitud web con parámetro de comando del sistema",
        "Alto",
        "Media",
        "T1505.003",
    ),
    "discovery_commands": (
        "Enumeración de recursos o privilegios registrada",
        "Bajo",
        "Baja",
        "T1135",
    ),
    "remote_share_sequence": (
        "Acceso remoto seguido de acceso a un recurso compartido",
        "Medio",
        "Media",
        "T1021.002",
    ),
}
LIMITATIONS = {
    "auth_burst": (
        "Los fallos pueden ser automatización legítima o credenciales caducadas. "
        "Una ráfaga no prueba intrusión."
    ),
    "remote_after_failures": (
        "El titular puede corregir sus credenciales. Se prueba la secuencia "
        "registrada, no quién controló la cuenta."
    ),
    "privileged_session": (
        "Windows 4672 registra privilegios de una sesión, no demuestra una elevación no autorizada."
    ),
    "scheduled_task": (
        "Crear una tarea es una operación administrativa habitual. Se requiere "
        "revisar su aprobación y acción configurada."
    ),
    "service_installation": (
        "Instalar un servicio puede ser legítimo. Una ruta o un nombre no prueban malware."
    ),
    "recovery_inhibition": (
        "Se observa una orden de afectar la recuperación; el registro no "
        "demuestra el borrado efectivo ni confirma ransomware."
    ),
    "archive_creation": (
        "La compresión también es actividad legítima. No demuestra recolección "
        "maliciosa ni salida de datos."
    ),
    "data_transfer": (
        "El volumen y el POST son observaciones del proxy; no prueban contenido "
        "sensible, destino malicioso ni exfiltración."
    ),
    "web_command": (
        "Una petición con comando puede ser una prueba autorizada. Una respuesta "
        "HTTP no demuestra ejecución ni una web shell implantada."
    ),
    "discovery_commands": (
        "La enumeración puede ser administración o diagnóstico legítimos. No "
        "demuestra movimiento lateral."
    ),
    "remote_share_sequence": (
        "La secuencia puede ser administración normal. No prueba explotación ni "
        "compromiso de los sistemas."
    ),
}
INVESTIGATE = {
    "auth_burst": (
        "Contrastar las cuentas y servicios con tareas automatizadas y verificar "
        "accesos posteriores."
    ),
    "remote_after_failures": (
        "Validar el acceso remoto con el titular y revisar la sesión y su actividad posterior."
    ),
    "privileged_session": (
        "Revisar los privilegios concretos, el tipo de cuenta y la autorización de la sesión."
    ),
    "scheduled_task": (
        "Revisar el XML o la definición completa de la tarea, actor, "
        "desencadenador, acción y aprobación."
    ),
    "service_installation": (
        "Obtener la configuración del servicio, firma y hash del binario, actor y cambio aprobado."
    ),
    "recovery_inhibition": (
        "Verificar inmediatamente la orden, su actor y resultado, el estado de "
        "las copias y las actividades cercanas."
    ),
    "archive_creation": (
        "Verificar propietario, archivos incluidos, propósito de la compresión y "
        "actividad de transferencia posterior."
    ),
    "data_transfer": (
        "Revisar destino, autorización, contenido mediante fuentes permitidas y "
        "posible relación con archivos comprimidos."
    ),
    "web_command": (
        "Revisar petición, respuesta, logs de aplicación y procesos del servidor "
        "para comprobar si hubo ejecución."
    ),
    "discovery_commands": (
        "Contrastar los comandos de enumeración con la función del usuario y sus "
        "acciones posteriores."
    ),
    "remote_share_sequence": (
        "Revisar la sesión remota, el recurso y las operaciones de archivos, y "
        "verificar su autorización."
    ),
}
CONTAIN = {
    key: (
        "Si se confirma actividad no autorizada, restringir la cuenta o el equipo"
        " implicado preservando la evidencia."
    )
    for key in CATALOG
}
REMEDIATE = {
    key: (
        "Tras validar la causa, corregir permisos y configuración y verificar que"
        " la actividad no se repita."
    )
    for key in CATALOG
}
CONTAIN["recovery_inhibition"] = (
    "Si la orden no está autorizada o está en curso, activar el procedimiento"
    " de respuesta y proteger inmediatamente las copias de recuperación."
)
REMEDIATE["recovery_inhibition"] = (
    "Tras preservar evidencia y validar el alcance, restaurar la capacidad de"
    " recuperación y revisar privilegios sobre copias y sistemas."
)


IMPACTS = {
    ("auth_burst"): (
        "Posible intento de adivinar credenciales o afectar la "
        "disponibilidad de autenticación; no se demuestra acceso."
    ),
    ("remote_after_failures"): (
        "Posible uso no autorizado de una sesión remota; deben revisarse acciones y alcance."
    ),
    ("privileged_session"): (
        "Una sesión privilegiada podría modificar recursos sensibles si "
        "se utilizara sin autorización."
    ),
    ("scheduled_task"): (
        "La tarea podría permitir ejecución recurrente o persistencia si "
        "su creación no estuviera autorizada."
    ),
    ("service_installation"): (
        "El servicio podría permitir ejecución persistente con los "
        "privilegios de su cuenta de servicio."
    ),
    ("recovery_inhibition"): (
        "Si la orden se completa, puede reducir o impedir la recuperación"
        " de datos y aumentar el impacto de una interrupción."
    ),
    ("archive_creation"): (
        "La compresión podría facilitar traslado de datos si se relaciona"
        " con actividad posterior no autorizada."
    ),
    ("data_transfer"): (
        "Una transferencia no autorizada podría comprometer la "
        "confidencialidad; el contenido transferido no está demostrado."
    ),
    ("web_command"): (
        "Si el servidor ejecutara la orden, podría exponer su cuenta y "
        "recursos; la petición sola no acredita ese efecto."
    ),
    ("discovery_commands"): (
        "La enumeración podría facilitar selección de objetivos si forma "
        "parte de una actividad no autorizada."
    ),
    ("remote_share_sequence"): (
        "Una sesión no autorizada podría dar acceso a archivos "
        "compartidos; deben verificarse permisos y operaciones concretas."
    ),
}


def rationale(rule, observed, severity):
    if rule == "recovery_inhibition":
        return (
            (
                "Prioridad crítica: orden explícita de eliminación total y silenciosa de copias, "
                "con resultado de evento registrado como exitoso. No prueba el borrado efectivo."
            )
            if severity == "Crítico"
            else (
                "Prioridad alta: orden explícita de eliminar o desactivar "
                "recuperación; el alcance o resultado final requiere "
                "verificación."
            )
        )
    if rule == "scheduled_task":
        return (
            (
                "Prioridad alta por persistencia programada con intérprete de "
                "scripts o una ruta no propia del sistema."
            )
            if severity == "Alto"
            else (
                "Tarea registrada sin indicadores suficientes para elevar su "
                "prioridad; requiere validar aprobación."
            )
        )
    if rule == "service_installation":
        return (
            (
                "Prioridad alta: un servicio nuevo referencia un binario en "
                "ProgramData, Users Public o Temp."
            )
            if severity == "Alto"
            else (
                "Servicio registrado sin una ruta de riesgo identificada; "
                "requiere validar aprobación y firma."
            )
        )
    return {
        ("auth_burst"): (
            "Prioridad alta por el volumen de fallos distribuido entre "
            "cuentas o destinos desde un mismo origen y ventana."
        ),
        ("remote_after_failures"): (
            "Prioridad alta por un éxito remoto tras al menos tres fallos "
            "previos con las mismas entidades."
        ),
        ("privileged_session"): (
            "Prioridad media: privilegios de sesión asociados a un inicio de "
            "sesión, sin prueba de elevación no autorizada."
        ),
        ("archive_creation"): (
            "Prioridad baja: la creación de archivos comprimidos admite "
            "explicaciones habituales y requiere contexto posterior."
        ),
        ("data_transfer"): (
            "Prioridad alta por superar el umbral de volumen saliente "
            "registrado mediante POST en una misma ventana."
        ),
        ("web_command"): (
            "Prioridad alta por una orden del sistema en el parámetro de un "
            "endpoint de script; se requiere comprobar ejecución."
        ),
        ("discovery_commands"): (
            "Prioridad baja: orden de enumeración que puede ser diagnóstico o"
            " administración legítimos."
        ),
        ("remote_share_sequence"): (
            "Prioridad media por una secuencia remota y de recurso compartido"
            " con la misma cuenta y equipo."
        ),
    }.get(rule)


def host(row):
    return (
        (row.values.get("reporting_host") or row.values.get("destination_host") or "")
        .strip()
        .casefold()
    )


def tokens(row):
    raw = row.values.get("command") or ""
    try:
        parts = [v.strip("\"'") for v in shlex.split(raw, posix=False)]
    except ValueError:
        return "", []
    if not parts:
        return "", []
    return parts[0].replace("\\", "/").split("/")[-1].casefold(), [p.casefold() for p in parts[1:]]


def command_pattern(rule, row):
    program, args = tokens(row)
    if rule == "recovery_inhibition":
        if program in {"vssadmin", "vssadmin.exe"} and args[:2] == ["delete", "shadows"]:
            return {
                "pattern": "delete_shadow_copies",
                "all": "/all" in args,
                "quiet": "/quiet" in args,
            }
        if program in {"wbadmin", "wbadmin.exe"} and args[:2] == ["delete", "catalog"]:
            return {"pattern": "delete_backup_catalog", "quiet": "-quiet" in args}
        if (
            program in {"bcdedit", "bcdedit.exe"}
            and "/set" in args
            and "recoveryenabled" in args
            and "no" in args
        ):
            return {"pattern": "disable_recovery"}
    if rule == "archive_creation":
        if program in {"7z", "7z.exe", "7za.exe"} and args and args[0] == "a":
            return {"pattern": "7z_add_archive"}
        if (
            program in {"tar", "tar.exe"}
            and any(
                a in {"-c", "--create"} or re.fullmatch(r"-[acfzv]+", a) and "c" in a for a in args
            )
            and any(a == "-f" or a.endswith((".zip", ".tar", ".gz")) for a in args)
        ):
            return {"pattern": "tar_create_archive"}
    if rule == "discovery_commands":
        script = row.values.get("script_block") or ""
        if program in {"net", "net.exe"} and args and args[0] in {"view", "group", "localgroup"}:
            return {"pattern": "net_resource_enumeration"}
        if re.search(r"(?:^|;)\s*(?:Get-LocalGroupMember|Get-SmbShare)(?=[\s;]|$)", script, re.I):
            return {"pattern": "powershell_resource_enumeration"}
    return None


def eligible(rule, row):
    if row.conflict:
        return "conflicting_semantics"
    kinds = {
        "auth_burst": {"auth"},
        "remote_after_failures": {"auth"},
        "privileged_session": {"privileged_session"},
        "scheduled_task": {"task"},
        "service_installation": {"service"},
        "data_transfer": {"proxy"},
        "web_command": {"web"},
        "remote_share_sequence": {"share"},
        "recovery_inhibition": {"process"},
        "archive_creation": {"process"},
        "discovery_commands": {"process"},
    }
    if row.kind not in kinds[rule]:
        return "not_applicable" if row.kind else "unknown_event_type"
    if rule in {
        "auth_burst",
        "remote_after_failures",
        "data_transfer",
        "privileged_session",
        "remote_share_sequence",
    }:
        if not row.timestamp:
            return "missing_valid_timestamp"
    if rule in {"auth_burst", "remote_after_failures"}:
        if not row.source:
            return "missing_valid_source"
        if row.outcome not in {"success", "failure"}:
            return "unknown_outcome"
        if rule == "remote_after_failures" and not row.remote:
            return "remote_type_not_established"
        if rule == "remote_after_failures" and (not row.user or not host(row)):
            return "missing_user_or_reporting_host"
    if rule == "auth_burst" and row.outcome != "failure":
        return "not_applicable"
    if rule in {"privileged_session", "remote_share_sequence"} and (not row.user or not host(row)):
        return "missing_user_or_reporting_host"
    if rule == "data_transfer":
        raw = str(row.values.get("bytes_out") or "")
        if not raw.isdigit() or len(raw) > 16 or not 0 < int(raw) <= 2**53:
            return "missing_valid_transfer_bytes"
        if row.values.get("http_method", "").upper() != "POST":
            return "missing_explicit_post"
        if not row.source and not host(row):
            return "missing_valid_source"
    return None


def windows(rows, seconds, threshold, weight=lambda r: 1):
    rows = sorted(rows, key=lambda r: (r.timestamp, r.id))
    left, amount = 0, 0
    ranges = []
    for right, row in enumerate(rows):
        amount += weight(row)
        while (row.timestamp - rows[left].timestamp).total_seconds() > seconds:
            amount -= weight(rows[left])
            left += 1
        if amount >= threshold:
            if ranges and left <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], right, max(ranges[-1][2], amount))
            else:
                ranges.append((left, right, amount))
    return [(rows[a : b + 1], maximum) for a, b, maximum in ranges]


def run(rule, usable, all_rows, config, emit):
    if rule in {"auth_burst", "data_transfer", "remote_after_failures"}:
        grouped = defaultdict(list)
        for row in usable:
            key = (row.clock, row.source or host(row))
            if rule == "data_transfer":
                key += (host(row), row.user, row.destination)
            elif rule == "remote_after_failures":
                key += (row.user, host(row))
            grouped[key].append(row)
        for rows in grouped.values():
            if rule == "remote_after_failures":
                failures = deque()
                for success in sorted(
                    rows, key=lambda r: (r.timestamp, 0 if r.outcome == "success" else 1, r.id)
                ):
                    while (
                        failures
                        and (success.timestamp - failures[0].timestamp).total_seconds()
                        > config.success_window
                    ):
                        failures.popleft()
                    if success.outcome == "failure":
                        failures.append(success)
                        continue
                    if len(failures) >= 3:
                        evidence = list(failures) + [success]
                        emit(
                            evidence,
                            {
                                "failures": len(failures),
                                "window_seconds": config.success_window,
                                "remote_logon_type": success.values.get("logon_type"),
                            },
                            (
                                "Un acceso explícitamente remoto y exitoso está precedido "
                                "por al menos "
                                "tres fallos del mismo origen, usuario y equipo en la ventana "
                                "configurada."
                            ),
                            {r.id: r.outcome for r in evidence},
                        )
                    failures.clear()
                continue
            threshold = config.burst_min if rule == "auth_burst" else config.transfer_bytes
            weight = (
                (lambda r: 1) if rule == "auth_burst" else (lambda r: int(r.values["bytes_out"]))
            )
            for evidence, maximum in windows(rows, config.burst_window, threshold, weight):
                if rule == "auth_burst" and len({(r.user, r.destination) for r in evidence}) < 2:
                    continue
                emit(
                    evidence,
                    {
                        "window_seconds": config.burst_window,
                        "threshold": threshold,
                        "max_in_window": maximum,
                        "sequence_events": len(evidence),
                    },
                    (
                        "Se superó el umbral de fallos distribuidos entre cuentas o destinos "
                        "desde un mismo origen."
                    )
                    if rule == "auth_burst"
                    else (
                        "La suma de bytes salientes registrados en peticiones POST superó el "
                        "umbral dentro de la ventana configurada; se cuenta el volumen "
                        "registrado, no contenido inferido."
                    ),
                )
        return
    auth_index = defaultdict(list)
    if rule in {"privileged_session", "remote_share_sequence"}:
        for row in all_rows:
            if (
                row.kind == "auth"
                and row.outcome == "success"
                and row.timestamp
                and row.user
                and host(row)
                and (rule != "remote_share_sequence" or row.remote)
            ):
                auth_index[(row.clock, row.user, host(row))].append(row)
    auth_index = {
        key: (
            sorted([r.timestamp for r in group]),
            sorted(group, key=lambda r: (r.timestamp, r.id)),
        )
        for key, group in auth_index.items()
    }
    for row in usable:
        if rule in {"recovery_inhibition", "archive_creation", "discovery_commands"}:
            pattern = command_pattern(rule, row)
            if pattern:
                critical = (
                    rule == "recovery_inhibition"
                    and pattern.get("all")
                    and pattern.get("quiet")
                    and row.outcome == "success"
                )
                emit(
                    [row],
                    pattern,
                    (
                        "El registro contiene una orden explícita de afectar las copias de "
                        "recuperación."
                    )
                    if rule == "recovery_inhibition"
                    else "Se observa una orden concreta de crear un archivo comprimido."
                    if rule == "archive_creation"
                    else "Se observa una orden concreta de enumeración de recursos o privilegios.",
                    severity="Crítico" if critical else CATALOG[rule][1],
                )
        elif rule in {"scheduled_task", "service_installation"}:
            command = row.values.get("command") or ""
            key = "Action" if rule == "scheduled_task" else "ImagePath"
            target = re.search(r"(?:^|;)\s*" + key + r"\s*=\s*([^;]+)", command, re.I)
            target = target[1].strip() if target else command
            try:
                parts = [p.strip("\"'") for p in shlex.split(target, posix=False)]
            except ValueError:
                parts = []
            program = parts[0].replace("\\", "/").split("/")[-1].casefold() if parts else ""
            args = [p.casefold() for p in parts[1:]]
            stop = next((i for i, a in enumerate(args) if a in {"-command", "-c", "--"}), len(args))
            script_option = next(
                (
                    i
                    for i, a in enumerate(args[:stop])
                    if a in {"-file", "-enc", "-encodedcommand"} and i + 1 < len(args)
                ),
                None,
            )
            script_loader = (
                program in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
                and script_option is not None
            )
            paths = parts[:1] + (
                [parts[script_option + 2]]
                if script_loader and args[script_option] == "-file"
                else []
            )
            unusual_path = any(
                re.match(r"[a-z]:\\(?:ProgramData|Users\\Public|Temp)\\", p, re.I) for p in paths
            )
            high = (script_loader or unusual_path) and bool(command)
            emit(
                [row],
                {
                    "provider_event_id": row.values.get("provider_event_id"),
                    "script_loader": script_loader,
                    "non_system_path": unusual_path,
                },
                (
                    "La fuente registra creación o modificación de una tarea programada; se "
                    "revisó su acción disponible."
                )
                if rule == "scheduled_task"
                else (
                    "La fuente registra instalación de un servicio; se revisó la ruta del "
                    "binario disponible."
                ),
                severity="Alto" if high else "Medio",
            )
        elif rule == "web_command":
            query = row.values.get("http_query") or {}
            path = row.values.get("http_path") or ""
            candidate = [v for key in ("cmd", "exec", "command") for v in query.get(key, [])]
            if re.search(r"\.(?:aspx?|php|jsp)$", path, re.I) and any(
                re.match(
                    r"\s*(?:whoami|cmd(?:\.exe)?|powershell(?:\.exe)?|id|uname)(?:\s|$)", v, re.I
                )
                for v in candidate
            ):
                emit(
                    [row],
                    {
                        "pattern": "script_endpoint_os_command",
                        "http_status": row.values.get("http_status"),
                    },
                    (
                        "Una petición a un endpoint de script incluye un parámetro de comando con"
                        " una orden del sistema. No se infiere ejecución de la petición."
                    ),
                )
        elif rule in {"privileged_session", "remote_share_sequence"}:
            times, related = auth_index.get((row.clock, row.user, host(row)), ([], []))
            index = bisect_right(times, row.timestamp) - 1
            if (
                index >= 0
                and (row.timestamp - times[index]).total_seconds() <= config.success_window
            ):
                auth = related[index]
                emit(
                    [auth, row],
                    {
                        "window_seconds": config.success_window,
                        "provider_event_id": row.values.get("provider_event_id"),
                    },
                    (
                        "Una asignación de privilegios de sesión se asocia por cuenta y equipo a "
                        "un inicio de sesión previo."
                    )
                    if rule == "privileged_session"
                    else (
                        "Un acceso a recurso compartido sigue a un inicio remoto exitoso con la "
                        "misma cuenta y equipo."
                    ),
                    {auth.id: "success", row.id: "observed"},
                )
