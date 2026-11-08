"""Concise client report: all findings, compact evidence locators, no repeated prose."""

import io
from collections import Counter
from datetime import datetime
from html import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from app.attack_matrix import report_rows


def row_ranges(values):
    """Losslessly compress row numbers; never imply evidence in gaps."""
    numbers = sorted(set(values))
    runs = []
    for value in numbers:
        if runs and value == runs[-1][1] + 1:
            runs[-1][1] = value
        else:
            runs.append([value, value])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def render_client_pdf(data, metadata):
    output = io.BytesIO()
    blue = colors.HexColor("#17458c")
    body = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=5, wordWrap="CJK"
    )
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10, spaceAfter=3)
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=12,
        spaceAfter=6,
        textColor=blue,
        keepWithNext=True,
    )
    title = ParagraphStyle("Title", parent=heading, fontSize=23, leading=27)
    story = []

    def p(value, style=body):
        literal = str(value).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        literal = "".join(
            c if 32 <= ord(c) <= 255 or c in "\n\t" else f"[U+{ord(c):04X}]" for c in literal
        )
        return Paragraph(escape(literal).replace("\n", "<br/>"), style)

    def add(value, style=body):
        literal = str(value)
        for offset in range(0, max(1, len(literal)), 1200):
            story.append(p(literal[offset : offset + 1200], style))

    def table(rows, widths):
        result = LongTable(
            [[p(cell, small) for cell in row] for row in rows],
            colWidths=[w * mm for w in widths],
            repeatRows=1,
            hAlign="LEFT",
        )
        result.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7effb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, blue),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(result)

    summary = data["summary"]
    findings = data["findings"]
    counts = Counter(f["data"]["severity"] for f in findings)
    add("INFORME DE SEGURIDAD", title)
    add(data["title"], heading)
    add("Confidencial", small)
    fields = [
        ("Cliente", metadata.client),
        ("Analista", metadata.analyst),
        ("Consultora", metadata.organization),
        ("Referencia", metadata.reference),
    ]
    provided = [f"{label}: {value.strip()}" for label, value in fields if value.strip()]
    if provided:
        add(" | ".join(provided), small)
    add(f"Emitido: {datetime.now().strftime('%Y-%m-%d')}", small)
    add("1. Resumen ejecutivo", heading)
    add(
        f"Se revisaron {summary.get('input_events', 0)} registros y se identificaron "
        f"{len(findings)} hallazgos, sustentados en {len(data['evidence'])} evidencias distintas. "
        f"Se formaron {len(data['groups'])} grupos para investigar. "
        "Estos grupos no equivalen a incidentes confirmados."
    )
    table(
        [
            ["Crítico", "Alto", "Medio", "Bajo"],
            [str(counts[level]) for level in ("Crítico", "Alto", "Medio", "Bajo")],
        ],
        [43] * 4,
    )
    add(
        "La criticidad define prioridad de investigación. El análisis no confirma por sí solo "
        "compromiso, autoría ni impacto efectivo."
    )
    if findings:
        add(
            "Prioridad: revisar primero los hallazgos críticos y altos, validar su legitimidad "
            "con el cliente y preservar la evidencia antes de actuar."
        )
    else:
        add(
            "No se detectaron hallazgos con las reglas y campos disponibles; "
            "esto no demuestra ausencia de compromiso."
        )
    add("2. Plan de acción prioritario", heading)
    table(
        [
            ["Fase", "Acción propuesta"],
            [
                "Investigar",
                "Validar los hallazgos con sus responsables, cambios autorizados y "
                "telemetría adicional. Las acciones específicas se indican en cada hallazgo.",
            ],
            [
                "Contener",
                "Si se valida actividad no autorizada, acordar la revocación de sesiones "
                "o aislamiento de activos implicados, preservando evidencia "
                "y continuidad operativa.",
            ],
            [
                "Remediar",
                "Tras confirmar causa y alcance, corregir permisos, credenciales o "
                "configuraciones afectados y verificar la recuperación y ausencia de recurrencia.",
            ],
        ],
        [27, 145],
    )
    add("3. Hallazgos y evidencias", heading)
    add(
        "Se incluyen todos los hallazgos, sin filtros del dashboard. Las referencias F1, F2, etc. "
        "identifican las fuentes al final del documento. Las filas citadas son evidencias; "
        "las celdas completas siguen disponibles en la aplicación y en el PDF técnico.",
        small,
    )
    sources = {source["import_id"]: f"F{n}" for n, source in enumerate(data["sources"], 1)}
    evidence = {e["label"]: e for e in data["evidence"]}
    for item in findings:
        block_start = len(story)
        finding = item["data"]
        add(f"{item['label']} | {finding['severity']} | {finding['title']}", heading)
        # Explain once: the risk rationale already includes the technical trigger.
        add(finding.get("severity_reason") or finding["reason"])
        add(f"Posible impacto: {finding.get('potential_impact') or 'Por validar con el cliente.'}")
        add(
            f"Límite: {finding.get('limitations') or 'Requiere validar contexto y autorización.'}",
            small,
        )
        actions = finding.get("actions", [])
        if isinstance(actions, dict):
            actions = actions.get("investigate", [])
        if isinstance(actions, str):
            actions = [actions]
        if actions:
            add("Acción: " + " ".join(actions), small)
        locations = {}
        for reference in item["evidence"]:
            event = evidence[reference["evidence"]]
            locations.setdefault((event["import_id"], event["sheet"]), []).append(event["row"])
        for (import_id, sheet), rows in locations.items():
            add(f"Evidencia: {sources[import_id]}, hoja {sheet}, filas {row_ranges(rows)}.", small)
        block = story[block_start:]
        story[block_start:] = [KeepTogether(block)]
    add("4. Correlaciones", heading)
    if data["groups"]:
        labels = {f["id"]: f["label"] for f in findings}
        table(
            [["Grupo", "Hallazgos relacionados"]]
            + [
                [str(n), ", ".join(labels[i] for i in group["finding_ids"])]
                for n, group in enumerate(data["groups"], 1)
            ],
            [27, 145],
        )
        add(
            "Relaciones por eventos compartidos o coincidencia de usuario y activo dentro "
            "de la ventana configurada. Requieren validación; no son incidentes confirmados.",
            small,
        )
    else:
        add("No se identificaron grupos de hallazgos relacionados.")
    add("5. Alcance y limitaciones", heading)
    coverage = summary.get("coverage", [])
    evaluable = sum(c["eligible_events"] > 0 for c in coverage)
    add(
        f"Reglas con eventos evaluables: {evaluable}/{len(coverage)}. "
        f"Registros sin interpretación reconocida: {summary.get('unknown_events', 0)}; "
        f"filas rechazadas: {summary.get('import_rejected_rows', 0)}. "
        "Los resultados dependen de los campos y contexto disponibles."
    )
    unavailable = [c["title"] for c in coverage if c["status"] == "not_evaluable"]
    if unavailable:
        add("Reglas no evaluables: " + "; ".join(unavailable) + ".", small)
    add(summary.get("limitations", "Revisión humana requerida."), small)
    ai_count = sum(bool(f["ai"]) for f in findings)
    add(
        f"IA local: {ai_count}/{len(findings)} explicaciones validadas disponibles. "
        "La versión para cliente resume el análisis sustentado; las explicaciones ampliadas "
        "y su trazabilidad pueden exportarse en el PDF técnico.",
        small,
    )
    add("6. Recomendaciones generales", heading)
    add(
        "Como medidas preventivas, revisar MFA, mínimo privilegio, protección de respaldos "
        "y retención de registros; asignar responsables y criterios de cierre. "
        "Estas recomendaciones no implican que dichos controles estén ausentes."
    )
    add("7. MITRE ATT&CK - referencias del análisis", heading)
    attack = data["attack_matrix"]
    add(
        f"Enterprise {attack['release']}. Referencias contextuales, no técnicas confirmadas. "
        "Las tácticas son categorías del catálogo, no fases de ataque demostradas. "
        "Una técnica puede figurar en varias tácticas; no sumar sus conteos como incidentes.",
        small,
    )
    if attack["techniques"]:
        table(report_rows(data), [23, 91, 58])
    else:
        add("No hay referencias activas a técnicas en los hallazgos de este análisis.", small)
    add(
        f"Hallazgos sin referencia activa: {attack['unmapped_findings']}. "
        "Fuente: https://attack.mitre.org/matrices/enterprise/",
        small,
    )
    add("8. Fuentes y trazabilidad", heading)
    for n, source in enumerate(data["sources"], 1):
        add(f"F{n}: {source['name']} | Importación: {source['import_id']}", small)
        add(f"SHA-256 verificado: {source['sha256']}", small)
    add(
        f"Análisis: {data['analysis_id']} | "
        f"Motor: {data['config'].get('engine_version', 'No registrado')}",
        small,
    )
    add(f"Huella del contenido: {data['snapshot_hash']}", small)
    add(
        "La huella identifica la instantánea analítica; no es una firma ni aprobación humana.",
        small,
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(blue)
        canvas.drawString(19 * mm, 12 * mm, "SOC Analyst AI | Confidencial | Informe para cliente")
        canvas.drawRightString(191 * mm, 12 * mm, f"Página {doc.page}")
        canvas.restoreState()

    story.append(Spacer(1, 1))
    document = SimpleDocTemplate(
        output,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=17 * mm,
        bottomMargin=22 * mm,
        title="Informe de seguridad para cliente",
        author=metadata.analyst.strip(),
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
