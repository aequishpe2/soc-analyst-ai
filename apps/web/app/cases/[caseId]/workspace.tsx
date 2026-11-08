"use client";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, warningLabel } from "../../../lib/api";

type Summary = {
  total: number;
  accepted: number;
  rejected: number;
  with_warnings: number;
  without_valid_time: number;
  warnings: Record<string, number>;
};
type Sample = {
  row: number;
  line_end: number;
  values: (string | null)[];
  formulas: number[];
  error: string | null;
};
type Sheet = {
  name: string;
  rows: number;
  header_row: number;
  formula_rows: number;
  columns: { id: string; label: string }[];
  preview: Sample[];
};
type Source = {
  id: string;
  name: string;
  sha256: string;
  size: number;
  status: string;
  manifest?: {
    sheets: Sheet[];
    total_rows: number;
    blank_rows: number;
    preview_note: string;
    csv_options?: { encoding: string; delimiter: string };
  };
};
type Job = {
  id: string;
  file_id: string;
  kind: string;
  status: string;
  error: string | null;
  result?: Summary & { import_id: string };
};
type Run = {
  id: string;
  summary: Summary;
  config: { timezone: string; date_format: string };
};
type EventRow = {
  id: string;
  sheet: string;
  row: number;
  line_end: number;
  timestamp_utc: string | null;
  normalized: Record<string, string | null>;
  warnings: string[];
};
type Evidence = EventRow & {
  file_name: string;
  sha256: string;
  columns: { id: string; label: string }[];
  original: (string | null)[];
  import_config: { timezone: string; date_format: string };
};
type Issue = { sheet: string; row: number; line_end: number; reason: string };
const fields = [
  ["timestamp", "Fecha y hora"],
  ["user", "Usuario"],
  ["source_ip", "IP de origen"],
  ["destination_ip", "IP de destino"],
  ["source_host", "Equipo de origen"],
  ["destination_host", "Equipo de destino"],
  ["event_type", "Tipo de evento"],
  ["result", "Resultado"],
  ["process", "Proceso"],
  ["command", "Comando"],
  ["provider_event_id", "ID de evento del SIEM"],
  ["event_provider", "Proveedor del evento"],
  ["logon_type", "Tipo de inicio de sesión (Windows)"],
  ["target_group", "Grupo de destino"],
  ["target_user", "Cuenta afectada o miembro añadido"],
  ["privilege", "Privilegio o rol asignado"],
];
const aliases: Record<string, string[]> = {
  timestamp: [
    "timestamp",
    "fecha",
    "date",
    "datetime",
    "time",
    "fecha_hora",
    "@timestamp",
  ],
  user: ["user", "usuario", "username", "account"],
  source_ip: ["source_ip", "src_ip", "ip_origen"],
  destination_ip: ["destination_ip", "dst_ip", "ip_destino"],
  source_host: ["source_host", "src_host"],
  destination_host: ["destination_host", "dst_host"],
  event_type: ["event_type", "evento", "event"],
  result: ["result", "resultado", "outcome", "status"],
  process: ["process", "proceso", "process_name"],
  command: ["command", "comando", "commandline", "command_line"],
  provider_event_id: ["event_id", "eventid"],
  event_provider: ["provider", "providername", "event_provider"],
  logon_type: ["logon_type", "logontype"],
  target_group: ["target_group", "targetgroup", "groupname", "targetgroupname"],
  target_user: ["target_user", "targetusername", "membername"],
  privilege: ["privilege", "privileges", "role"],
};
function suggest(sheet: Sheet) {
  const mapping: Record<string, string> = {};
  const used = new Set<string>();
  for (const [field] of fields) {
    const col = sheet.columns.find(
      (c) =>
        !used.has(c.id) &&
        aliases[field]?.includes(
          c.label.toLowerCase().trim().replaceAll(" ", "_"),
        ),
    );
    if (col) {
      mapping[field] = col.id;
      used.add(col.id);
    }
  }
  return mapping;
}
const clip = (text: string | null | undefined) =>
  text ? text.slice(0, 180) + (text.length > 180 ? "…" : "") : "—";

export default function ImportWorkspace({ caseId }: { caseId: string }) {
  const [caseInfo, setCaseInfo] = useState<{
    title: string;
    timezone: string;
  } | null>(null);
  const [files, setFiles] = useState<Source[]>([]);
  const [fileTotal, setFileTotal] = useState(0);
  const [fileOffset, setFileOffset] = useState(0);
  const [source, setSource] = useState<Source | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState("");
  const [activeSheet, setActiveSheet] = useState("");
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const [mappings, setMappings] = useState<
    Record<string, Record<string, string>>
  >({});
  const [timezone, setTimezone] = useState("Europe/Stockholm");
  const [dateFormat, setDateFormat] = useState("iso8601");
  const [confirmed, setConfirmed] = useState(false);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [eventTotal, setEventTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [issueTotal, setIssueTotal] = useState(0);
  const [issueOffset, setIssueOffset] = useState(0);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [encoding, setEncoding] = useState("auto");
  const [delimiter, setDelimiter] = useState("auto");
  const uploadRef = useRef<HTMLInputElement>(null);
  const selection = useRef(0);
  const working = busy || (!!job && ["queued", "running"].includes(job.status));

  const loadFiles = useCallback(async () => {
    const list = await api<{ items: Source[]; total: number }>(
      `cases/${caseId}/files?offset=${fileOffset}`,
    );
    setFiles(list.items);
    setFileTotal(list.total);
  }, [caseId, fileOffset]);

  useEffect(() => {
    api<{ title: string; timezone: string }>(`cases/${caseId}`)
      .then((data) => {
        setCaseInfo(data);
        setTimezone(data.timezone);
      })
      .catch((e) => setError(e.message));
  }, [caseId]);
  useEffect(() => {
    loadFiles().catch((e) => setError(e.message));
  }, [loadFiles]);

  async function openSource(id: string, message = "") {
    const generation = ++selection.current;
    setBusy(true);
    setError("");
    setNotice("");
    setSource(null);
    setJob(null);
    setRunId("");
    setEvidence(null);
    setEvents([]);
    setRuns([]);
    setConfirmed(false);
    try {
      const [file, jobs, imports] = await Promise.all([
        api<Source>(`files/${id}/preview`),
        api<Job[]>(`files/${id}/jobs`),
        api<Run[]>(`files/${id}/imports`),
      ]);
      if (generation !== selection.current) return;
      setSource(file);
      setRuns(imports);
      setRunId(imports[0]?.id ?? "");
      setOffset(0);
      setIssueOffset(0);
      const sheets = file.manifest?.sheets ?? [];
      setActiveSheet(sheets[0]?.name ?? "");
      setSelectedSheets(sheets.filter((s) => s.rows > 0).map((s) => s.name));
      setMappings(Object.fromEntries(sheets.map((s) => [s.name, suggest(s)])));
      setJob(
        jobs[0] && ["queued", "running", "failed"].includes(jobs[0].status)
          ? jobs[0]
          : null,
      );
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (generation === selection.current) setBusy(false);
    }
  }

  const activeJobId =
    job && ["queued", "running"].includes(job.status) ? job.id : null;
  useEffect(() => {
    if (!activeJobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const current = await api<Job>(`jobs/${activeJobId}`);
        if (disposed) return;
        setJob(current);
        if (current.status === "succeeded") {
          await openSource(
            current.file_id,
            current.kind === "import"
              ? "Importación terminada. Revisa los conteos y las advertencias."
              : "Archivo validado. Revisa las hojas y confirma el mapeo.",
          );
          await loadFiles();
          return;
        }
        if (current.status === "failed") {
          await loadFiles();
          return;
        }
      } catch (e) {
        if (!disposed)
          setError(
            `No se pudo consultar el trabajo. Recarga para recuperar su estado. ${(e as Error).message}`,
          );
      }
      if (!disposed) timer = setTimeout(poll, 1200);
    };
    timer = setTimeout(poll, 500);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
    // The job identity controls this polling lifetime; UI form state must not restart it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId]);

  useEffect(() => {
    setEvents([]);
    setEvidence(null);
    if (!runId) return;
    let ignore = false;
    api<{ items: EventRow[]; total: number }>(
      `cases/${caseId}/events?import_id=${runId}&offset=${offset}`,
    )
      .then((data) => {
        if (!ignore) {
          setEvents(data.items);
          setEventTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [caseId, runId, offset]);
  useEffect(() => {
    setIssues([]);
    if (!runId) return;
    let ignore = false;
    api<{ items: Issue[]; total: number }>(
      `imports/${runId}/issues?offset=${issueOffset}`,
    )
      .then((data) => {
        if (!ignore) {
          setIssues(data.items);
          setIssueTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [runId, issueOffset]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = uploadRef.current?.files?.[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024 || file.size === 0) {
      setError("El archivo debe tener contenido y no superar 20 MiB.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.set("file", file);
      form.set("encoding", encoding);
      form.set("delimiter", delimiter);
      const result = await api<{ file: Source; job: Job; reused: boolean }>(
        `cases/${caseId}/files`,
        { method: "POST", body: form },
      );
      await openSource(result.file.id);
      setJob(result.job.status === "succeeded" ? null : result.job);
      setNotice(
        result.reused
          ? "Este archivo y sus opciones ya estaban registrados; se reutilizó la carga."
          : "Archivo recibido. Se está validando en segundo plano.",
      );
      await loadFiles();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startImport(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const current = await api<Job>(`files/${source.id}/imports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sheets: selectedSheets.map((sheet) => ({
            sheet,
            mapping: mappings[sheet],
          })),
          timezone,
          date_format: dateFormat,
        }),
      });
      setJob(current);
      if (current.status === "succeeded") {
        await openSource(source.id);
        setNotice(
          "Esta configuración ya estaba importada. No se duplicaron eventos.",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      setJob(await api<Job>(`jobs/${job.id}/retry`, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const sheet = source?.manifest?.sheets.find((s) => s.name === activeSheet);
  const mapping = mappings[activeSheet] ?? {};
  const validMappings =
    selectedSheets.length > 0 &&
    selectedSheets.every((name) => {
      const values = Object.values(mappings[name] ?? {});
      return values.length > 0 && new Set(values).size === values.length;
    });
  const run = runs.find((r) => r.id === runId);

  return (
    <main className="import-main">
      <header>
        <Link href="/">← Investigaciones</Link>
        <Link className="secondary" href={`/cases/${caseId}/analysis`}>
          Análisis de seguridad →
        </Link>
      </header>
      <section className="heading">
        <div>
          <p className="eyebrow">02 / IMPORTAR REGISTROS</p>
          <h1>{caseInfo?.title ?? "Investigación"}</h1>
          <p className="intro">
            Conserva la fuente, revisa las columnas y prepara los eventos.
          </p>
        </div>
      </section>
      <p className="info-note">
        Importa y revisa los eventos antes de evaluar las versiones desde
        Análisis de seguridad. Los registros no se envían a la IA en esta fase.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <div className="ingestion-grid">
        <section className="panel">
          <p className="eyebrow">ARCHIVOS DEL CASO</p>
          <h2>Fuentes de evidencia</h2>
          <form onSubmit={upload}>
            <label htmlFor="file">Excel (.xlsx) o CSV · máximo 20 MiB</label>
            <input
              id="file"
              type="file"
              accept=".csv,.xlsx"
              ref={uploadRef}
              required
              disabled={working}
            />
            <details className="csv-options">
              <summary>Opciones de CSV</summary>
              <label htmlFor="encoding">Codificación</label>
              <select
                id="encoding"
                value={encoding}
                onChange={(e) => setEncoding(e.target.value)}
              >
                <option value="auto">UTF-8 o UTF-16 con BOM</option>
                <option value="utf-8-sig">UTF-8</option>
                <option value="utf-16">UTF-16 con BOM</option>
                <option value="cp1252">Windows-1252</option>
              </select>
              <label htmlFor="delimiter">Separador</label>
              <select
                id="delimiter"
                value={delimiter}
                onChange={(e) => setDelimiter(e.target.value)}
              >
                <option value="auto">Detectar y mostrar</option>
                <option value=",">Coma</option>
                <option value=";">Punto y coma</option>
                <option value={"\t"}>Tabulación</option>
                <option value="|">Barra vertical</option>
              </select>
            </details>
            <button className="primary" disabled={working}>
              {working ? "Procesando…" : "Cargar y validar archivo"}
            </button>
            <small>
              Sin macros ni enlaces externos. Primera fila no vacía como
              cabecera. Límite: 100 000 registros, 200 columnas y 20 hojas.
            </small>
          </form>
          <ul className="file-list">
            {files.map((f) => (
              <li key={f.id}>
                <button
                  className={source?.id === f.id ? "selected-file" : ""}
                  onClick={() => void openSource(f.id)}
                  disabled={working}
                >
                  <strong>{f.name}</strong>
                  <span>
                    {(f.size / 1024).toFixed(1)} KiB ·{" "}
                    {f.status === "ready"
                      ? "Listo"
                      : f.status === "failed"
                        ? "No válido"
                        : "En lectura"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {!files.length && (
            <p className="muted">Todavía no hay archivos en este caso.</p>
          )}
          {fileTotal > 20 && (
            <div className="pagination">
              <button
                disabled={fileOffset === 0 || working}
                onClick={() => setFileOffset(fileOffset - 20)}
              >
                Anterior
              </button>
              <span>
                {fileOffset + 1}–{Math.min(fileOffset + 20, fileTotal)} /{" "}
                {fileTotal}
              </span>
              <button
                disabled={fileOffset + 20 >= fileTotal || working}
                onClick={() => setFileOffset(fileOffset + 20)}
              >
                Siguiente
              </button>
            </div>
          )}
        </section>
        <section className="panel import-detail">
          <p className="eyebrow">LECTURA Y NORMALIZACIÓN</p>
          <h2>{source?.name ?? "Selecciona o carga un archivo"}</h2>
          {job && (
            <div
              role="status"
              className={job.status === "failed" ? "error" : "notice"}
            >
              {job.status === "queued"
                ? "Trabajo en cola…"
                : job.status === "running"
                  ? "Procesando en segundo plano…"
                  : job.status === "failed"
                    ? job.error
                    : "Trabajo completado."}
              {job.status === "failed" && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void retry()}
                >
                  Reintentar
                </button>
              )}
            </div>
          )}
          {source && (
            <p className="hash">
              SHA-256 del original <code>{source.sha256}</code>
            </p>
          )}
          {source?.manifest && (
            <>
              <p className="muted">
                {source.manifest.total_rows} registros ·{" "}
                {source.manifest.blank_rows} filas vacías omitidas.{" "}
                {source.manifest.preview_note}
              </p>
              {source.manifest.csv_options && (
                <p className="muted">
                  CSV: {source.manifest.csv_options.encoding} · separador{" "}
                  {JSON.stringify(source.manifest.csv_options.delimiter)}
                </p>
              )}
              <fieldset className="sheet-selection">
                <legend>Hojas que deseas importar</legend>
                {source.manifest.sheets.map((s) => (
                  <label key={s.name}>
                    <input
                      type="checkbox"
                      disabled={!s.rows || working}
                      checked={selectedSheets.includes(s.name)}
                      onChange={(e) => {
                        setSelectedSheets(
                          e.target.checked
                            ? [...selectedSheets, s.name]
                            : selectedSheets.filter((n) => n !== s.name),
                        );
                        setConfirmed(false);
                      }}
                    />
                    {s.name} ({s.rows})
                  </label>
                ))}
              </fieldset>
              <label htmlFor="sheet">Ver columnas y muestra de</label>
              <select
                id="sheet"
                value={activeSheet}
                onChange={(e) => setActiveSheet(e.target.value)}
              >
                {source.manifest.sheets.map((s) => (
                  <option key={s.name}>{s.name}</option>
                ))}
              </select>
              {sheet && (
                <>
                  <div className="table-scroll">
                    <table>
                      <caption>
                        Vista previa · {sheet.name} · cabecera en fila{" "}
                        {sheet.header_row}
                      </caption>
                      <thead>
                        <tr>
                          <th>Fila</th>
                          {sheet.columns.map((c) => (
                            <th key={c.id}>
                              {c.label} <small>({c.id})</small>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sheet.preview.map((row) => (
                          <tr key={row.row}>
                            <th>
                              {row.row}
                              {row.line_end !== row.row
                                ? `–${row.line_end}`
                                : ""}
                            </th>
                            {row.values.map((v, i) => (
                              <td key={i}>{clip(v)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {sheet.formula_rows > 0 && (
                    <p className="notice">
                      {sheet.formula_rows} filas contienen fórmulas. Se
                      conservarán como texto y se excluirán de los campos
                      normalizados.
                    </p>
                  )}
                  <form onSubmit={startImport}>
                    <h3>Asignación de columnas · {sheet.name}</h3>
                    <p className="muted">
                      Las sugerencias por nombre requieren tu revisión. Asigna
                      al menos un campo por hoja seleccionada; una columna no
                      puede representar varios campos.
                    </p>
                    <div className="mapping-grid">
                      {fields.map(([key, label]) => (
                        <div key={key}>
                          <label htmlFor={`map-${key}`}>{label}</label>
                          <select
                            id={`map-${key}`}
                            disabled={working}
                            value={mapping[key] ?? ""}
                            onChange={(e) => {
                              const next = { ...mapping };
                              if (e.target.value) next[key] = e.target.value;
                              else delete next[key];
                              setMappings({ ...mappings, [activeSheet]: next });
                              setConfirmed(false);
                            }}
                          >
                            <option value="">Sin asignar</option>
                            {sheet.columns.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.label} ({c.id})
                              </option>
                            ))}
                          </select>
                        </div>
                      ))}
                    </div>
                    <div className="mapping-grid">
                      <div>
                        <label htmlFor="date-format">Formato de fecha</label>
                        <select
                          id="date-format"
                          value={dateFormat}
                          disabled={working}
                          onChange={(e) => {
                            setDateFormat(e.target.value);
                            setConfirmed(false);
                          }}
                        >
                          <option value="iso8601">
                            ISO 8601 / fecha de Excel
                          </option>
                          <option value="dmy">DD/MM/AAAA HH:mm:ss</option>
                          <option value="mdy">MM/DD/AAAA HH:mm:ss</option>
                          <option value="epoch_seconds">
                            Unix en segundos
                          </option>
                          <option value="epoch_milliseconds">
                            Unix en milisegundos
                          </option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="import-zone">
                          Zona horaria del archivo
                        </label>
                        <input
                          id="import-zone"
                          value={timezone}
                          disabled={working}
                          onChange={(e) => {
                            setTimezone(e.target.value);
                            setConfirmed(false);
                          }}
                          required
                          maxLength={100}
                        />
                      </div>
                    </div>
                    <p className="muted">
                      La zona se aplica a fechas sin offset. Fechas ausentes,
                      inválidas o ambiguas se conservarán con advertencias y sin
                      hora UTC; no se podrán usar para correlación temporal.
                    </p>
                    <label className="confirm">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        disabled={working}
                        onChange={(e) => setConfirmed(e.target.checked)}
                      />
                      Revisé el mapeo de las {selectedSheets.length} hojas
                      seleccionadas, el formato de fecha y la zona horaria.
                    </label>
                    {!validMappings && (
                      <p className="notice">
                        Asigna al menos un campo por cada hoja seleccionada y
                        evita asignar una columna a varios campos.
                      </p>
                    )}
                    <button
                      className="primary"
                      disabled={working || !confirmed || !validMappings}
                    >
                      Importar eventos
                    </button>
                  </form>
                </>
              )}
            </>
          )}
        </section>
      </div>
      {!!runs.length && (
        <section className="panel events-panel">
          <p className="eyebrow">03 / REVISAR LA IMPORTACIÓN</p>
          <h2>Eventos y trazabilidad</h2>
          <label htmlFor="run">Versión de importación</label>
          <select
            id="run"
            value={runId}
            onChange={(e) => {
              setRunId(e.target.value);
              setOffset(0);
              setIssueOffset(0);
            }}
          >
            {runs.map((r, i) => (
              <option key={r.id} value={r.id}>
                Versión {runs.length - i} · {r.summary.accepted} aceptados ·{" "}
                {r.config.timezone} · {r.config.date_format}
              </option>
            ))}
          </select>
          <p className="muted">
            Cada versión conserva su configuración. La tabla muestra únicamente
            los eventos de la versión seleccionada.
          </p>
          {run && (
            <>
              <div className="import-stats">
                {[
                  ["Filas", run.summary.total],
                  ["Aceptadas", run.summary.accepted],
                  ["Rechazadas", run.summary.rejected],
                  ["Con advertencias", run.summary.with_warnings],
                  ["Sin hora válida", run.summary.without_valid_time],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <strong>{value}</strong>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
              <ul className="warning-list">
                {Object.entries(run.summary.warnings).map(([w, count]) => (
                  <li key={w}>
                    {warningLabel(w)} ({count})
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="table-scroll">
            <table>
              <caption>Eventos aceptados · fechas normalizadas a UTC</caption>
              <thead>
                <tr>
                  <th>Origen</th>
                  <th>Fecha UTC</th>
                  <th>Usuario</th>
                  <th>IP origen</th>
                  <th>Evento / resultado</th>
                  <th>Advertencias</th>
                  <th>Evidencia</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.sheet} · fila {e.row}
                      {e.row !== e.line_end ? `–${e.line_end}` : ""}
                    </td>
                    <td>{e.timestamp_utc ?? "Sin fecha válida"}</td>
                    <td>{clip(e.normalized.user)}</td>
                    <td>{clip(e.normalized.source_ip)}</td>
                    <td>
                      {clip(e.normalized.event_type)} /{" "}
                      {clip(e.normalized.result)}
                    </td>
                    <td>{e.warnings.length}</td>
                    <td>
                      <button
                        className="secondary"
                        onClick={() => {
                          api<Evidence>(`cases/${caseId}/events/${e.id}`)
                            .then(setEvidence)
                            .catch((err) => setError(err.message));
                        }}
                      >
                        Ver original · fila {e.row}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button disabled={!offset} onClick={() => setOffset(offset - 20)}>
              Anterior
            </button>
            <span>
              {eventTotal ? offset + 1 : 0}–{Math.min(offset + 20, eventTotal)}{" "}
              de {eventTotal}
            </span>
            <button
              disabled={offset + 20 >= eventTotal}
              onClick={() => setOffset(offset + 20)}
            >
              Siguiente
            </button>
          </div>
          {evidence && (
            <section className="evidence" aria-label="Detalle de evidencia">
              <div className="panel-title">
                <h3>
                  {evidence.file_name} · {evidence.sheet} · fila {evidence.row}
                </h3>
                <button className="secondary" onClick={() => setEvidence(null)}>
                  Cerrar detalle
                </button>
              </div>
              <p className="hash">
                <code>{evidence.sha256}</code>
              </p>
              <ul>
                {evidence.warnings.map((w, i) => (
                  <li key={i}>{warningLabel(w)}</li>
                ))}
              </ul>
              <div className="table-scroll">
                <table>
                  <caption>
                    Valores originales conservados; no se ejecuta su contenido
                  </caption>
                  <thead>
                    <tr>
                      <th>Columna</th>
                      <th>Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.original.map((v, i) => (
                      <tr key={i}>
                        <th>
                          {evidence.columns[i]?.label ?? `Columna ${i + 1}`} (
                          {evidence.columns[i]?.id ?? i})
                        </th>
                        <td className="raw-value">{v ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {issueTotal > 0 && (
            <section>
              <h3>Filas rechazadas ({issueTotal})</h3>
              <ul>
                {issues.map((r) => (
                  <li key={`${r.sheet}-${r.row}`}>
                    {r.sheet} · fila {r.row}–{r.line_end}: {r.reason}
                  </li>
                ))}
              </ul>
              <div className="pagination">
                <button
                  disabled={!issueOffset}
                  onClick={() => setIssueOffset(issueOffset - 20)}
                >
                  Anteriores
                </button>
                <span>
                  {issueOffset + 1}–{Math.min(issueOffset + 20, issueTotal)}
                </span>
                <button
                  disabled={issueOffset + 20 >= issueTotal}
                  onClick={() => setIssueOffset(issueOffset + 20)}
                >
                  Más rechazos
                </button>
              </div>
            </section>
          )}
        </section>
      )}
      <footer>
        Los archivos permanecen en este equipo. Los hallazgos se consultan en
        Análisis de seguridad.
      </footer>
    </main>
  );
}
