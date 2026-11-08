"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

type Case = { id: string; title: string; timezone: string; created_at: string };
type System = { ai_status: string; model: string };

export default function Home() {
  const [cases, setCases] = useState<Case[]>([]);
  const [system, setSystem] = useState<System | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [timezone, setTimezone] = useState("Europe/Stockholm");
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/cases?offset=${offset}&limit=20`);
      if (!response.ok)
        throw new Error(
          "No se pudieron cargar los casos. Comprueba la API y sus migraciones.",
        );
      const data = await response.json();
      setCases(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar los casos.");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    fetch("/api/v1/system")
      .then((r) => (r.ok ? r.json() : null))
      .then(setSystem)
      .catch(() => setSystem(null));
  }, []);

  async function createCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/v1/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, timezone }),
      });
      if (!response.ok)
        throw new Error(
          response.status === 422
            ? "Revisa el título y la zona horaria IANA."
            : "No se pudo crear el caso.",
        );
      setTitle("");
      setNotice("Caso creado. Ábrelo para importar los registros.");
      if (offset === 0) await load();
      else setOffset(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al crear el caso.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="workspace">
      <aside>
        <a className="brand" href="/" aria-label="SOC Analyst AI, inicio">
          <span className="mark">S</span>
          <span>
            SOC Analyst<span className="brand-sub">AI WORKSPACE</span>
          </span>
        </a>
        <div className="section-label">ESPACIO DE TRABAJO</div>
        <a href="#cases" className="nav-active">
          ◈ &nbsp; Investigaciones
        </a>
        <div className="sidebar-note">
          <span className="dot" /> Entorno local
          <p>Archivos y análisis bajo tu control.</p>
        </div>
      </aside>
      <main>
        <header>
          <span>
            Operaciones de seguridad <span className="slash">/</span>{" "}
            Investigaciones
          </span>
          <span className="badge">DESARROLLO LOCAL</span>
        </header>
        <section className="heading">
          <div>
            <p className="eyebrow">SOC NIVEL 2 · ANÁLISIS DE EVIDENCIAS</p>
            <h1>
              Cada investigación
              <br />
              empieza con evidencia.
            </h1>
            <p className="intro">
              Organiza tus casos y prepara el análisis de los registros de
              seguridad.
            </p>
          </div>
          <div className="signal" aria-hidden="true">
            <span>◈</span>
            <small>EVIDENCE FIRST</small>
          </div>
        </section>
        <div className="status-strip">
          <div>
            <span className="dot" /> Proveedor local <strong>Ollama</strong>
          </div>
          <div>
            Modelo <strong>{system?.model ?? "Qwen3-8B"}</strong>
          </div>
          <div>
            Estado{" "}
            <strong>
              {system?.ai_status === "ready"
                ? "Modelo disponible"
                : system?.ai_status === "model_missing"
                  ? "Modelo pendiente de descarga"
                  : "Sin conexión a Ollama"}
            </strong>
          </div>
        </div>
        <div className="content-grid">
          <section id="cases" className="panel">
            <div className="panel-title">
              <div>
                <p className="eyebrow">TU ESPACIO DE ANÁLISIS</p>
                <h2>Investigaciones</h2>
              </div>
              <span className="count">{total} casos</span>
            </div>
            {error && (
              <div role="alert" className="error">
                {error}{" "}
                <button type="button" onClick={() => void load()}>
                  Reintentar
                </button>
              </div>
            )}
            {notice && (
              <p role="status" className="notice">
                {notice}
              </p>
            )}
            {loading ? (
              <p role="status" className="empty">
                Cargando investigaciones…
              </p>
            ) : cases.length === 0 && !error ? (
              <div className="empty">
                <span className="empty-icon" aria-hidden="true">
                  ▤
                </span>
                <h3>Tu primer caso, un punto de partida.</h3>
                <p>
                  Crea una investigación para definir su alcance y zona horaria.
                  <br />
                  Todavía no hay eventos ni hallazgos.
                </p>
              </div>
            ) : (
              <ul className="case-list">
                {cases.map((c) => (
                  <li key={c.id}>
                    <span className="case-icon" aria-hidden="true">
                      ▤
                    </span>
                    <div>
                      <h3>{c.title}</h3>
                      <p>
                        {c.timezone} ·{" "}
                        {new Intl.DateTimeFormat("es", {
                          dateStyle: "medium",
                          timeStyle: "short",
                          timeZone: c.timezone,
                        }).format(new Date(c.created_at))}
                      </p>
                      <small>{c.id}</small>
                    </div>
                    <Link className="secondary" href={`/cases/${c.id}`}>
                      Abrir caso →
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {total > 20 && (
              <div className="pagination">
                <button
                  disabled={offset === 0 || loading}
                  onClick={() => setOffset(offset - 20)}
                >
                  Anterior
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + 20, total)} de {total}
                </span>
                <button
                  disabled={offset + 20 >= total || loading}
                  onClick={() => setOffset(offset + 20)}
                >
                  Siguiente
                </button>
              </div>
            )}
          </section>
          <section className="panel create">
            <p className="eyebrow">01 / PREPARAR</p>
            <h2>Nueva investigación</h2>
            <p>Usa un nombre que identifique el alcance del caso.</p>
            <form onSubmit={createCase}>
              <label htmlFor="title">Nombre del caso</label>
              <input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ej. Revisión de accesos · Cliente A"
                minLength={3}
                maxLength={200}
                required
              />
              <label htmlFor="timezone">Zona horaria de los registros</label>
              <input
                id="timezone"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                required
                maxLength={100}
                aria-describedby="tz-help"
              />
              <small id="tz-help">
                Formato IANA. Confirma la zona del archivo; la ubicación del
                cliente puede ser diferente.
              </small>
              <button
                className="primary"
                disabled={saving || title.trim().length < 3}
              >
                {saving ? "Creando…" : "Crear investigación →"}
              </button>
            </form>
          </section>
        </div>
        <section className="roadmap">
          <h2>El camino de la evidencia</h2>
          <div>
            {[
              ["01", "Preparar", "Crear y organizar casos", true],
              ["02", "Importar", "Excel y CSV", true],
              ["03", "Investigar", "Reglas con evidencias", true],
              ["04", "Informar", "Informe PDF · Próximamente", false],
            ].map(([n, t, d, active]) => (
              <div key={String(n)} className={active ? "step active" : "step"}>
                <span>{n}</span>
                <h3>{t}</h3>
                <p>{d}</p>
              </div>
            ))}
          </div>
        </section>
        <footer>
          Motor de reglas disponible · IA e informes en desarrollo.
          <span>Las conclusiones deberán estar sustentadas en registros.</span>
        </footer>
      </main>
    </div>
  );
}
