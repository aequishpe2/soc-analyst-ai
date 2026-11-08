"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";

type Count = { value: string; count: number; title?: string };
type Data = {
  input_activity: {
    events: number;
    users: number;
    command_events: number;
    event_codes: Count[];
    evaluable_rules: number;
  };
  total: number;
  groups: number;
  evidence_events: number;
  by_severity: Count[];
  by_rule: Count[];
  timeline: Count[];
  undated: number;
  top_users: Count[];
  top_hosts: Count[];
};
const colors: Record<string, string> = {
  Crítico: "#ff8097",
  Alto: "#ffb47a",
  Medio: "#e7cc73",
  Bajo: "#6de6b9",
};

function Bars({
  items,
  selected,
  onSelect,
  empty,
}: {
  items: Count[];
  selected: string;
  onSelect: (value: string) => void;
  empty: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (!items.length) return <p className="muted">{empty}</p>;
  return (
    <ul className="dashboard-bars">
      {items.map((item) => (
        <li key={item.value}>
          <button
            type="button"
            aria-pressed={selected === item.value}
            onClick={() => onSelect(selected === item.value ? "" : item.value)}
            title={`${item.title ?? item.value}: ${item.count} hallazgos`}
          >
            <span className="bar-caption">
              <span>{item.title ?? item.value}</span>
              <strong>{item.count}</strong>
            </span>
            <span className="bar-track" aria-hidden="true">
              <span style={{ width: `${(item.count / max) * 100}%` }} />
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function Dashboard({
  analysisId,
  query,
  severity,
  rule,
  user,
  host,
  day,
  onSeverity,
  onRule,
  onUser,
  onHost,
  onDay,
}: {
  analysisId: string;
  query: string;
  severity: string;
  rule: string;
  user: string;
  host: string;
  day: string;
  onSeverity: (value: string) => void;
  onRule: (value: string) => void;
  onUser: (value: string) => void;
  onHost: (value: string) => void;
  onDay: (value: string) => void;
}) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let ignore = false;
    setData(null);
    setError("");
    api<Data>(`analyses/${analysisId}/dashboard?${query}`)
      .then((result) => {
        if (!ignore) setData(result);
      })
      .catch((e) => {
        if (!ignore) setError((e as Error).message);
      });
    return () => {
      ignore = true;
    };
  }, [analysisId, query, tick]);
  if (error)
    return (
      <div role="alert" className="error">
        {error}{" "}
        <button className="secondary" onClick={() => setTick((t) => t + 1)}>
          Reintentar dashboard
        </button>
      </div>
    );
  if (!data) return <p role="status">Cargando estadísticas del análisis…</p>;
  let cursor = 0;
  const stops = data.by_severity.map((s) => {
    const start = cursor;
    cursor += data.total ? (s.count / data.total) * 100 : 0;
    return `${colors[s.value]} ${start}% ${cursor}%`;
  });
  const timeline = data.timeline.slice(-90);
  const maxDay = Math.max(1, ...timeline.map((t) => t.count));
  return (
    <section
      className="dashboard"
      aria-label="Dashboard interactivo de hallazgos"
    >
      <section
        className="dashboard-input"
        aria-label="Actividad de los registros importados"
      >
        <h4>Datos del archivo · análisis completo</h4>
        <div className="dashboard-stats">
          <div>
            <span>Registros importados</span>
            <strong>{data.input_activity.events}</strong>
          </div>
          <div>
            <span>Usuarios registrados</span>
            <strong>{data.input_activity.users}</strong>
          </div>
          <div>
            <span>Registros con comando mapeado</span>
            <strong>{data.input_activity.command_events}</strong>
          </div>
          <div>
            <span>Reglas con eventos evaluables</span>
            <strong>{data.input_activity.evaluable_rules} / 8</strong>
          </div>
        </div>
        {data.input_activity.event_codes.length > 0 && (
          <p className="muted">
            IDs de evento registrados (hasta ocho):{" "}
            {data.input_activity.event_codes
              .map((c) => `${c.value}: ${c.count}`)
              .join(" · ")}
            . Estos conteos describen la entrada y no son alertas.
          </p>
        )}
      </section>
      <p className="muted">
        Vista filtrada · Los gráficos consideran todos los hallazgos
        coincidentes, incluidas las otras páginas. Pulsa una categoría para
        filtrar; vuelve a pulsarla para quitar ese filtro.
      </p>
      <div className="dashboard-stats">
        <div>
          <span>Hallazgos</span>
          <strong>{data.total}</strong>
        </div>
        <div>
          <span>Registros de evidencia únicos</span>
          <strong>{data.evidence_events}</strong>
        </div>
        <div>
          <span>Grupos relacionados</span>
          <strong>{data.groups}</strong>
        </div>
        <div>
          <span>Hallazgos sin fecha de inicio</span>
          <strong>{data.undated}</strong>
        </div>
      </div>
      {!data.total && (
        <p className="info-note">
          {data.input_activity.evaluable_rules === 0
            ? "No se pudo evaluar ninguna regla. Revisa el mapeo y el proveedor antes de interpretar este resultado."
            : query
              ? "No hay hallazgos para estos filtros. Amplía la selección o consulta la cobertura del análisis."
              : "Las reglas evaluables no encontraron coincidencias. Consulta la cobertura para ver qué condiciones no pudieron comprobarse."}
        </p>
      )}
      <div className="dashboard-grid">
        <section
          className="dashboard-chart"
          aria-label="Distribución por criticidad"
        >
          <h4>Distribución por criticidad</h4>
          <div className="severity-chart">
            <div
              className="risk-donut"
              role="img"
              aria-label={data.by_severity
                .map((s) => `${s.value}: ${s.count}`)
                .join(", ")}
              style={{
                background: data.total
                  ? `conic-gradient(${stops.join(",")})`
                  : "var(--line)",
              }}
            >
              <div>
                <strong>{data.total}</strong>
                <span>hallazgos</span>
              </div>
            </div>
            <ul className="risk-legend">
              {data.by_severity.map((s) => (
                <li key={s.value}>
                  <button
                    type="button"
                    aria-pressed={severity === s.value}
                    onClick={() =>
                      onSeverity(severity === s.value ? "" : s.value)
                    }
                  >
                    <span
                      className="legend-dot"
                      style={{ background: colors[s.value] }}
                      aria-hidden="true"
                    />
                    <span>{s.value}</span>
                    <strong>{s.count}</strong>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
        <section className="dashboard-chart" aria-label="Hallazgos por regla">
          <h4>Hallazgos por regla</h4>
          <Bars
            items={data.by_rule}
            selected={rule}
            onSelect={onRule}
            empty="Sin reglas evaluadas."
          />
        </section>
        <section
          className="dashboard-chart dashboard-timeline"
          aria-label="Línea de tiempo por fecha de inicio"
        >
          <h4>Hallazgos por fecha de inicio</h4>
          <p className="muted">
            Distribución diaria según la fecha del hallazgo; no implica relación
            entre archivos. Pulsa un día para consultar sus hallazgos.
          </p>
          {data.timeline.length > 90 && (
            <p className="muted">
              Se muestran las últimas 90 fechas con hallazgos de{" "}
              {data.timeline.length}. Usa el periodo para consultar las
              anteriores.
            </p>
          )}
          {!timeline.length ? (
            <p className="muted">Sin fechas disponibles para esta selección.</p>
          ) : (
            <div className="timeline-scroll">
              <div className="timeline-bars">
                {timeline.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    title={`${t.value}: ${t.count} hallazgos`}
                    aria-label={`${t.value}: ${t.count} hallazgos`}
                    aria-pressed={day === t.value}
                    onClick={() => onDay(day === t.value ? "" : t.value)}
                  >
                    <strong>{t.count}</strong>
                    <span className="timeline-column" aria-hidden="true">
                      <span
                        style={{ height: `${(t.count / maxDay) * 100}%` }}
                      />
                    </span>
                    <span>{t.value}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
        <section
          className="dashboard-chart"
          aria-label="Usuarios con más hallazgos"
        >
          <h4>Usuarios con más hallazgos</h4>
          <p className="muted">
            Hasta ocho usuarios de las evidencias vinculadas. Incluye cuenta de
            origen o de destino.
          </p>
          <Bars
            items={data.top_users}
            selected={user}
            onSelect={onUser}
            empty="Las evidencias no identifican usuarios."
          />
        </section>
        <section
          className="dashboard-chart"
          aria-label="Equipos con más hallazgos"
        >
          <h4>Equipos con más hallazgos</h4>
          <p className="muted">
            Hasta ocho equipos de origen o destino registrados en las
            evidencias.
          </p>
          <Bars
            items={data.top_hosts}
            selected={host}
            onSelect={onHost}
            empty="Las evidencias no identifican nombres de equipos."
          />
        </section>
      </div>
      <p className="muted">
        Un registro puede sustentar varios hallazgos y un hallazgo puede
        involucrar varias entidades. Las cifras de usuarios y equipos no se
        suman como incidentes.
      </p>
    </section>
  );
}
