"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, displayDetails } from "../../../../lib/api";
import FindingEvidence, { OriginalEvidence } from "./evidence";
import AIDraft from "./ai-draft";
import Dashboard from "./dashboard";
import AssistantSummary from "./assistant-summary";
import TechnicalReport from "./report";
import AttackMatrix from "./attack-matrix";
import {
  Analysis,
  Coverage,
  Finding,
  Group,
  Scope,
  Settings,
  statusLabels,
  reasonLabels,
} from "./types";

const thresholds: [keyof Settings, string, number, number][] = [
  ["brute_min", "Fallos mínimos · fuerza bruta", 2, 1000],
  ["brute_window", "Ventana fuerza bruta (segundos)", 30, 3600],
  ["spray_min", "Usuarios distintos · spraying", 2, 1000],
  ["spray_window", "Ventana spraying (segundos)", 30, 3600],
  ["success_min", "Fallos previos a un éxito", 2, 1000],
  ["success_window", "Ventana de fallos y éxito (segundos)", 30, 3600],
  ["lateral_min", "Destinos remotos distintos", 2, 1000],
  ["lateral_window", "Ventana accesos remotos (segundos)", 30, 3600],
  ["correlation_window", "Ventana de correlación (segundos)", 30, 3600],
  ["burst_min", "Fallos mínimos en una ráfaga distribuida", 5, 1000],
  ["burst_window", "Ventana de ráfagas y transferencias (segundos)", 30, 3600],
  [
    "transfer_bytes",
    "Umbral de transferencia POST (bytes)",
    1048576,
    1099511627776,
  ],
];
const emptyFilters = { date_from: "", date_to: "", user: "", host: "" };
function lines(value: string) {
  return value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}
function stamp(value: string) {
  return (
    new Intl.DateTimeFormat("es", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(
      new Date(
        value.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(value)
          ? value
          : value + "Z",
      ),
    ) + ""
  );
}

function CoverageTable({ rows }: { rows: Coverage[] }) {
  return (
    <div className="table-scroll">
      <table>
        <caption>
          Cobertura de {rows.length} reglas · se informa lo que no pudo
          evaluarse
        </caption>
        <thead>
          <tr>
            <th>Regla</th>
            <th>Estado</th>
            <th>Eventos elegibles</th>
            <th>Hallazgos</th>
            <th>Descartes y límites</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.rule_id}>
              <th>{r.title}</th>
              <td>{statusLabels[r.status]}</td>
              <td>{r.eligible_events}</td>
              <td>{r.findings}</td>
              <td>
                {Object.entries(r.excluded_reasons).map(([reason, count]) => (
                  <div key={reason}>
                    {reasonLabels[reason] ?? reason}: {count}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalysisWorkspace({
  caseId,
  compact = false,
  initialAnalysisId = "",
}: {
  caseId: string;
  compact?: boolean;
  initialAnalysisId?: string;
}) {
  const router = useRouter();
  const [currentEngine, setCurrentEngine] = useState("");
  const [title, setTitle] = useState("Investigación");
  const [imports, setImports] = useState<Scope[]>([]);
  const [importsLoading, setImportsLoading] = useState(true);
  const [importsError, setImportsError] = useState(false);
  const [importOffset, setImportOffset] = useState(0);
  const [importTotal, setImportTotal] = useState(0);
  const [selected, setSelected] = useState<Scope[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [catalog, setCatalog] = useState<{ id: string; title: string }[]>([]);
  const [calendar, setCalendar] = useState(false);
  const [weekdays, setWeekdays] = useState([0, 1, 2, 3, 4]);
  const [start, setStart] = useState("08:00");
  const [end, setEnd] = useState("18:00");
  const [excludedUsers, setExcludedUsers] = useState("");
  const [excludedIps, setExcludedIps] = useState("");
  const [privilegedGroups, setPrivilegedGroups] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [windowsConfirmed, setWindowsConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Analysis[]>([]);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [analysisId, setAnalysisId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const [severity, setSeverity] = useState("");
  const [rule, setRule] = useState("");
  const [technique, setTechnique] = useState("");
  const [groupId, setGroupId] = useState("");
  const [filters, setFilters] = useState(emptyFilters);
  const [draftFilters, setDraftFilters] = useState(emptyFilters);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [findingsLoading, setFindingsLoading] = useState(true);
  const [findingsError, setFindingsError] = useState("");
  const [findingTotal, setFindingTotal] = useState(0);
  const [findingOffset, setFindingOffset] = useState(0);
  const [activeFinding, setActiveFinding] = useState("");
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupTotal, setGroupTotal] = useState(0);
  const [groupOffset, setGroupOffset] = useState(0);
  const [duplicates, setDuplicates] = useState<
    { event_id: string; representative_id: string }[]
  >([]);
  const [duplicateOffset, setDuplicateOffset] = useState(0);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [originalId, setOriginalId] = useState("");
  const running =
    busy || (!!analysis && ["queued", "running"].includes(analysis.status));

  const loadHistory = useCallback(async () => {
    const data = await api<{ items: Analysis[]; total: number }>(
      `cases/${caseId}/analyses?offset=${historyOffset}`,
    );
    setHistory(data.items);
    setHistoryTotal(data.total);
    return data.items;
  }, [caseId, historyOffset]);
  useEffect(() => {
    api<{ title: string }>(`cases/${caseId}`)
      .then((c) => {
        setTitle(c.title);
      })
      .catch((e) => setError(e.message));
    api<{
      engine_version: string;
      defaults: Settings;
      rules: { id: string; title: string }[];
    }>("detection/rules")
      .then((data) => {
        setSettings(data.defaults);
        setPrivilegedGroups(data.defaults.privileged_groups.join("\n"));
        setCatalog(data.rules);
        setCurrentEngine(data.engine_version);
      })
      .catch((e) => setError(e.message));
  }, [caseId]);
  useEffect(() => {
    let ignore = false;
    setImportsLoading(true);
    setImportsError(false);
    api<{ items: Scope[]; total: number }>(
      `cases/${caseId}/imports?offset=${importOffset}`,
    )
      .then((data) => {
        if (!ignore) {
          setImports(data.items);
          setImportTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) {
          setError(e.message);
          setImportsError(true);
        }
      })
      .finally(() => {
        if (!ignore) setImportsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [caseId, importOffset]);
  useEffect(() => {
    let ignore = false;
    loadHistory()
      .then((items) => {
        if (!ignore)
          setAnalysisId(
            (current) => current || initialAnalysisId || items[0]?.id || "",
          );
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [loadHistory, initialAnalysisId]);
  useEffect(() => {
    if (!analysisId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setAnalysis(null);
    setFindingsLoading(true);
    setFindings([]);
    setGroups([]);
    setActiveFinding("");
    setOriginalId("");
    setGroupId("");
    setSeverity("");
    setRule("");
    setTechnique("");
    setFilters(emptyFilters);
    setDraftFilters(emptyFilters);
    setFindingOffset(0);
    setGroupOffset(0);
    setDuplicateOffset(0);
    const poll = async () => {
      try {
        const data = await api<Analysis>(`analyses/${analysisId}`);
        if (disposed) return;
        setAnalysis(data);
        if (["queued", "running"].includes(data.status))
          timer = setTimeout(poll, 1200);
        else await loadHistory();
      } catch (e) {
        if (!disposed) {
          setError(
            `No se pudo consultar el análisis. Recarga para recuperar su estado. ${(e as Error).message}`,
          );
          timer = setTimeout(poll, 3000);
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
    // History pagination must not reset a running analysis poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, pollTick]);
  const completed = analysis?.status === "succeeded" ? analysis.id : null;
  const filterParams = new URLSearchParams();
  if (severity) filterParams.set("severity", severity);
  if (rule) filterParams.set("rule_id", rule);
  if (technique) filterParams.set("technique_id", technique);
  if (groupId) filterParams.set("group_id", groupId);
  for (const [key, value] of Object.entries(filters)) {
    if (value) filterParams.set(key, value);
  }
  const filterQuery = filterParams.toString();
  function applyFilters(patch: Partial<typeof emptyFilters>) {
    const next = { ...filters, ...patch };
    setFilters(next);
    setDraftFilters(next);
    setFindingOffset(0);
  }
  useEffect(() => {
    if (!completed) return;
    let ignore = false;
    setFindingsLoading(true);
    setFindingsError("");
    setFindings([]);
    setActiveFinding("");
    const query = new URLSearchParams(filterQuery);
    query.set("offset", String(findingOffset));
    api<{ items: Finding[]; total: number }>(
      `analyses/${completed}/findings?${query}`,
    )
      .then((data) => {
        if (!ignore) {
          setFindings(data.items);
          setFindingTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) {
          setError(e.message);
          setFindingsError(e.message);
        }
      })
      .finally(() => {
        if (!ignore) setFindingsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [completed, filterQuery, findingOffset]);
  useEffect(() => {
    if (!completed) return;
    let ignore = false;
    api<{ items: Group[]; total: number }>(
      `analyses/${completed}/groups?offset=${groupOffset}`,
    )
      .then((data) => {
        if (!ignore) {
          setGroups(data.items);
          setGroupTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [completed, groupOffset]);
  useEffect(() => {
    if (!completed || !showDuplicates) return;
    let ignore = false;
    api<{ items: { event_id: string; representative_id: string }[] }>(
      `analyses/${completed}/duplicates?offset=${duplicateOffset}`,
    )
      .then((data) => {
        if (!ignore) setDuplicates(data.items);
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [completed, showDuplicates, duplicateOffset]);

  function changeSetting(key: keyof Settings, value: unknown) {
    if (settings) setSettings({ ...settings, [key]: value });
    setConfirmed(false);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true);
    setError("");
    try {
      const config = {
        ...settings,
        excluded_users: lines(excludedUsers),
        excluded_source_ips: lines(excludedIps),
        privileged_groups: lines(privilegedGroups),
        business_hours: calendar ? { weekdays, start, end } : null,
      };
      const data = await api<Analysis>(`cases/${caseId}/analyses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          import_ids: selected.map((s) => s.id),
          settings: config,
        }),
      });
      setAnalysisId(data.id);
      setPollTick((n) => n + 1);
      await loadHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    if (!analysis) return;
    setBusy(true);
    try {
      await api(`analyses/${analysis.id}/retry`, { method: "POST" });
      setPollTick((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const scheduleValid = !calendar || (start < end && weekdays.length > 0);

  return (
    <main className="import-main analysis-main">
      <header>
        <Link href={`/cases/${caseId}`}>← Archivos y eventos del caso</Link>
        {completed && (
          <a className="dashboard-link" href="#dashboard">
            Ver dashboard ↓
          </a>
        )}
        <span className="badge">MOTOR LOCAL · REGLAS</span>
      </header>
      <section className="heading">
        <div>
          <p className="eyebrow">03 / INVESTIGAR</p>
          <h1>{title}</h1>
          <p className="intro">
            Detección reproducible, cobertura explícita y evidencias
            verificables.
          </p>
        </div>
      </section>
      <p className="info-note">
        Los hallazgos son indicios que requieren revisión. Un grupo de
        investigación no equivale a un incidente confirmado. Puedes preparar
        borradores con IA local al investigar cada hallazgo.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div
        className="analysis-setup"
        style={compact ? { display: "none" } : undefined}
      >
        <section className="panel">
          <h2>1. Selecciona el alcance</h2>
          <p className="muted">
            Elige una revisión por archivo original. Máximo 20 importaciones y
            100 000 eventos en total; no se sumarán dos versiones del mismo
            archivo.
          </p>
          <div className="scope-list">
            {imports.map((s) => {
              const checked = selected.some((x) => x.id === s.id);
              const alternate = selected.some(
                (x) => x.sha256 === s.sha256 && x.id !== s.id,
              );
              return (
                <label key={s.id} className="scope-option">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={
                      running ||
                      alternate ||
                      (!checked && selected.length >= 20)
                    }
                    onChange={(e) => {
                      setSelected(
                        e.target.checked
                          ? [...selected, s]
                          : selected.filter((x) => x.id !== s.id),
                      );
                      setConfirmed(false);
                      setWindowsConfirmed(false);
                    }}
                  />
                  <span>
                    <strong>{s.name}</strong>
                    <small>
                      {s.summary.accepted} eventos aceptados ·{" "}
                      {stamp(s.created_at)}
                    </small>
                    <code>{s.id}</code>
                    {alternate && (
                      <small>
                        Ya seleccionaste otra lectura del mismo archivo.
                      </small>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
          {importsLoading && <p role="status">Recuperando importaciones…</p>}
          {!importsLoading && !importsError && !importTotal && (
            <p className="muted">
              Primero importa eventos desde{" "}
              <Link href={`/cases/${caseId}`}>los archivos del caso</Link>.
            </p>
          )}
          {importTotal > 20 && (
            <div className="pagination">
              <button
                disabled={!importOffset || running}
                onClick={() => setImportOffset(importOffset - 20)}
              >
                Anteriores
              </button>
              <span>
                {importOffset + 1}–{Math.min(importOffset + 20, importTotal)} /{" "}
                {importTotal}
              </span>
              <button
                disabled={importOffset + 20 >= importTotal || running}
                onClick={() => setImportOffset(importOffset + 20)}
              >
                Siguientes
              </button>
            </div>
          )}
          <p className="notice">
            Seleccionadas: {selected.length} · Eventos:{" "}
            {selected.reduce((n, s) => n + s.summary.accepted, 0)}
          </p>
          <details>
            <summary>Historial de análisis ({historyTotal})</summary>
            <ul className="file-list">
              {history.map((a) => (
                <li key={a.id}>
                  <button
                    className={analysisId === a.id ? "selected-file" : ""}
                    disabled={running}
                    onClick={() => setAnalysisId(a.id)}
                  >
                    {stamp(a.created_at)} · {statusLabels[a.status]}
                    <span>
                      {a.summary?.findings ?? "—"} hallazgos ·{" "}
                      {a.config.import_ids.length} importaciones
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {historyTotal > 20 && (
              <div className="pagination">
                <button
                  disabled={!historyOffset || running}
                  onClick={() => setHistoryOffset(historyOffset - 20)}
                >
                  Anteriores
                </button>
                <span>
                  {historyOffset + 1}–
                  {Math.min(historyOffset + 20, historyTotal)}
                </span>
                <button
                  disabled={historyOffset + 20 >= historyTotal || running}
                  onClick={() => setHistoryOffset(historyOffset + 20)}
                >
                  Siguientes
                </button>
              </div>
            )}
          </details>
        </section>
        <section className="panel">
          <h2>2. Confirma la interpretación</h2>
          <p className="muted">
            Estos controles preparan un análisis nuevo. El resultado del
            historial conserva su propia configuración.
          </p>
          {settings && (
            <form onSubmit={submit}>
              <label htmlFor="source-profile">Semántica de los registros</label>
              {settings.source_profile === "generic" &&
                selected.some((s) => s.profile_hint === "windows_security") && (
                  <div className="info-note">
                    <p>
                      La muestra del archivo contiene un canal, códigos y
                      descripciones compatibles con Windows Security. Confirma
                      el proveedor antes de interpretar esos códigos.
                    </p>
                    <button
                      type="button"
                      className="secondary"
                      disabled={running}
                      onClick={() => {
                        changeSetting("source_profile", "windows_security");
                        setWindowsConfirmed(false);
                      }}
                    >
                      Revisar con perfil Windows Security
                    </button>
                  </div>
                )}
              <select
                id="source-profile"
                disabled={running}
                value={settings.source_profile}
                onChange={(e) => {
                  changeSetting("source_profile", e.target.value);
                  setWindowsConfirmed(false);
                }}
              >
                <option value="generic">
                  Genérica: tipos explícitos y proveedor mapeado
                </option>
                <option value="auto">
                  Automática por registro: canal, proveedor y campos explícitos
                </option>
                <option value="windows_security">
                  Windows Security: códigos nativos de ese proveedor
                </option>
              </select>
              <p className="muted">
                Los códigos numéricos no identifican por sí solos un evento. En
                fuentes mixtas usa el perfil genérico y mapea la columna
                Proveedor. Los resultados no reconocidos se indican en
                cobertura.
              </p>
              {settings.source_profile === "windows_security" && (
                <label className="confirm">
                  <input
                    type="checkbox"
                    checked={windowsConfirmed}
                    disabled={running}
                    onChange={(e) => setWindowsConfirmed(e.target.checked)}
                  />
                  Confirmo que las fuentes seleccionadas son Windows Security.
                </label>
              )}
              <label className="confirm">
                <input
                  type="checkbox"
                  checked={calendar}
                  disabled={running}
                  onChange={(e) => {
                    setCalendar(e.target.checked);
                    setConfirmed(false);
                  }}
                />
                Evaluar accesos fuera de horario con un calendario conocido
              </label>
              {calendar && (
                <fieldset>
                  <legend>Horario autorizado (mismo día)</legend>
                  <div className="mapping-grid">
                    <div>
                      <label htmlFor="business-start">Inicio incluido</label>
                      <input
                        id="business-start"
                        type="time"
                        value={start}
                        onChange={(e) => {
                          setStart(e.target.value);
                          setConfirmed(false);
                        }}
                        required
                        disabled={running}
                      />
                    </div>
                    <div>
                      <label htmlFor="business-end">Fin excluido</label>
                      <input
                        id="business-end"
                        type="time"
                        value={end}
                        onChange={(e) => {
                          setEnd(e.target.value);
                          setConfirmed(false);
                        }}
                        required
                        disabled={running}
                      />
                    </div>
                  </div>
                  <div className="weekdays">
                    {["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"].map(
                      (d, i) => (
                        <label key={d}>
                          <input
                            type="checkbox"
                            checked={weekdays.includes(i)}
                            disabled={running}
                            onChange={(e) => {
                              setWeekdays(
                                e.target.checked
                                  ? [...weekdays, i].sort()
                                  : weekdays.filter((x) => x !== i),
                              );
                              setConfirmed(false);
                            }}
                          />
                          {d}
                        </label>
                      ),
                    )}
                  </div>
                  {!scheduleValid && (
                    <p className="error">
                      Elige días y un horario cuyo inicio sea anterior al fin.
                    </p>
                  )}
                </fieldset>
              )}
              <details>
                <summary>Umbrales y exclusiones</summary>
                <p className="muted">
                  No se excluyen cuentas administrativas automáticamente. Las
                  exclusiones que indiques se aplican a todas las reglas y
                  quedarán registradas.
                </p>
                <div className="mapping-grid">
                  {thresholds.map(([key, label, min, max]) => (
                    <div key={key}>
                      <label htmlFor={`threshold-${key}`}>{label}</label>
                      <input
                        id={`threshold-${key}`}
                        type="number"
                        min={min}
                        max={max}
                        step="1"
                        disabled={running}
                        value={Number(settings[key])}
                        onChange={(e) =>
                          changeSetting(key, Number(e.target.value))
                        }
                        required
                      />
                    </div>
                  ))}
                </div>
                <label htmlFor="excluded-users">
                  Usuarios excluidos (uno por línea, coincidencia exacta)
                </label>
                <textarea
                  id="excluded-users"
                  value={excludedUsers}
                  disabled={running}
                  onChange={(e) => {
                    setExcludedUsers(e.target.value);
                    setConfirmed(false);
                  }}
                  maxLength={12850}
                />
                <label htmlFor="excluded-ips">
                  IP de origen excluidas (una por línea)
                </label>
                <textarea
                  id="excluded-ips"
                  value={excludedIps}
                  disabled={running}
                  onChange={(e) => {
                    setExcludedIps(e.target.value);
                    setConfirmed(false);
                  }}
                  maxLength={2500}
                />
                <label htmlFor="privileged-groups">
                  Nombres de grupos privilegiados (uno por línea)
                </label>
                <textarea
                  id="privileged-groups"
                  value={privilegedGroups}
                  disabled={running}
                  onChange={(e) => {
                    setPrivilegedGroups(e.target.value);
                    setConfirmed(false);
                  }}
                  maxLength={12850}
                />
                <p className="muted">
                  No se infieren grupos privilegiados por palabras parciales ni
                  por el nombre de la cuenta. Revisa la asignación de Grupo de
                  destino y Privilegio en la importación.
                </p>
              </details>
              <label className="confirm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={running}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                Revisé el alcance, la semántica de las fuentes y el contexto
                configurado.
              </label>
              <button
                className="primary"
                disabled={
                  running ||
                  !selected.length ||
                  !confirmed ||
                  !scheduleValid ||
                  (settings.source_profile === "windows_security" &&
                    !windowsConfirmed) ||
                  selected.reduce((n, s) => n + s.summary.accepted, 0) > 100000
                }
              >
                {running ? "Procesando…" : "Ejecutar análisis de seguridad"}
              </button>
              <small>
                Se reutiliza un análisis existente si el alcance, las reglas y
                la configuración son idénticos.
              </small>
            </form>
          )}
        </section>
      </div>
      {analysis && (
        <section className="panel analysis-results">
          <div className="panel-title">
            <h2>Resultado · {statusLabels[analysis.status]}</h2>
            <span className="badge">REVISIÓN HUMANA PENDIENTE</span>
          </div>
          {["queued", "running"].includes(analysis.status) && (
            <p role="status">
              Analizando las importaciones seleccionadas. No se muestran
              resultados parciales.
            </p>
          )}
          {analysis.status === "failed" && (
            <div role="alert" className="error">
              {analysis.error}
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void retry()}
              >
                Reintentar análisis
              </button>
            </div>
          )}
          {analysis.summary && (
            <>
              <p className="muted">{analysis.summary.limitations}</p>
              {currentEngine &&
                analysis.config.engine_version !== currentEngine && (
                  <div className="notice" role="status">
                    <strong>
                      Resultado histórico · motor{" "}
                      {analysis.config.engine_version}
                    </strong>
                    <p>
                      Esta ejecución no incluye las detecciones del motor{" "}
                      {currentEngine}. Puedes conservarla y generar una nueva
                      revisión.
                    </p>
                    {analysis.summary.sources.length === 1 &&
                      analysis.summary.sources[0].file_id && (
                        <button
                          type="button"
                          className="secondary"
                          disabled={busy}
                          onClick={async () => {
                            setBusy(true);
                            try {
                              const result = await api<{ id: string }>(
                                `cases/${caseId}/files/${analysis.summary!.sources[0].file_id}/automatic`,
                                { method: "POST" },
                              );
                              router.push(
                                `/cases/${caseId}/overview?run=${result.id}`,
                              );
                            } catch (e) {
                              setError((e as Error).message);
                              setBusy(false);
                            }
                          }}
                        >
                          Reanalizar con el motor actual
                        </button>
                      )}
                  </div>
                )}
              {analysis.summary.coverage.every(
                (r) => r.eligible_events === 0,
              ) && (
                <div className="error" role="alert">
                  <strong>
                    No se pudo evaluar la seguridad de los registros.
                  </strong>
                  <p>
                    Se importaron {analysis.summary.input_events} eventos, pero
                    ninguna regla tuvo datos interpretables. Cero hallazgos no
                    significa que el archivo esté libre de amenazas.
                  </p>
                  <p>
                    Revisa el mapeo de tipo de evento, ID y proveedor, comandos
                    y destinos. Si los códigos corresponden a Windows Security,
                    selecciona ese perfil al analizar.
                  </p>
                  <Link href={`/cases/${caseId}`}>
                    Revisar las columnas del archivo →
                  </Link>
                </div>
              )}
              <p className="muted">Totales del análisis completo</p>
              {analysis.summary.coverage.some(
                (r) => r.status === "partial" || r.status === "not_evaluable",
              ) &&
                analysis.summary.coverage.some(
                  (r) => r.eligible_events > 0,
                ) && (
                  <p className="info-note">
                    La cobertura es parcial. Consulta las reglas no evaluables y
                    sus motivos; pueden faltar campos, semántica del proveedor o
                    contexto del cliente.
                  </p>
                )}
              <div className="import-stats">
                {Object.entries(analysis.summary.by_severity).map(([s, n]) => (
                  <div key={s}>
                    <strong>{n}</strong>
                    <span>{s}</span>
                  </div>
                ))}
                <div>
                  <strong>{analysis.summary.investigation_groups}</strong>
                  <span>Grupos para investigar</span>
                </div>
              </div>
              <p className="muted">
                {analysis.summary.input_events} eventos recibidos ·{" "}
                {analysis.summary.unique_events} distinguibles ·{" "}
                {analysis.summary.duplicate_events} copias sin recuento
                adicional · {analysis.summary.excluded_events} excluidos por
                configuración · {analysis.summary.import_rejected_rows} filas
                rechazadas durante la importación.
              </p>
              <p className="info-note">
                La criticidad indica prioridad de investigación, no impacto
                confirmado. Cada hallazgo explica sus condiciones y
                limitaciones. La confianza se muestra por separado.
              </p>
              <details>
                <summary>Configuración y huella de esta ejecución</summary>
                <p className="hash">
                  SHA-256 de entradas y configuración{" "}
                  <code>{analysis.input_hash}</code>
                </p>
                <p className="muted">
                  Motor {analysis.config.engine_version} · Reglas{" "}
                  {analysis.config.ruleset_version}
                </p>
                <pre className="observed-data">
                  {displayDetails(analysis.config)}
                </pre>
                <ul className="hash">
                  {analysis.summary.sources.map((s) => (
                    <li key={s.import_id}>
                      {s.name}
                      <code>{s.sha256}</code>
                    </li>
                  ))}
                </ul>
              </details>
              <h3 id="dashboard" tabIndex={-1}>
                Dashboard interactivo
              </h3>
              <div className="finding-filters">
                <div>
                  <label htmlFor="severity-filter">Criticidad</label>
                  <select
                    id="severity-filter"
                    value={severity}
                    onChange={(e) => {
                      setSeverity(e.target.value);
                      setFindingOffset(0);
                    }}
                  >
                    <option value="">Todas</option>
                    {["Crítico", "Alto", "Medio", "Bajo"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="rule-filter">Regla</label>
                  <select
                    id="rule-filter"
                    value={rule}
                    onChange={(e) => {
                      setRule(e.target.value);
                      setFindingOffset(0);
                    }}
                  >
                    <option value="">Todas</option>
                    {catalog.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title}
                      </option>
                    ))}
                  </select>
                </div>
                {groupId && (
                  <button
                    className="secondary"
                    onClick={() => {
                      setGroupId("");
                      setFindingOffset(0);
                    }}
                  >
                    Quitar filtro de grupo
                  </button>
                )}
              </div>
              <form
                className="dashboard-filter-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  applyFilters({
                    ...draftFilters,
                    user: draftFilters.user.trim(),
                    host: draftFilters.host.trim(),
                  });
                }}
              >
                <div>
                  <label htmlFor="dashboard-from">
                    Desde · inicio del hallazgo
                  </label>
                  <input
                    id="dashboard-from"
                    type="date"
                    value={draftFilters.date_from}
                    max={draftFilters.date_to || undefined}
                    onChange={(e) =>
                      setDraftFilters({
                        ...draftFilters,
                        date_from: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label htmlFor="dashboard-to">Hasta · inclusive</label>
                  <input
                    id="dashboard-to"
                    type="date"
                    value={draftFilters.date_to}
                    min={draftFilters.date_from || undefined}
                    onChange={(e) =>
                      setDraftFilters({
                        ...draftFilters,
                        date_to: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label htmlFor="dashboard-user">Usuario exacto</label>
                  <input
                    id="dashboard-user"
                    value={draftFilters.user}
                    maxLength={256}
                    onChange={(e) =>
                      setDraftFilters({ ...draftFilters, user: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label htmlFor="dashboard-host">Equipo exacto</label>
                  <input
                    id="dashboard-host"
                    value={draftFilters.host}
                    maxLength={256}
                    onChange={(e) =>
                      setDraftFilters({ ...draftFilters, host: e.target.value })
                    }
                  />
                </div>
                <div className="dashboard-filter-actions">
                  <button type="submit">Aplicar filtros</button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setSeverity("");
                      setRule("");
                      setTechnique("");
                      setGroupId("");
                      applyFilters(emptyFilters);
                    }}
                  >
                    Restablecer filtros
                  </button>
                </div>
              </form>
              <p className="muted">
                Filtros aplicados:{" "}
                {[
                  severity,
                  technique ? `MITRE: ${technique}` : "",
                  rule
                    ? (catalog.find((r) => r.id === rule)?.title ?? rule)
                    : "",
                  groupId ? "Grupo seleccionado" : "",
                  filters.date_from ? `Desde ${filters.date_from}` : "",
                  filters.date_to ? `Hasta ${filters.date_to}` : "",
                  filters.user ? `Usuario: ${filters.user}` : "",
                  filters.host ? `Equipo: ${filters.host}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ") || "Todos los hallazgos"}
                .
              </p>
              <Dashboard
                analysisId={analysis.id}
                query={filterQuery}
                severity={severity}
                rule={rule}
                user={filters.user}
                host={filters.host}
                day={
                  filters.date_from === filters.date_to ? filters.date_from : ""
                }
                onSeverity={(value) => {
                  setSeverity(value);
                  setFindingOffset(0);
                }}
                onRule={(value) => {
                  setRule(value);
                  setFindingOffset(0);
                }}
                onUser={(value) => applyFilters({ user: value })}
                onHost={(value) => applyFilters({ host: value })}
                onDay={(value) =>
                  applyFilters({ date_from: value, date_to: value })
                }
              />
              <details
                className="dashboard-coverage"
                open={
                  analysis.summary.coverage.every(
                    (r) => r.eligible_events === 0,
                  ) || undefined
                }
              >
                <summary>Cobertura del análisis completo</summary>
                <CoverageTable rows={analysis.summary.coverage} />
              </details>
              <AttackMatrix
                analysisId={analysis.id}
                query={filterQuery}
                selected={technique}
                onSelect={(value) => {
                  setTechnique(value);
                  setFindingOffset(0);
                }}
              />
              <h3 id="findings">Hallazgos sustentados · vista filtrada</h3>
              {findingsLoading && <p role="status">Recuperando hallazgos…</p>}
              {findingsError && (
                <p role="alert" className="error">
                  {findingsError}
                </p>
              )}
              {!findingsLoading && !findingsError && !findings.length && (
                <p className="muted">
                  Sin hallazgos para estos filtros. Revisa la cobertura; esto no
                  demuestra ausencia de compromiso.
                </p>
              )}
              {!findingsLoading &&
                findings.map((f) => (
                  <article className="finding-card" key={f.id}>
                    <div className="panel-title">
                      <h4>{f.title}</h4>
                      <span className={`risk risk-${f.severity.toLowerCase()}`}>
                        {f.severity}
                      </span>
                    </div>
                    <p className="muted">
                      Confianza {f.confidence} · {f.evidence_count} referencias
                      · Requiere revisión
                    </p>
                    <p>{f.reason}</p>
                    {f.severity_reason && (
                      <div className="risk-rationale">
                        <strong>Por qué {f.severity}</strong>
                        <p>{f.severity_reason}</p>
                        <small>
                          Prioridad: {f.risk_score}/100 · Escala de la política,
                          no probabilidad de compromiso.
                        </small>
                      </div>
                    )}
                    <p className="muted">
                      {f.start ?? "Sin hora válida"}
                      {f.end && f.end !== f.start ? ` → ${f.end}` : ""}
                    </p>
                    <button
                      className="secondary"
                      aria-expanded={activeFinding === f.id}
                      onClick={() =>
                        setActiveFinding(activeFinding === f.id ? "" : f.id)
                      }
                    >
                      {activeFinding === f.id
                        ? "Cerrar hallazgo"
                        : "Investigar hallazgo"}
                    </button>
                    {activeFinding === f.id && (
                      <>
                        <h4>Limitaciones y posibles explicaciones legítimas</h4>
                        <p>{f.limitations}</p>
                        <h4>Impacto potencial</h4>
                        <p>{f.potential_impact}</p>
                        <h4>Acciones recomendadas, no ejecutadas</h4>
                        <ul>
                          {f.actions.map((a) => (
                            <li key={a}>{a}</li>
                          ))}
                        </ul>
                        {f.attack_reference && (
                          <p className="muted">
                            Referencia ATT&CK para investigar:{" "}
                            {f.attack_reference}. No confirma esa técnica.
                          </p>
                        )}
                        <details>
                          <summary>
                            Condiciones observadas y coincidencias
                          </summary>
                          <pre className="observed-data">
                            {displayDetails(f.observed)}
                          </pre>
                        </details>
                        <FindingEvidence
                          key={f.id}
                          caseId={caseId}
                          analysisId={analysis.id}
                          findingId={f.id}
                        />
                        <AIDraft
                          caseId={caseId}
                          analysisId={analysis.id}
                          findingId={f.id}
                        />
                      </>
                    )}
                  </article>
                ))}
              <div className="pagination">
                <button
                  disabled={!findingOffset}
                  onClick={() => setFindingOffset(findingOffset - 20)}
                >
                  Anteriores
                </button>
                <span>
                  {findingTotal ? findingOffset + 1 : 0}–
                  {Math.min(findingOffset + 20, findingTotal)} / {findingTotal}
                </span>
                <button
                  disabled={findingOffset + 20 >= findingTotal}
                  onClick={() => setFindingOffset(findingOffset + 20)}
                >
                  Siguientes
                </button>
              </div>
              {compact && (
                <AssistantSummary key={analysis.id} analysisId={analysis.id} />
              )}
              <TechnicalReport
                key={`report-${analysis.id}`}
                analysisId={analysis.id}
              />
              <h3 id="correlations">
                Correlación · grupos del análisis completo
              </h3>
              <p className="muted">
                No es un conteo de incidentes. Las relaciones por entidad
                requieren usuario y activo coincidentes; una IP sola no une
                hallazgos.
              </p>
              {groups.map((g, i) => (
                <div className="group-card" key={g.id}>
                  <h4>
                    Grupo {groupOffset + i + 1} · {g.finding_ids.length}{" "}
                    hallazgos
                  </h4>
                  <p>{g.interpretation}</p>
                  <details>
                    <summary>
                      Motivos de las {g.links.length} conexiones
                    </summary>
                    {!g.links.length && (
                      <p>
                        Hallazgo individual sin vínculo suficiente con otro.
                      </p>
                    )}
                    <ul>
                      {g.links.map((link, j) => (
                        <li key={j}>
                          {link.kind === "shared_event"
                            ? "Los hallazgos comparten un registro de evidencia."
                            : `Coinciden usuario ${link.user} y activo ${link.asset} dentro de la ventana configurada.`}
                        </li>
                      ))}
                    </ul>
                  </details>
                  <button
                    className="secondary"
                    onClick={() => {
                      setGroupId(g.id);
                      setTechnique("");
                      setSeverity("");
                      setRule("");
                      setFindingOffset(0);
                    }}
                  >
                    Ver hallazgos de este grupo
                  </button>
                </div>
              ))}
              {groupTotal > 20 && (
                <div className="pagination">
                  <button
                    disabled={!groupOffset}
                    onClick={() => setGroupOffset(groupOffset - 20)}
                  >
                    Grupos anteriores
                  </button>
                  <span>
                    {groupOffset + 1}–{Math.min(groupOffset + 20, groupTotal)}
                  </span>
                  <button
                    disabled={groupOffset + 20 >= groupTotal}
                    onClick={() => setGroupOffset(groupOffset + 20)}
                  >
                    Grupos siguientes
                  </button>
                </div>
              )}
              {analysis.summary.duplicate_events > 0 && (
                <section>
                  <button
                    className="secondary"
                    aria-expanded={showDuplicates}
                    onClick={() => setShowDuplicates(!showDuplicates)}
                  >
                    Revisar registros indistinguibles (
                    {analysis.summary.duplicate_events})
                  </button>
                  {showDuplicates && (
                    <>
                      <p className="muted">
                        Coinciden campos normalizados y fecha. Se cuentan una
                        vez para evitar umbrales artificiales; los registros
                        originales siguen disponibles. Podrían ser eventos
                        distintos si la fuente perdió precisión o
                        identificadores.
                      </p>
                      <ul>
                        {duplicates.map((d) => (
                          <li key={d.event_id}>
                            <button
                              className="secondary"
                              onClick={() => setOriginalId(d.event_id)}
                            >
                              Ver copia
                            </button>{" "}
                            <button
                              className="secondary"
                              onClick={() => setOriginalId(d.representative_id)}
                            >
                              Ver representante
                            </button>
                          </li>
                        ))}
                      </ul>
                      <div className="pagination">
                        <button
                          disabled={!duplicateOffset}
                          onClick={() =>
                            setDuplicateOffset(duplicateOffset - 20)
                          }
                        >
                          Copias anteriores
                        </button>
                        <span>
                          {duplicateOffset + 1}–
                          {Math.min(
                            duplicateOffset + 20,
                            analysis.summary.duplicate_events,
                          )}
                        </span>
                        <button
                          disabled={
                            duplicateOffset + 20 >=
                            analysis.summary.duplicate_events
                          }
                          onClick={() =>
                            setDuplicateOffset(duplicateOffset + 20)
                          }
                        >
                          Copias siguientes
                        </button>
                      </div>
                      {originalId && (
                        <OriginalEvidence
                          caseId={caseId}
                          eventId={originalId}
                        />
                      )}
                    </>
                  )}
                </section>
              )}
            </>
          )}
        </section>
      )}
      <footer>
        Motor determinista local · Sin acciones de contención automáticas ni
        confirmación automática de incidentes.
      </footer>
    </main>
  );
}
