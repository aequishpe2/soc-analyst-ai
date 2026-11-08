"""Evidence-backed report snapshots and PDF rendering. No inference is run on export."""

import hashlib
import io
import json
import uuid
from collections import Counter
from datetime import datetime
from html import escape
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.client_report import render_client_pdf
from app.detection.dashboard import PRIORITY_ORDER
from app.fingerprints import config_digest, digest_file
from app.models import (
    AIDraft,
    Analysis,
    AnalysisScope,
    Case,
    Event,
    Finding,
    FindingEvidence,
    ImportRun,
    InvestigationGroup,
    SourceFile,
)

VERSION = "technical-report-2"
MAX_FINDINGS = 2000
MAX_REFERENCES = 20000
MAX_BYTES = 20 * 1024 * 1024


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analyst: str = Field(default="", max_length=150)
    client: str = Field(default="", max_length=200)
    organization: str = Field(default="", max_length=200)
    reference: str = Field(default="", max_length=100)
    include_ai: bool = True
    format: Literal["client", "technical"] = "client"
    # Optional optimistic lock: the reviewed preview must match the downloaded PDF.
    snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


def snapshot(db, storage, analysis_id):
    analysis = db.get(Analysis, str(analysis_id))
    if analysis is None:
        raise HTTPException(404, "Análisis no encontrado.")
    if analysis.status != "succeeded":
        raise HTTPException(409, "Espera a que termine el análisis antes de preparar el informe.")
    case = db.get(Case, analysis.case_id)
    sources = []
    imports = set()
    for run, source in db.execute(
        select(ImportRun, SourceFile)
        .join(SourceFile, SourceFile.id == ImportRun.file_id)
        .join(AnalysisScope, AnalysisScope.import_id == ImportRun.id)
        .where(AnalysisScope.analysis_id == analysis.id)
        .order_by(ImportRun.id)
    ):
        try:
            valid = (
                digest_file(storage / source.id / ("source" + source.extension)) == source.sha256
            )
        except OSError:
            valid = False
        if not valid or source.case_id != case.id:
            raise HTTPException(409, "No se pudo verificar la integridad de una fuente original.")
        imports.add(run.id)
        sources.append(
            {
                "name": source.name,
                "sha256": source.sha256,
                "import_id": run.id,
                "summary": run.summary,
            }
        )
    if not sources:
        raise HTTPException(409, "El análisis no tiene fuentes verificables.")
    findings = db.scalars(
        select(Finding)
        .where(Finding.analysis_id == analysis.id)
        .order_by(PRIORITY_ORDER, Finding.id)
        .limit(MAX_FINDINGS + 1)
    ).all()
    if len(findings) > MAX_FINDINGS:
        raise HTTPException(413, "El informe admite hasta 2000 hallazgos. Reduce el alcance.")
    refs = db.execute(
        select(FindingEvidence, Event)
        .join(Event, Event.id == FindingEvidence.event_id)
        .join(Finding, Finding.id == FindingEvidence.finding_id)
        .where(Finding.analysis_id == analysis.id)
        .order_by(Event.import_id, Event.sheet, Event.row, Event.id, Finding.id)
        .limit(MAX_REFERENCES + 1)
    ).all()
    if len(refs) > MAX_REFERENCES:
        raise HTTPException(413, "El informe admite hasta 20 000 referencias. Reduce el alcance.")
    evidence = {}
    references = {}
    for ref, event in refs:
        if event.import_id not in imports or event.case_id != case.id:
            raise HTTPException(409, "La evidencia no pertenece al alcance del análisis.")
        if event.id not in evidence:
            evidence[event.id] = {
                "label": f"E{len(evidence) + 1:04d}",
                "id": event.id,
                "import_id": event.import_id,
                "sheet": event.sheet,
                "row": event.row,
                "line_end": event.line_end,
                "values": event.normalized,
                "warnings": event.warnings,
            }
        references.setdefault(ref.finding_id, []).append(
            {"evidence": evidence[event.id]["label"], "role": ref.role}
        )
    drafts = {
        d.finding_id: d
        for d in db.scalars(
            select(AIDraft)
            .join(Finding, Finding.id == AIDraft.finding_id)
            .where(Finding.analysis_id == analysis.id)
        )
    }
    items = []
    for n, finding in enumerate(findings, 1):
        links = references.get(finding.id, [])
        if not links or len(links) != finding.payload.get("evidence_count"):
            raise HTTPException(409, "Un hallazgo tiene referencias de evidencia incompletas.")
        draft = drafts.get(finding.id)
        ai = None
        if draft and draft.status == "succeeded" and draft.result:
            ai = {
                "model": draft.model,
                "digest": draft.model_digest,
                "version": draft.version,
                "input_hash": draft.input_hash,
                "result": draft.result,
            }
        items.append(
            {
                "label": f"H{n:03d}",
                "id": finding.id,
                "group_id": finding.group_id,
                "data": finding.payload,
                "evidence": links,
                "ai": ai,
            }
        )
    result = {
        "version": VERSION,
        "analysis_id": analysis.id,
        "case_id": case.id,
        "title": case.title,
        "analysis_created_at": analysis.created_at.isoformat(),
        "input_hash": analysis.input_hash,
        "config": analysis.config,
        "summary": analysis.summary,
        "sources": sources,
        "findings": items,
        "evidence": list(evidence.values()),
        "groups": [
            {"id": g.id, **g.payload}
            for g in db.scalars(
                select(InvestigationGroup)
                .where(InvestigationGroup.analysis_id == analysis.id)
                .order_by(InvestigationGroup.id)
            )
        ],
    }
    encoded = json.dumps(result, ensure_ascii=False).encode()
    if len(encoded) > MAX_BYTES:
        raise HTTPException(413, "El informe supera 20 MiB de contenido. Reduce el alcance.")
    result["snapshot_hash"] = config_digest(result)
    return result


def render_pdf(data, metadata):
    if metadata.format == "client":
        output = render_client_pdf(data, metadata)
        if len(output) > MAX_BYTES:
            raise HTTPException(413, "El PDF supera 20 MiB. Reduce el alcance.")
        return output
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=6,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSmall",
            parent=styles["ReportBody"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=32,
            textColor=colors.HexColor("#17458c"),
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportHeading",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#17458c"),
            spaceBefore=15,
            spaceAfter=9,
            keepWithNext=True,
        )
    )
    story = []

    def text(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value) if value is not None else "No registrado"

    def p(value, style="ReportBody"):
        # Log values are always literal text, never ReportLab markup.
        value = text(value).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        # Core PDF fonts support Latin-1; unsupported glyphs remain traceable as U+XXXX.
        value = "".join(
            c if 32 <= ord(c) <= 255 or c in "\n\t" else f"[U+{ord(c):04X}]" for c in value
        )
        return Paragraph(escape(value).replace("\n", "<br/>"), styles[style])

    def add(value, style="ReportBody"):
        literal = text(value)
        for offset in range(0, max(1, len(literal)), 1400):
            story.append(p(literal[offset : offset + 1400], style))

    def heading(value):
        add(value, "ReportHeading")

    def details(value):
        if isinstance(value, dict):
            for key, val in value.items():
                add(f"{key}: {text(val)}", "ReportSmall")
        elif isinstance(value, list):
            for val in value:
                add(text(val))
        else:
            add(value)

    summary = data["summary"]
    ready_ai = sum(bool(f["ai"]) for f in data["findings"])
    add("SOC ANALYST AI | INFORME DE SEGURIDAD", "ReportSmall")
    story.append(Spacer(1, 16 * mm))
    add("Investigación de registros SIEM", "ReportTitle")
    add(data["title"], "ReportHeading")
    add("CONFIDENCIAL")
    for label, value in (
        ("Cliente", metadata.client),
        ("Analista", metadata.analyst),
        ("Consultora", metadata.organization),
        ("Referencia", metadata.reference),
    ):
        add(f"{label}: {value.strip() or 'No especificado'}")
    add(f"Generado: {datetime.now().isoformat(timespec='seconds')}")
    add(f"Análisis: {data['analysis_id']}", "ReportSmall")
    add(f"Huella del contenido: {data['snapshot_hash']}", "ReportSmall")
    add("Confidencial. Contiene información de seguridad de los registros proporcionados.")
    heading("Contenido")
    for section in (
        "1. Resumen ejecutivo",
        "2. Alcance, metodología y fuentes",
        "3. Cobertura y limitaciones",
        "4. Hallazgos y plan de acción",
        "5. Correlaciones",
        "6. Recomendaciones generales",
        "7. Anexo de evidencias",
        "8. Configuración y trazabilidad",
    ):
        add(section)
    story.append(PageBreak())
    heading("1. Resumen ejecutivo")
    add(
        f"Se analizaron {summary.get('input_events', 0)} registros. Se identificaron "
        f"{len(data['findings'])} hallazgos sustentados en {len(data['evidence'])} registros "
        f"de evidencia distintos y {len(data['groups'])} grupos para investigar."
    )
    add(
        "Los grupos relacionados no representan un conteo de incidentes confirmados. "
        "Este informe no confirma automáticamente compromiso ni impacto efectivo."
    )
    rows = [[p("Criticidad"), p("Hallazgos")]]
    counts = Counter(f["data"]["severity"] for f in data["findings"])
    rows += [[p(level), p(counts[level])] for level in ("Crítico", "Alto", "Medio", "Bajo")]
    table = LongTable(rows, colWidths=[105 * mm, 65 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7effb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    if data["findings"]:
        add(
            "Prioridad de revisión: validar primero los hallazgos de mayor criticidad, "
            "preservar evidencia y confirmar con el cliente la legitimidad de la actividad."
        )
    else:
        add(
            "No se detectaron hallazgos con las reglas y campos disponibles. "
            "Esto no demuestra ausencia de compromiso."
        )
    add(
        f"Explicaciones de IA disponibles: {ready_ai}/{len(data['findings'])}. "
        + (
            "Se incluyen las completadas y validadas; las restantes usan el análisis del motor."
            if metadata.include_ai
            else "Se excluyeron las explicaciones de IA de esta exportación."
        )
    )
    heading("2. Alcance, metodología y fuentes")
    add(
        "Se incluyen todos los hallazgos del análisis seleccionado, sin aplicar los filtros "
        "del dashboard. Se normalizaron los registros, se evaluaron reglas y se correlacionaron "
        "evidencias. Las fechas conservan la interpretación de los registros del archivo."
    )
    add(
        "La clasificación procede de reglas y contexto verificable. La IA local organiza "
        "explicaciones previamente validadas; no añade evidencias ni confirma incidentes."
    )
    for n, source in enumerate(data["sources"], 1):
        add(f"Fuente {n}: {source['name']}", "ReportHeading")
        add(f"SHA-256 verificado al exportar: {source['sha256']}", "ReportSmall")
        add(f"Importación: {source['import_id']}", "ReportSmall")
        details(source["summary"])
    heading("3. Cobertura y limitaciones")
    add(summary.get("limitations", "Revisión humana requerida."))
    add(
        f"Registros interpretados: {summary.get('recognized_events', 'No registrado')}; "
        f"sin interpretación reconocida: {summary.get('unknown_events', 'No registrado')}; "
        f"copias sin recuento adicional: {summary.get('duplicate_events', 0)}; "
        f"excluidos: {summary.get('excluded_events', 0)}; "
        f"filas rechazadas: {summary.get('import_rejected_rows', 0)}."
    )
    status_labels = {
        "evaluated": "Evaluada",
        "partial": "Parcial",
        "not_evaluable": "No evaluable",
        "not_applicable": "No aplicable",
    }
    for rule in summary.get("coverage", []):
        add(
            f"{rule['title']}: {status_labels.get(rule['status'], rule['status'])}. "
            f"Eventos evaluables: {rule['eligible_events']}; hallazgos: {rule['findings']}."
        )
        if rule.get("excluded_reasons"):
            add(f"Motivos y cantidades: {text(rule['excluded_reasons'])}", "ReportSmall")
    add(
        "La puntuación expresa prioridad por política, no probabilidad de compromiso. "
        "El posible impacto y las acciones propuestas requieren validar contexto, "
        "autorización y alcance con el cliente antes de ejecutarse."
    )
    heading("4. Hallazgos y plan de acción")
    for finding in data["findings"]:
        f = finding["data"]
        heading(f"{finding['label']} | {f['severity']} | {f['title']}")
        add(f"ID: {finding['id']} | Regla: {f['rule_id']}", "ReportSmall")
        add(
            f"Confianza de la inferencia: {f.get('confidence', 'No registrada')}; "
            f"puntuación de prioridad: {f.get('risk_score', 'No registrada')}."
        )
        add(f"Justificación de criticidad: {f.get('severity_reason') or f.get('reason')}")
        add(f"Explicación técnica: {f.get('reason')}")
        add(f"Periodo: {f.get('start') or 'No registrado'} a {f.get('end') or 'No registrado'}")
        add(f"Referencia MITRE ATT&CK: {f.get('attack_reference') or 'No asignada'}")
        add("Hechos observados", "ReportHeading")
        details(f.get("observed", {}))
        add("Limitaciones", "ReportHeading")
        details(f.get("limitations", []))
        add("Posible impacto (hipótesis para validar)", "ReportHeading")
        details(f.get("potential_impact", []))
        add("Plan de acción propuesto", "ReportHeading")
        actions = f.get("actions", {})
        if isinstance(actions, dict):
            for phase, label in (
                ("investigate", "Investigar"),
                ("contain", "Contener"),
                ("remediate", "Remediar"),
            ):
                add(label, "ReportHeading")
                details(actions.get(phase, "Validar con el responsable del incidente."))
        else:
            add("Investigar", "ReportHeading")
            details(actions)
            add("Contener (si se valida actividad no autorizada)", "ReportHeading")
            add(
                "Acordar con el responsable del incidente una contención proporcional: "
                "revocar sesiones o aislar los activos implicados según la evidencia, "
                "preservando registros y considerando el impacto operativo."
            )
            add("Remediar (tras confirmar causa y alcance)", "ReportHeading")
            add(
                "Corregir la causa validada, revisar credenciales y permisos afectados, "
                "restaurar controles cuando corresponda y verificar que la actividad no se repita."
            )
        if metadata.include_ai and finding["ai"]:
            ai = finding["ai"]
            add("Apoyo de IA local - explicación validada estructuralmente", "ReportHeading")
            details(ai["result"].get("explanation", []))
            add(f"Modelo: {ai['model']} | Versión: {ai['version']}", "ReportSmall")
            add(f"Digest: {ai['digest']} | Entrada: {ai['input_hash']}", "ReportSmall")
        add(f"Evidencias ({len(finding['evidence'])}), ver anexo:", "ReportHeading")
        for start in range(0, len(finding["evidence"]), 20):
            add(
                "; ".join(
                    f"{ref['evidence']} ({ref['role']})"
                    for ref in finding["evidence"][start : start + 20]
                ),
                "ReportSmall",
            )
    heading("5. Correlaciones")
    labels = {f["id"]: f["label"] for f in data["findings"]}
    for n, group in enumerate(data["groups"], 1):
        add(
            f"Grupo {n}: " + ", ".join(labels.get(i, i) for i in group["finding_ids"]),
            "ReportHeading",
        )
        add(group["interpretation"])
        details(group.get("links", []))
    heading("6. Recomendaciones generales")
    add(
        "Las siguientes medidas son recomendaciones preventivas; no describen controles "
        "ausentes ni deficiencias demostradas por los registros."
    )
    for recommendation in (
        "Preservar archivos originales y hashes; documentar decisiones y la cadena de custodia.",
        "Validar usuarios, activos, cambios autorizados y contexto operativo con el cliente.",
        "Contrastar hallazgos con telemetría de endpoint, identidad y red cuando esté disponible.",
        "Revisar MFA, mínimo privilegio, protección de respaldos y retención de auditoría.",
        "Definir responsables, plazos y criterios de cierre; "
        "verificar la eficacia de la remediación.",
    ):
        add(recommendation)
    story.append(PageBreak())
    heading("7. Anexo de evidencias")
    add(
        "Se incluyen todos los registros de evidencia distintos citados por los hallazgos. "
        "Los valores son los campos normalizados conservados en la importación. "
        "Se omiten los campos vacíos para facilitar la lectura. "
        "El original completo se localiza por archivo, importación, hoja y fila. "
        "Los caracteres fuera de Latin-1 se representan como [U+XXXX]."
    )
    source_names = {s["import_id"]: s["name"] for s in data["sources"]}
    for event in data["evidence"]:
        heading(f"{event['label']} | {source_names[event['import_id']]}")
        add(f"Hoja: {event['sheet']} | Fila: {event['row']} | Línea final: {event['line_end']}")
        add(f"Evento: {event['id']} | Importación: {event['import_id']}", "ReportSmall")
        for key, value in event["values"].items():
            if value is None or value == "":
                continue
            # Split very long cells across flowables so no paragraph exceeds a page.
            literal = text(value)
            for offset in range(0, max(1, len(literal)), 1400):
                label = key + (" (continuación)" if offset else "")
                add(f"{label}: {literal[offset : offset + 1400]}", "ReportSmall")
        if event["warnings"]:
            add(f"Advertencias de importación: {text(event['warnings'])}", "ReportSmall")
    story.append(PageBreak())
    heading("8. Configuración y trazabilidad")
    add(f"Plantilla: {VERSION}")
    add(f"Huella de entrada del análisis: {data['input_hash']}", "ReportSmall")
    add(f"Huella del contenido del informe: {data['snapshot_hash']}", "ReportSmall")
    details(data["config"])
    add(
        "La huella del contenido identifica la instantánea consultada, incluidas las "
        "explicaciones de IA disponibles. No constituye una firma digital ni una revisión humana."
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(20 * mm, 17 * mm, 190 * mm, 17 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(20 * mm, 12 * mm, "SOC Analyst AI | Confidencial")
        canvas.drawRightString(190 * mm, 12 * mm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        stream,
        pagesize=(210 * mm, 297 * mm),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=24 * mm,
        title="Informe técnico de seguridad",
        author=metadata.analyst.strip(),
        subject="Hallazgos sustentados en registros SIEM",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output = stream.getvalue()
    if len(output) > MAX_BYTES:
        raise HTTPException(413, "El PDF supera 20 MiB. Reduce el alcance.")
    return output


def router_for(engine, storage):
    router = APIRouter(prefix="/api/v1")

    @router.get("/analyses/{analysis_id}/report")
    def preview(analysis_id: uuid.UUID):
        with Session(engine) as db:
            return snapshot(db, storage, analysis_id)

    @router.post("/analyses/{analysis_id}/report/pdf")
    def download(analysis_id: uuid.UUID, payload: ReportInput):
        with Session(engine) as db:
            data = snapshot(db, storage, analysis_id)
        if payload.snapshot_hash and payload.snapshot_hash != data["snapshot_hash"]:
            raise HTTPException(
                409, "El contenido cambió desde la vista previa. Actualízala antes de descargar."
            )
        pdf = render_pdf(data, payload)
        return Response(
            pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="informe-soc-{analysis_id}.pdf"',
                "X-Report-Snapshot": data["snapshot_hash"],
                "X-Content-SHA256": hashlib.sha256(pdf).hexdigest(),
            },
        )

    return router
