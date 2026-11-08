"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";
import AutoUpload from "../../../../lib/auto-upload";
import AnalysisWorkspace from "../analysis/workspace";

type Run = {
  id: string;
  file_id: string;
  status: string;
  phase: string;
  error: string | null;
  result: null | {
    analysis_id?: string;
    ai_status?: string;
    decisions?: { profile: string; date_format: string; notes: string };
  };
};
const steps = [
  ["reading", "Leer archivo"],
  ["mapping", "Reconocer columnas"],
  ["importing", "Preparar registros"],
  ["analyzing", "Detectar y correlacionar"],
  ["ready", "Abrir dashboard"],
];
export default function Overview({
  caseId,
  runId,
}: {
  caseId: string;
  runId?: string;
}) {
  const [title, setTitle] = useState("Investigación");
  const [run, setRun] = useState<Run | null>(null);
  const [analysisId, setAnalysisId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const info = await api<{ title: string }>(`cases/${caseId}`);
        if (disposed) return;
        setTitle(info.title);
        if (runId) {
          const state = await api<Run>(`cases/${caseId}/automatic/${runId}`);
          if (disposed) return;
          setRun(state);
          if (state.status === "succeeded")
            setAnalysisId(state.result?.analysis_id ?? "");
          else if (["queued", "running"].includes(state.status))
            timer = setTimeout(load, 1000);
        } else {
          const history = await api<{
            items: { id: string; status: string }[];
          }>(`cases/${caseId}/analyses?limit=1`);
          if (disposed) return;
          setAnalysisId(history.items[0]?.id ?? "");
        }
        setError("");
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        if (!disposed) setLoading(false);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [caseId, runId, tick]);
  async function retry() {
    if (!run) return;
    try {
      const state = await api<Run>(
        `cases/${caseId}/files/${run.file_id}/automatic`,
        { method: "POST" },
      );
      setRun(state);
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const running = !!run && ["queued", "running"].includes(run.status);
  return (
    <div className="workspace overview-workspace">
      <aside>
        <Link className="brand" href="/">
          <span className="mark">◈</span>
          <span>
            SOC Analyst
            <span className="brand-sub">INTELIGENCIA CON EVIDENCIA</span>
          </span>
        </Link>
        <div className="section-label">ESPACIO DE INVESTIGACIÓN</div>
        <nav
          className="overview-nav"
          aria-label="Navegación de la investigación"
        >
          <a href="#dashboard" className="nav-active">
            ▦ &nbsp; Resumen
          </a>
          <a href="#findings">◎ &nbsp; Hallazgos</a>
          <Link href={`/cases/${caseId}`}>≡ &nbsp; Explorador de eventos</Link>
          <a href="#correlations">◇ &nbsp; Correlaciones</a>
          <a href="#attack-matrix">▦ &nbsp; MITRE ATT&CK</a>
          <a href="#ai-summary">✧ &nbsp; Explicaciones con IA</a>
          <a href="#technical-report">▤ &nbsp; Informe técnico</a>
          <Link href={`/cases/${caseId}/analysis`}>
            ⚙ &nbsp; Ajustes avanzados
          </Link>
        </nav>
        <div className="sidebar-note">
          <span className="dot" />
          Tu evidencia, en tu equipo
          <p>
            Archivos privados y Ollama local. Cada hallazgo conserva sus
            referencias.
          </p>
          <Link href="/">← Todas las investigaciones</Link>
        </div>
      </aside>
      <div className="overview-content">
        <section className="overview-hero">
          <p className="eyebrow">LABORATORIO DE INVESTIGACIÓN · SOC NIVEL 2</p>
          <h1>Explora. Investiga. Comprende.</h1>
          <p>{title}</p>
          <span className="badge">ANÁLISIS LOCAL · EVIDENCIAS TRAZABLES</span>
        </section>
        {running ? (
          <section className="panel auto-progress" role="status">
            <h2>Estamos analizando tu archivo</h2>
            <p>
              El dashboard se abrirá al terminar la detección. Las explicaciones
              con IA continuarán en segundo plano.
            </p>
            <ol>
              {steps.map(([key, label], i) => (
                <li
                  key={key}
                  className={
                    steps.findIndex((s) => s[0] === run.phase) >= i
                      ? "active"
                      : ""
                  }
                >
                  <span>{i + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
          </section>
        ) : (
          <details className="overview-upload" open={!analysisId && !loading}>
            <summary>
              {analysisId
                ? "＋ Cargar otro archivo en este caso"
                : "Cargar archivo para análisis automático"}
            </summary>
            <AutoUpload caseId={caseId} />
          </details>
        )}
        {error && (
          <p className="error" role="alert">
            {error}{" "}
            <button className="secondary" onClick={() => setTick((t) => t + 1)}>
              Consultar de nuevo
            </button>
          </p>
        )}
        {loading && <p role="status">Recuperando investigación…</p>}
        {run && ["failed", "needs_review"].includes(run.status) && (
          <section className="panel" role="alert">
            <h2>
              {run.status === "needs_review"
                ? "El archivo necesita una revisión"
                : "El análisis no pudo completarse"}
            </h2>
            <p>{run.error}</p>
            <Link className="secondary" href={`/cases/${caseId}`}>
              Revisar columnas y fechas
            </Link>
            {run.status === "failed" && (
              <button className="secondary" onClick={retry}>
                Reintentar análisis automático
              </button>
            )}
          </section>
        )}
        {analysisId && !running && (
          <>
            {run?.result?.decisions && (
              <details className="auto-decisions">
                <summary>Cómo se interpretó el archivo automáticamente</summary>
                <p>
                  Perfil:{" "}
                  {run.result.decisions.profile === "windows_security"
                    ? "Windows Security, inferido por el formato"
                    : "Interpretación por registro y proveedor"}{" "}
                  · Formato de fecha: {run.result.decisions.date_format}
                </p>
                <p>{run.result.decisions.notes}</p>
              </details>
            )}
            {run?.result?.ai_status === "unavailable" && (
              <p className="info-note">
                El dashboard está disponible. Ollama no estaba disponible al
                iniciar; puedes solicitar las explicaciones desde la sección de
                IA.
              </p>
            )}
            <AnalysisWorkspace
              key={analysisId}
              caseId={caseId}
              compact
              initialAnalysisId={analysisId}
            />
          </>
        )}
      </div>
    </div>
  );
}
