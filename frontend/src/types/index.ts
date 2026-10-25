export type ServiceStatus = "healthy" | "degraded" | "down" | "unknown";
export type IncidentStatus = "open" | "investigating" | "resolved";
export type AIAnalysisStatus =
  | "processing"
  | "completed"
  | "failed"
  | "unavailable"
  | "not_generated";
export type EventLevel = "INFO" | "WARN" | "ERROR" | "FATAL" | "METRIC";
export type Severity = "P1" | "P2" | "P3";

export interface OkResponse<T> {
  status: "ok";
  data: T;
}

export interface OkListResponse<T> {
  status: "ok";
  data: T[];
  count: number;
}

export interface ErrorResponse {
  status: "error";
  message: string;
  code: number;
}

export interface Service {
  id: number;
  name: string;
  environment: string;
  description: string | null;
  status: ServiceStatus;
  last_seen_at: string | null;
  created_at: string | null;
  open_incident_count: number;
  latest_latency_p99: number | null;
  latest_error_rate: number | null;
  highest_open_severity: Severity | string | null;
}

export interface ServiceDetail {
  id: number;
  name: string;
  environment: string;
  description: string | null;
  status: ServiceStatus;
  last_seen_at: string | null;
  created_at: string | null;
  recent_incident_count: number;
  recent_events: Event[];
  active_incidents: Incident[];
}

export interface Event {
  id: number;
  service_id: number;
  level: EventLevel | string;
  message: string | null;
  payload: Record<string, unknown> | null;
  source: string | null;
  timestamp: string | null;
}

export interface Metric {
  id: number;
  service_id: number;
  metric_name: string;
  value: number;
  unit: string | null;
  timestamp: string | null;
}

export interface Incident {
  id: number;
  service_id: number;
  service_name: string | null;
  title: string;
  status: IncidentStatus | string;
  severity: Severity | string | null;
  detection_type: string | null;
  started_at: string | null;
  resolved_at: string | null;
  postmortem: string | null;
  created_at: string | null;
}

export interface IncidentDetail extends Incident {
  ai_summary: string | null;
  ai_root_cause: string | null;
  ai_affected_components: string[] | null;
  ai_remediation_steps: string[] | null;
  ai_confidence: number | null;
  ai_analyzed_at: string | null;
  ai_analysis_status: AIAnalysisStatus;
  alerts: Alert[];
}

export interface Alert {
  id: number;
  incident_id: number;
  service_id: number;
  rule: string;
  threshold_value: number | null;
  observed_value: number | null;
  fired_at: string | null;
  acknowledged: boolean;
}

export interface AIReport {
  ai_summary: string | null;
  ai_root_cause: string | null;
  ai_affected_components: string[] | null;
  ai_remediation_steps: string[] | null;
  ai_confidence: number | null;
  ai_analyzed_at: string | null;
  ai_analysis_status: AIAnalysisStatus;
}

export interface WSEventMessage {
  type: "event";
  data: Event;
}

export type WSMessage = WSEventMessage;

export interface MetricDataPoint {
  timestamp: string;
  cpu_pct: number | null;
  error_rate: number | null;
}
