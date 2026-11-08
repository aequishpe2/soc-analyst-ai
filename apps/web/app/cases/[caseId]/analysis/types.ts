export type Scope = {
  id: string;
  file_id: string;
  name: string;
  sha256: string;
  summary: { accepted: number; rejected: number };
  config: { date_format?: string };
  profile_hint?: string | null;
  created_at: string;
};
export type Coverage = {
  rule_id: string;
  title: string;
  status: string;
  eligible_events: number;
  excluded_reasons: Record<string, number>;
  findings: number;
};
export type Summary = {
  input_events: number;
  unique_events: number;
  duplicate_events: number;
  excluded_events: number;
  conflicting_semantics: number;
  findings: number;
  investigation_groups: number;
  by_severity: Record<string, number>;
  coverage: Coverage[];
  import_rejected_rows: number;
  limitations: string;
  sources: { name: string; sha256: string; import_id: string }[];
};
export type Analysis = {
  id: string;
  case_id: string;
  status: string;
  error: string | null;
  input_hash: string | null;
  created_at: string;
  summary: Summary | null;
  config: {
    engine_version: string;
    ruleset_version: string;
    import_ids: string[];
    settings: Settings;
  };
};
export type Settings = {
  source_profile: string;
  brute_min: number;
  brute_window: number;
  spray_min: number;
  spray_window: number;
  success_min: number;
  success_window: number;
  lateral_min: number;
  lateral_window: number;
  correlation_window: number;
  business_hours: {
    weekdays: number[];
    start: string;
    end: string;
  } | null;
  excluded_users: string[];
  excluded_source_ips: string[];
  privileged_groups: string[];
};
export type Finding = {
  id: string;
  group_id: string;
  rule_id: string;
  title: string;
  severity: string;
  confidence: string;
  reason: string;
  observed: Record<string, unknown>;
  limitations: string;
  potential_impact: string;
  actions: string[];
  start: string | null;
  end: string | null;
  evidence_count: number;
  attack_reference: string | null;
};
export type Group = {
  id: string;
  finding_ids: string[];
  links: {
    from: string;
    to: string;
    kind: string;
    user?: string;
    asset?: string;
    event_id?: string;
  }[];
  interpretation: string;
};
export const statusLabels: Record<string, string> = {
  queued: "En cola",
  running: "En curso",
  succeeded: "Completado",
  failed: "Fallido",
  evaluated: "Evaluada",
  partial: "Parcial",
  not_evaluable: "No evaluable",
  not_applicable: "No aplicable",
};
export const reasonLabels: Record<string, string> = {
  not_applicable: "Evento ajeno a esta condición",
  unknown_event_type: "Tipo de evento no reconocido",
  unknown_outcome: "Resultado no reconocido",
  conflicting_semantics: "Tipo, resultado o código contradictorios",
  remote_type_not_established: "No se establece que el acceso sea remoto",
  missing_valid_timestamp: "Sin fecha válida",
  missing_user: "Sin usuario válido",
  missing_valid_source: "Sin IP o equipo de origen válido",
  missing_distinct_destination: "Sin destino distinto del origen",
  calendar_file_time_missing:
    "No se dispone de una hora local explícita en el archivo",
  calendar_not_configured: "Calendario no configurado",
  missing_privileged_target:
    "Sin grupo o privilegio privilegiado identificable",
  missing_command_or_process: "Sin comando ni proceso",
};
