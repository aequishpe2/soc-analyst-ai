"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";
import { OriginalEvidence } from "./evidence";

type Citation = {
  event_id: string;
  file_name: string;
  sha256: string;
  sheet: string;
  row: number;
  line_end: number;
};
type Draft = {
  id: string;
  status: string;
  model: string;
  version: string;
  model_digest: string | null;
  input_hash: string | null;
  error: string | null;
  result: {
    explanation: string[];
    severity: string;
    confidence: string;
    plan: Record<"investigate" | "contain" | "remediate", string[]>;
    citations: Citation[];
    evidence_count: number;
    method: string;
  } | null;
};
const phases = {
  investigate: "Investigar",
  contain: "Contener · si se confirma actividad no autorizada",
  remediate: "Remediar · después de validar la causa",
};

export default function AIDraft({
  caseId,
  analysisId,
  findingId,
}: {
  caseId: string;
  analysisId: string;
  findingId: string;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const [eventId, setEventId] = useState("");
  const path = `analyses/${analysisId}/findings/${findingId}/draft`;
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await api<{ draft: Draft | null }>(path);
        if (disposed) return;
        setDraft(data.draft);
        setError("");
        if (data.draft && ["queued", "running"].includes(data.draft.status))
          timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [path, tick]);

  async function generate() {
    setSending(true);
    setError("");
    try {
      const data = await api<{ draft: Draft }>(path, { method: "POST" });
      setDraft(data.draft);
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  const running = !!draft && ["queued", "running"].includes(draft.status);
  return (
    <section className="ai-draft" aria-label="Asistente de IA local">
      <div className="panel-title">
        <h4>Asistente de IA local</h4>
        <span className="badge">Ollama · Qwen3:8b</span>
      </div>
      <p className="muted">
        Organiza una explicación y un plan con contenido validado del hallazgo.
        Procesamiento local, sin enviar registros originales al modelo.
      </p>
      {loading && <p role="status">Consultando borrador…</p>}
      {error && (
        <p className="error" role="alert">
          {error}{" "}
          <button className="secondary" onClick={() => setTick((t) => t + 1)}>
            Consultar de nuevo
          </button>
        </p>
      )}
      {!loading && !error && (!draft || draft.status === "failed") && (
        <button disabled={sending} onClick={generate}>
          {sending
            ? "Solicitando…"
            : draft
              ? "Reintentar borrador con IA"
              : "Preparar borrador con IA"}
        </button>
      )}
      {draft?.error && (
        <p className="error" role="alert">
          {draft.error}
        </p>
      )}
      {running && (
        <p role="status">
          {draft.status === "queued"
            ? "Borrador en cola…"
            : "La IA está preparando el borrador…"}{" "}
          Puedes continuar revisando las evidencias. La generación tiene un
          límite de tres minutos.
        </p>
      )}
      {draft?.status === "succeeded" && draft.result && (
        <>
          <p className="ai-review">Borrador para revisión del analista</p>
          <p className="muted">
            Criticidad {draft.result.severity} · Confianza{" "}
            {draft.result.confidence}
          </p>
          {draft.result.explanation.map((text, i) => (
            <p key={i}>{text}</p>
          ))}
          {(Object.keys(phases) as (keyof typeof phases)[]).map((phase) => (
            <div key={phase}>
              <h4>{phases[phase]}</h4>
              <ol>
                {draft.result!.plan[phase].map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ol>
            </div>
          ))}
          <h4>Evidencias citadas</h4>
          <p className="muted">
            {draft.result.citations.length} referencias seleccionadas de{" "}
            {draft.result.evidence_count} registros vinculados al hallazgo. El
            conjunto completo está en la tabla de evidencias.
          </p>
          <ul className="ai-citations">
            {draft.result.citations.map((ref) => (
              <li key={ref.event_id}>
                <button
                  className="secondary"
                  onClick={() =>
                    setEventId(eventId === ref.event_id ? "" : ref.event_id)
                  }
                >
                  {ref.file_name} · {ref.sheet} · fila {ref.row}
                  {ref.line_end !== ref.row ? `–${ref.line_end}` : ""}
                </button>
              </li>
            ))}
          </ul>
          {eventId && (
            <OriginalEvidence key={eventId} caseId={caseId} eventId={eventId} />
          )}
          <details>
            <summary>Método y trazabilidad del borrador</summary>
            <p>{draft.result.method}</p>
            <dl className="ai-trace">
              <dt>Modelo</dt>
              <dd>{draft.model}</dd>
              <dt>Versión</dt>
              <dd>{draft.version}</dd>
              <dt>Huella del modelo</dt>
              <dd>{draft.model_digest}</dd>
              <dt>Huella de entrada</dt>
              <dd>{draft.input_hash}</dd>
            </dl>
          </details>
        </>
      )}
    </section>
  );
}
