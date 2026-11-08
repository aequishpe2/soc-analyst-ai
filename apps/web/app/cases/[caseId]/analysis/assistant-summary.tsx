"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";

type Item = {
  finding_id: string;
  title: string;
  severity: string;
  draft: null | {
    status: string;
    error: string | null;
    result: null | {
      explanation: string[];
      evidence_count: number;
      risk_reason?: string | null;
      plan: Record<string, string[]>;
    };
  };
};
type State = {
  total: number;
  counts: Record<string, number>;
  not_requested: number;
  items: Item[];
};
export default function AssistantSummary({
  analysisId,
}: {
  analysisId: string;
}) {
  const [data, setData] = useState<State | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const state = await api<State>(
          `analyses/${analysisId}/assistant?offset=${offset}`,
        );
        if (disposed) return;
        setData(state);
        setError("");
        if ((state.counts.queued ?? 0) + (state.counts.running ?? 0) > 0)
          timer = setTimeout(load, 2000);
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [analysisId, offset, tick]);
  async function retry() {
    setBusy(true);
    setError("");
    try {
      await api(`analyses/${analysisId}/assistant`, { method: "POST" });
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="assistant-summary"
      id="ai-summary"
      aria-label="Explicaciones con IA local"
    >
      <div className="panel-title">
        <div>
          <p className="eyebrow">OLLAMA · QWEN3:8B</p>
          <h3>Explicaciones con IA local</h3>
        </div>
        <span className="badge">BORRADOR PARA REVISIÓN</span>
      </div>
      <p className="muted">
        La IA organiza explicaciones y planes de acción basados en los
        hallazgos. La clasificación conserva la evidencia y las limitaciones del
        motor.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}{" "}
          <button className="secondary" onClick={() => setTick((t) => t + 1)}>
            Consultar de nuevo
          </button>
        </p>
      )}
      {!data && !error && <p role="status">Consultando el estado de la IA…</p>}
      {data && (
        <>
          {!data.total ? (
            <p>
              No hay hallazgos para explicar. Consulta la actividad importada y
              la cobertura.
            </p>
          ) : (
            <>
              <p role="status" className="notice">
                {data.counts.succeeded ?? 0} de {data.total} explicaciones
                listas · {data.counts.running ?? 0} en curso ·{" "}
                {data.counts.queued ?? 0} pendientes · {data.counts.failed ?? 0}{" "}
                con error.
              </p>
              {(data.not_requested > 0 || (data.counts.failed ?? 0) > 0) && (
                <button className="secondary" disabled={busy} onClick={retry}>
                  {busy
                    ? "Solicitando…"
                    : "Completar o reintentar explicaciones"}
                </button>
              )}
              {data.items.map((item) => (
                <article className="assistant-item" key={item.finding_id}>
                  <div className="panel-title">
                    <h4>{item.title}</h4>
                    <span
                      className={`risk risk-${item.severity.toLowerCase()}`}
                    >
                      {item.severity}
                    </span>
                  </div>
                  {item.draft?.status === "succeeded" && item.draft.result ? (
                    <>
                      {item.draft.result.risk_reason && (
                        <p className="risk-rationale">
                          {item.draft.result.risk_reason}
                        </p>
                      )}
                      {item.draft.result.explanation.map((text, i) => (
                        <p key={i}>{text}</p>
                      ))}
                      <details>
                        <summary>
                          Plan para investigar, contener y remediar
                        </summary>
                        {Object.entries(item.draft.result.plan).map(
                          ([key, actions]) => (
                            <div key={key}>
                              <h4>
                                {{
                                  investigate: "Investigar",
                                  contain: "Contener si se confirma compromiso",
                                  remediate: "Remediar tras validar la causa",
                                }[key] ?? key}
                              </h4>
                              <ul>
                                {actions.map((a) => (
                                  <li key={a}>{a}</li>
                                ))}
                              </ul>
                            </div>
                          ),
                        )}
                      </details>
                      <p className="muted">
                        {item.draft.result.evidence_count} registros vinculados.
                        Puedes comprobar las referencias originales al
                        investigar el hallazgo.
                      </p>
                    </>
                  ) : (
                    <p className="muted">
                      {item.draft?.status === "running"
                        ? "La IA está preparando esta explicación…"
                        : item.draft?.status === "failed"
                          ? item.draft.error
                          : "Explicación pendiente."}
                    </p>
                  )}
                </article>
              ))}
              {data.total > 20 && (
                <div className="pagination">
                  <button
                    disabled={!offset}
                    onClick={() => setOffset(offset - 20)}
                  >
                    Anteriores
                  </button>
                  <span>
                    {offset + 1}–{Math.min(offset + 20, data.total)} /{" "}
                    {data.total}
                  </span>
                  <button
                    disabled={offset + 20 >= data.total}
                    onClick={() => setOffset(offset + 20)}
                  >
                    Siguientes
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
