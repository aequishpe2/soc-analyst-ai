"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";

type Technique = {
  id: string;
  name: string;
  url: string;
  count: number;
  severity: string;
  by_severity: Record<string, number>;
};
type Matrix = {
  release: string;
  total_findings: number;
  mapped_findings: number;
  unmapped_findings: number;
  unmapped_reasons: Record<string, number>;
  interpretation: string;
  techniques: Technique[];
  tactics: {
    id: string;
    label: string;
    name: string;
    url: string;
    techniques: Technique[];
  }[];
};

export default function AttackMatrix({
  analysisId,
  query,
  selected,
  onSelect,
}: {
  analysisId: string;
  query: string;
  selected: string;
  onSelect: (value: string) => void;
}) {
  const [data, setData] = useState<Matrix | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const params = new URLSearchParams(query);
  params.delete("technique_id");
  const matrixQuery = params.toString();
  useEffect(() => {
    let disposed = false;
    setData(null);
    setError("");
    api<Matrix>(`analyses/${analysisId}/attack-matrix?${matrixQuery}`)
      .then((value) => {
        if (!disposed) setData(value);
      })
      .catch((e) => {
        if (!disposed) setError((e as Error).message);
      });
    return () => {
      disposed = true;
    };
  }, [analysisId, matrixQuery, tick]);
  function select(id: string) {
    onSelect(selected === id ? "" : id);
    document
      .getElementById("findings")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return (
    <section
      className="attack-matrix panel"
      id="attack-matrix"
      aria-label="Matriz MITRE ATT&CK"
    >
      <div className="panel-title">
        <div>
          <p className="eyebrow">CONTEXTO DE LOS HALLAZGOS</p>
          <h3>MITRE ATT&CK · Matriz Enterprise</h3>
        </div>
        {data && <span className="badge">CATÁLOGO {data.release} · LOCAL</span>}
      </div>
      <p className="muted">
        Relaciona los hallazgos con tácticas y técnicas del catálogo oficial. No
        confirma su ejecución ni una cadena de ataque. Pulsa una técnica para
        consultar los hallazgos y abrir sus evidencias.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}{" "}
          <button onClick={() => setTick((t) => t + 1)}>Reintentar</button>
        </p>
      )}
      {!data && !error && <p role="status">Preparando matriz…</p>}
      {data && (
        <>
          <div className="attack-stats">
            <span>
              <strong>{data.techniques.length}</strong> técnicas relacionadas
            </span>
            <span>
              <strong>{data.mapped_findings}</strong> hallazgos con referencia
              activa
            </span>
            <span>
              <strong>{data.unmapped_findings}</strong> sin referencia activa
            </span>
          </div>
          {selected && (
            <p className="notice">
              Técnica seleccionada: {selected}.{" "}
              <button className="secondary" onClick={() => onSelect("")}>
                Quitar filtro MITRE
              </button>
            </p>
          )}
          <p className="muted">
            La matriz respeta los filtros de criticidad, regla, fechas, usuario,
            equipo y grupo. Conserva sus columnas al seleccionar una técnica.
            Desplázate horizontalmente para ver todas las tácticas.
          </p>
          <div
            className="attack-scroll"
            tabIndex={0}
            role="region"
            aria-label="Columnas de tácticas MITRE"
          >
            <div className="attack-columns">
              {data.tactics.map((tactic) => (
                <article className="attack-column" key={tactic.id}>
                  <header>
                    <a
                      href={tactic.url}
                      target="_blank"
                      rel="noreferrer"
                      title={tactic.name}
                    >
                      {tactic.label}
                    </a>
                    <small>{tactic.id}</small>
                  </header>
                  {!tactic.techniques.length && (
                    <p className="muted attack-empty">
                      Sin referencias en esta vista
                    </p>
                  )}
                  {tactic.techniques.map((technique) => (
                    <div
                      key={technique.id}
                      className="attack-cell"
                      data-severity={technique.severity}
                    >
                      <button
                        type="button"
                        aria-pressed={selected === technique.id}
                        onClick={() => select(technique.id)}
                        aria-label={`${tactic.label}: ${technique.id} ${technique.name}, ${technique.count} hallazgos`}
                      >
                        <strong>{technique.id}</strong>
                        <span>{technique.name}</span>
                        <small>
                          {technique.count} hallazgos · prioridad{" "}
                          {technique.severity}
                        </small>
                      </button>
                      <a
                        href={technique.url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Referencia oficial ${technique.id}`}
                      >
                        Ver en MITRE ↗
                      </a>
                    </div>
                  ))}
                </article>
              ))}
            </div>
          </div>
          <p className="muted">{data.interpretation}</p>
          {data.unmapped_findings > 0 && (
            <details>
              <summary>
                Hallazgos sin referencia activa ({data.unmapped_findings})
              </summary>
              <ul>
                {Object.entries(data.unmapped_reasons).map(
                  ([reason, count]) => (
                    <li key={reason}>
                      {(
                        {
                          missing_reference: "Sin técnica asignada",
                          unknown_reference:
                            "Referencia no incluida en el catálogo local",
                          inactive_reference:
                            "Referencia retirada o descontinuada por MITRE",
                        } as Record<string, string>
                      )[reason] ?? reason}
                      : {count}
                    </li>
                  ),
                )}
              </ul>
              <p>
                Se conservan en el análisis y sus evidencias. No se les asigna
                una técnica nueva automáticamente.
              </p>
            </details>
          )}
          <a
            className="muted"
            href="https://attack.mitre.org/matrices/enterprise/"
            target="_blank"
            rel="noreferrer"
          >
            Fuente: MITRE ATT&CK® Enterprise ↗
          </a>
        </>
      )}
    </section>
  );
}
