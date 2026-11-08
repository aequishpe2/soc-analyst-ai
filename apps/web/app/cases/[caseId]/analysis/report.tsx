"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";

type Report = {
  title: string;
  snapshot_hash: string;
  summary: {
    input_events: number;
    unknown_events?: number;
    limitations: string;
    coverage: {
      rule_id: string;
      title: string;
      status: string;
      eligible_events: number;
    }[];
  };
  sources: { name: string; sha256: string; import_id: string }[];
  findings: {
    id: string;
    label: string;
    data: {
      title: string;
      severity: string;
      severity_reason?: string;
      reason: string;
      limitations: string;
      potential_impact: string;
      actions: string[];
    };
    evidence: { evidence: string; role: string }[];
    ai: null | { result: { explanation: string[] } };
  }[];
  evidence: {
    id: string;
    label: string;
    import_id: string;
    sheet: string;
    row: number;
    values: Record<string, unknown>;
  }[];
  groups: unknown[];
};

export default function TechnicalReport({
  analysisId,
}: {
  analysisId: string;
}) {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);
  const [tick, setTick] = useState(0);
  const [metadata, setMetadata] = useState({
    analyst: "",
    client: "",
    organization: "",
    reference: "",
    include_ai: true,
  });
  useEffect(() => {
    if (!preview) return;
    let disposed = false;
    setData(null);
    setError("");
    api<Report>(`analyses/${analysisId}/report`)
      .then((result) => {
        if (!disposed) setData(result);
      })
      .catch((e) => {
        if (!disposed) setError((e as Error).message);
      });
    return () => {
      disposed = true;
    };
  }, [analysisId, preview, tick]);

  async function download() {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/v1/analyses/${analysisId}/report/pdf`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...metadata,
            snapshot_hash: data.snapshot_hash,
          }),
        },
      );
      if (!response.ok) {
        const problem = await response.json();
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : (problem.message ?? "No se pudo generar el PDF."),
        );
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `informe-soc-${analysisId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      id="technical-report"
      className="panel technical-report"
      aria-label="Informe técnico"
    >
      <div className="panel-title">
        <div>
          <p className="eyebrow">DOCUMENTACIÓN DEL CASO</p>
          <h3>Informe técnico de seguridad</h3>
        </div>
        <span className="badge">REVISIÓN HUMANA PENDIENTE</span>
      </div>
      <p className="muted">
        Resumen ejecutivo, hallazgos, criticidad justificada, impacto posible,
        plan de acción y anexo de evidencias. Incluye el análisis completo, sin
        los filtros del dashboard.
      </p>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => {
          setPreview(true);
          if (preview) setTick((t) => t + 1);
        }}
      >
        {preview ? "Actualizar vista previa" : "Preparar informe"}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {preview && !data && !error && (
        <p role="status">Verificando las fuentes y reuniendo evidencias…</p>
      )}
      {data && (
        <>
          <div className="report-fields">
            {(
              [
                ["analyst", "Analista", 150],
                ["client", "Cliente", 200],
                ["organization", "Consultora", 200],
                ["reference", "Referencia", 100],
              ] as const
            ).map(([key, label, max]) => (
              <label key={key}>
                {label} (opcional)
                <input
                  maxLength={max}
                  value={metadata[key]}
                  onChange={(e) =>
                    setMetadata({ ...metadata, [key]: e.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={metadata.include_ai}
              onChange={(e) =>
                setMetadata({ ...metadata, include_ai: e.target.checked })
              }
            />{" "}
            Incluir explicaciones de IA completadas y validadas
          </label>
          <div className="report-preview">
            <h4>Resumen ejecutivo · {data.title}</h4>
            <p>
              {data.summary.input_events} registros · {data.findings.length}{" "}
              hallazgos · {data.evidence.length} evidencias distintas ·{" "}
              {data.groups.length} grupos para investigar.
            </p>
            <div className="report-risk-summary">
              {["Crítico", "Alto", "Medio", "Bajo"].map((level) => (
                <span key={level}>
                  <strong>
                    {
                      data.findings.filter((f) => f.data.severity === level)
                        .length
                    }
                  </strong>{" "}
                  {level}
                </span>
              ))}
            </div>
            <p>{data.summary.limitations}</p>
            <p className="muted">
              Los grupos no equivalen a incidentes confirmados. La puntuación
              expresa prioridad, no probabilidad. Las acciones de contención
              requieren validar la actividad y su autorización.
            </p>
            <p>
              IA disponible: {data.findings.filter((f) => f.ai).length}/
              {data.findings.length}.{" "}
              {metadata.include_ai
                ? "Se incluirán las explicaciones disponibles al preparar esta vista previa."
                : "Las explicaciones de IA se excluirán del PDF."}
            </p>
            <details>
              <summary>Alcance, fuentes y cobertura</summary>
              {data.sources.map((s) => (
                <div key={s.import_id}>
                  <p>{s.name}</p>
                  <code className="report-hash">SHA-256: {s.sha256}</code>
                </div>
              ))}
              <p>
                Registros sin interpretación reconocida:{" "}
                {data.summary.unknown_events ?? "No registrado"}.
              </p>
              <ul>
                {data.summary.coverage.map((c) => (
                  <li key={c.rule_id}>
                    {c.title}:{" "}
                    {(
                      {
                        evaluated: "Evaluada",
                        partial: "Parcial",
                        not_evaluable: "No evaluable",
                        not_applicable: "No aplicable",
                      } as Record<string, string>
                    )[c.status] ?? c.status}{" "}
                    · {c.eligible_events} eventos evaluables
                  </li>
                ))}
              </ul>
            </details>
            <details>
              <summary>
                Hallazgos, justificación y acciones ({data.findings.length})
              </summary>
              {data.findings.map((f) => (
                <article key={f.id} className="group-card">
                  <h4>
                    {f.label} · {f.data.severity} · {f.data.title}
                  </h4>
                  <p>{f.data.severity_reason ?? f.data.reason}</p>
                  <p>{f.data.reason}</p>
                  <p>
                    <strong>Limitaciones:</strong> {f.data.limitations}
                  </p>
                  <p>
                    <strong>Posible impacto:</strong> {f.data.potential_impact}
                  </p>
                  <ul>
                    {f.data.actions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                  {metadata.include_ai &&
                    f.ai?.result.explanation.map((a, i) => <p key={i}>{a}</p>)}
                  <p>
                    Evidencias:{" "}
                    {f.evidence
                      .map((e) => `${e.evidence} (${e.role})`)
                      .join("; ")}
                  </p>
                </article>
              ))}
            </details>
            <details>
              <summary>Anexo de evidencias ({data.evidence.length})</summary>
              {data.evidence.map((e) => (
                <div className="group-card" key={e.id}>
                  <h4>
                    {e.label} ·{" "}
                    {
                      data.sources.find((s) => s.import_id === e.import_id)
                        ?.name
                    }{" "}
                    · {e.sheet} · Fila {e.row}
                  </h4>
                  <pre>{JSON.stringify(e.values, null, 2)}</pre>
                </div>
              ))}
            </details>
            <p className="muted report-hash">
              Huella del contenido: {data.snapshot_hash}
            </p>
          </div>
          <button className="primary" disabled={busy} onClick={download}>
            {busy ? "Generando PDF…" : "Descargar informe PDF"}
          </button>
          <p className="muted">
            El documento se descarga como borrador confidencial. Si el contenido
            cambia mientras termina la IA, actualiza la vista previa antes de
            exportar.
          </p>
        </>
      )}
    </section>
  );
}
