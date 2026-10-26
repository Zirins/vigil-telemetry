import type {
  ErrorResponse,
  Event,
  Incident,
  IncidentDetail,
  OkListResponse,
  OkResponse,
  Service,
  ServiceDetail,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  const body = (await response.json()) as T | ErrorResponse;

  if (
    typeof body === "object" &&
    body !== null &&
    "status" in body &&
    body.status === "error"
  ) {
    throw new Error(body.message);
  }

  return body as T;
}

export async function getServices(): Promise<Service[]> {
  const result = await request<OkListResponse<Service>>("/services");
  return result.data;
}

export async function getService(id: number): Promise<ServiceDetail> {
  const result = await request<OkResponse<ServiceDetail>>(`/services/${id}`);
  return result.data;
}

export interface GetEventsParams {
  limit?: number;
  offset?: number;
  level?: string;
  since?: string;
  until?: string;
}

export async function getEvents(
  serviceId: number,
  params: GetEventsParams = {}
): Promise<Event[]> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.level) search.set("level", params.level);
  if (params.since) search.set("since", params.since);
  if (params.until) search.set("until", params.until);

  const query = search.toString();
  const path = `/events/${serviceId}${query ? `?${query}` : ""}`;
  const result = await request<OkListResponse<Event>>(path);
  return result.data;
}

export interface GetIncidentsParams {
  status?: string;
  serviceId?: number;
  limit?: number;
  offset?: number;
}

export async function getIncidents(
  params: GetIncidentsParams = {}
): Promise<Incident[]> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.serviceId !== undefined) {
    search.set("service_id", String(params.serviceId));
  }
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));

  const query = search.toString();
  const path = `/incidents${query ? `?${query}` : ""}`;
  const result = await request<OkListResponse<Incident>>(path);
  return result.data;
}

export async function getIncident(id: number): Promise<IncidentDetail> {
  const result = await request<OkResponse<IncidentDetail>>(`/incidents/${id}`);
  return result.data;
}

export async function resolveIncident(
  id: number,
  postmortem?: string
): Promise<Incident> {
  const result = await request<OkResponse<Incident>>(
    `/incidents/${id}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ postmortem: postmortem ?? null }),
    }
  );
  return result.data;
}
