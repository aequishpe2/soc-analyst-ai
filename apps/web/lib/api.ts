export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `La solicitud falló (${response.status}).`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (typeof data.message === "string") message = data.message;
      else if (response.status === 422)
        message = "Revisa los campos de la solicitud.";
    } catch {
      /* A proxy may return a non-JSON error. */
    }
    throw new Error(message);
  }
  return response.json();
}

export const warningLabels: Record<string, string> = {
  timestamp_missing:
    "Sin fecha asignada: no se podrá correlacionar por tiempo.",
  timestamp_invalid: "Fecha no válida para el formato seleccionado.",
  timestamp_dst_ambiguous:
    "Hora ambigua por cambio de horario: requiere un offset explícito.",
  timestamp_dst_nonexistent: "Hora inexistente por cambio de horario.",
  formula_present: "Se conserva una fórmula como texto; no se ejecutó.",
  duplicate_preserved: "Fila idéntica a otra: se conserva su evidencia.",
};
export function warningLabel(value: string) {
  if (value.startsWith("formula_excluded:"))
    return "Un campo con fórmula se excluyó de la normalización.";
  if (value.startsWith("invalid_ip:"))
    return "Una IP no tiene un formato válido; se conserva el original.";
  return warningLabels[value] ?? value;
}
