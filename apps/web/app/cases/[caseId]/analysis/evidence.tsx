"use client";
import { useEffect, useState } from "react";
import { api, warningLabel } from "../../../../lib/api";

type Original = {
  file_name: string;
  sha256: string;
  sheet: string;
  row: number;
  line_end: number;
  columns: { id: string; label: string; original_label?: string }[];
  original: (string | null)[];
  warnings: string[];
};
type Reference = {
  id: string;
  role: string;
  file_name: string;
  sha256: string;
  sheet: string;
  row: number;
  line_end: number;
  timestamp_utc: string | null;
  timestamp?: string | null;
  normalized: Record<string, string | null>;
};
export function OriginalEvidence({
  caseId,
  eventId,
}: {
  caseId: string;
  eventId: string;
}) {
  const [data, setData] = useState<Original | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let ignore = false;
    setData(null);
    setError("");
    api<Original>(`cases/${caseId}/events/${eventId}`)
      .then((d) => {
        if (!ignore) setData(d);
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [caseId, eventId]);
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p role="status">Recuperando evidencia original…</p>;
  return (
    <section className="evidence">
      <h4>
        {data.file_name} · {data.sheet} · fila {data.row}
        {data.line_end !== data.row ? `–${data.line_end}` : ""}
      </h4>
      <p className="hash">
        SHA-256 <code>{data.sha256}</code>
      </p>
      <ul>
        {data.warnings.map((w, i) => (
          <li key={i}>{warningLabel(w)}</li>
        ))}
      </ul>
      <div className="table-scroll">
        <table>
          <caption>Valores originales conservados como datos</caption>
          <thead>
            <tr>
              <th>Columna</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            {data.original.map((v, i) => (
              <tr key={i}>
                <th>
                  {data.columns[i]?.original_label ??
                    data.columns[i]?.label ??
                    `Columna ${i + 1}`}
                </th>
                <td className="raw-value">{v ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
export default function FindingEvidence({
  caseId,
  analysisId,
  findingId,
}: {
  caseId: string;
  analysisId: string;
  findingId: string;
}) {
  const [rows, setRows] = useState<Reference[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [original, setOriginal] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let ignore = false;
    setRows([]);
    setError("");
    api<{ items: Reference[]; total: number }>(
      `analyses/${analysisId}/findings/${findingId}/evidence?offset=${offset}`,
    )
      .then((data) => {
        if (!ignore) {
          setRows(data.items);
          setTotal(data.total);
        }
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [analysisId, findingId, offset]);
  return (
    <section aria-label="Evidencias del hallazgo">
      <h4>Registros que sustentan la condición ({total})</h4>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="table-scroll">
        <table>
          <caption>Archivo, hoja y fila de cada referencia</caption>
          <thead>
            <tr>
              <th>Fuente</th>
              <th>Fecha y hora</th>
              <th>Usuario / origen</th>
              <th>Papel</th>
              <th>Original</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.file_name}
                  <br />
                  {r.sheet} · fila {r.row}
                  {r.line_end !== r.row ? `–${r.line_end}` : ""}
                </td>
                <td>{r.timestamp ?? r.timestamp_utc ?? "Sin fecha válida"}</td>
                <td>
                  {r.normalized.user ?? "—"}
                  <br />
                  {r.normalized.source_ip ?? r.normalized.source_host ?? "—"}
                </td>
                <td>
                  {r.role === "failure"
                    ? "Fallo previo"
                    : r.role === "success"
                      ? "Acceso posterior"
                      : "Condición observada"}
                </td>
                <td>
                  <button
                    className="secondary"
                    onClick={() => setOriginal(r.id)}
                  >
                    Ver fila {r.row}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <button disabled={!offset} onClick={() => setOffset(offset - 20)}>
          Anteriores
        </button>
        <span>
          {total ? offset + 1 : 0}–{Math.min(offset + 20, total)} / {total}
        </span>
        <button
          disabled={offset + 20 >= total}
          onClick={() => setOffset(offset + 20)}
        >
          Siguientes
        </button>
      </div>
      {original && (
        <>
          <button className="secondary" onClick={() => setOriginal("")}>
            Cerrar original
          </button>
          <OriginalEvidence caseId={caseId} eventId={original} />
        </>
      )}
    </section>
  );
}
