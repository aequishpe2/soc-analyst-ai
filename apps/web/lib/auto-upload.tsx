"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";

export default function AutoUpload({ caseId }: { caseId?: string }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  async function upload(file?: File) {
    if (!file || busy) return;
    setError("");
    if (!/\.(xlsx|csv)$/i.test(file.name)) {
      setError("Selecciona un archivo .xlsx o .csv.");
      return;
    }
    if (file.size > 20 * 1024 * 1024 || file.size === 0) {
      setError("El archivo debe tener contenido y no superar 20 MB.");
      return;
    }
    setBusy(true);
    try {
      setPhase("Preparando investigación…");
      const identifier =
        caseId ??
        (
          await api<{ id: string }>("cases", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title: `Análisis · ${file.name.replace(/\.[^.]+$/, "").slice(0, 170)}`,
            }),
          })
        ).id;
      setPhase("Cargando el archivo…");
      const form = new FormData();
      form.append("file", file);
      const uploaded = await api<{
        file: { id: string };
        job: { id: string; status: string };
      }>(`cases/${identifier}/files`, { method: "POST", body: form });
      if (uploaded.job.status === "failed")
        await api(`jobs/${uploaded.job.id}/retry`, { method: "POST" });
      setPhase("Iniciando reconocimiento y análisis…");
      const run = await api<{ id: string }>(
        `cases/${identifier}/files/${uploaded.file.id}/automatic`,
        { method: "POST" },
      );
      router.push(`/cases/${identifier}/overview?run=${run.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <section
      className={`auto-upload panel ${dragging ? "dragging" : ""}`}
      aria-label="Cargar y analizar archivo"
      onDragOver={(event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (event.dataTransfer.files.length !== 1) {
          setError("Carga un archivo cada vez.");
          return;
        }
        void upload(event.dataTransfer.files[0]);
      }}
    >
      <input
        ref={input}
        hidden
        type="file"
        accept=".xlsx,.csv"
        disabled={busy}
        aria-label="Archivo para análisis automático"
        onChange={(e) => {
          void upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <button
        className="upload-zone"
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
      >
        <span className="upload-symbol" aria-hidden="true">
          ↥
        </span>
        <strong>{busy ? phase : "Arrastra tu Excel o CSV aquí"}</strong>
        <span>
          {busy
            ? "Conservamos el original y preparamos tu dashboard."
            : "o pulsa para seleccionar el archivo y analizarlo"}
        </span>
      </button>
      <p className="muted">
        XLSX / CSV · Hasta 20 MB · Análisis y modelo de IA en tu equipo
      </p>
      <div className="upload-steps">
        <span>01 · Reconocer columnas</span>
        <span>02 · Detectar y correlacionar</span>
        <span>03 · Explicar con IA</span>
      </div>
      {busy && <p role="status">{phase}</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
