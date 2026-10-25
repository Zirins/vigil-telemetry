"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { AppNav } from "@/components/AppNav";
import { ServiceRow } from "@/components/ServiceRow";
import { Skeleton } from "@/components/ui/skeleton";
import * as api from "@/lib/api";
import { cn } from "@/lib/utils";

const ENV_FILTERS = ["all", "production", "staging", "dev"] as const;

const STATUS_DOT: Record<string, string> = {
  open: "bg-red-500",
  investigating: "bg-amber-500",
  resolved: "bg-emerald-500",
};

const SEVERITY_BADGE: Record<string, string> = {
  P1: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30 font-bold",
  P2: "bg-transparent text-amber-700 dark:text-amber-400 border-amber-500/30 font-medium",
  P3: "bg-transparent text-muted-foreground border-border font-normal",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatIncidentTitle(title: string): string {
  const t = title.trim();
  if (t.startsWith("error_rate detected")) {
    return "Elevated 5xx error rate";
  }
  if (t.startsWith("rage_pattern detected") || t.startsWith("cascade_failure detected")) {
    return "Repeated failure burst";
  }
  if (t.startsWith("spike detected on cpu_pct")) {
    return "CPU utilization spike (>85%)";
  }
  if (t.startsWith("spike detected on error_rate")) {
    return "Error rate anomaly spike";
  }
  return t.replace(/_/g, " ");
}

export default function HomePage() {
  const [envFilter, setEnvFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const { data, isLoading, error } = useQuery({
    queryKey: ["services"],
    queryFn: api.getServices,
    refetchInterval: 10_000,
  });

  const { data: incidents } = useQuery({
    queryKey: ["incidents", "recent"],
    queryFn: () => api.getIncidents({ limit: 15 }),
    refetchInterval: 10_000,
  });

  const filteredServices = useMemo(() => {
    if (!data) return [];
    return data.filter((service) => {
      const envOk =
        envFilter === "all" ||
        service.environment.toLowerCase() === envFilter.toLowerCase();
      const statusOk =
        statusFilter === "all" || service.status === statusFilter;
      const searchOk =
        !searchQuery.trim() ||
        service.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        service.environment.toLowerCase().includes(searchQuery.toLowerCase());
      return envOk && statusOk && searchOk;
    });
  }, [data, envFilter, statusFilter, searchQuery]);

  const serviceNameById = useMemo(() => {
    const map = new Map<number, string>();
    data?.forEach((service) => map.set(service.id, service.name));
    return map;
  }, [data]);

  function incidentServiceLabel(incident: {
    service_id: number;
    service_name?: string | null;
  }) {
    return (
      incident.service_name ??
      serviceNameById.get(incident.service_id) ??
      `svc:${incident.service_id}`
    );
  }

  const totalServices = data?.length ?? 0;
  const healthyCount = data?.filter((s) => s.status === "healthy").length ?? 0;
  const downCount = data?.filter((s) => s.status === "down").length ?? 0;
  const degradedCount = data?.filter((s) => s.status === "degraded").length ?? 0;
  const totalIncidents =
    data?.reduce((sum, s) => sum + s.open_incident_count, 0) ?? 0;

  const latencyValues = useMemo(() => {
    if (!data) return [];
    return data
      .map((s) =>
        s.latest_latency_p99 !== null && s.latest_latency_p99 !== undefined
          ? Number(s.latest_latency_p99)
          : null
      )
      .filter((v): v is number => v !== null && !isNaN(v));
  }, [data]);


  const maxLatency = useMemo(() => {
    if (latencyValues.length === 0) return null;
    return Math.round(Math.max(...latencyValues));
  }, [latencyValues]);

  const minLatency = useMemo(() => {
    if (latencyValues.length === 0) return null;
    return Math.round(Math.min(...latencyValues));
  }, [latencyValues]);

  const latestSignalMs = useMemo(() => {
    if (!data || data.length === 0) return null;
    const timestamps = data
      .map((s) => (s.last_seen_at ? new Date(s.last_seen_at).getTime() : 0))
      .filter((t) => t > 0);
    return timestamps.length > 0 ? Math.max(...timestamps) : null;
  }, [data]);

  const isTelemetryStale = useMemo(() => {
    if (!latestSignalMs) return false;
    return Date.now() - latestSignalMs > 60 * 60 * 1000;
  }, [latestSignalMs]);

  const staleTimeAgo = useMemo(() => {
    if (!latestSignalMs) return null;
    return timeAgo(new Date(latestSignalMs).toISOString());
  }, [latestSignalMs]);

  const healthPct = totalServices > 0 ? (healthyCount / totalServices) * 100 : 0;
  const healthBadgeStyle =
    healthPct === 100
      ? "text-emerald-800 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-500/10 dark:border-emerald-500/30"
      : healthPct >= 80
      ? "text-amber-800 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-500/10 dark:border-amber-500/30"
      : "text-red-800 bg-red-50 border-red-200 dark:text-red-400 dark:bg-red-500/10 dark:border-red-500/30";

  const highestSeverity = useMemo(() => {
    if (!data || totalIncidents === 0) return null;
    const severities = new Set(
      data
        .map((s) => s.highest_open_severity)
        .filter((sev): sev is string => Boolean(sev))
    );
    if (severities.has("P1")) return "P1";
    if (severities.has("P2")) return "P2";
    if (severities.has("P3")) return "P3";
    return null;
  }, [data, totalIncidents]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppNav />

      <main className="mx-auto max-w-[1380px] px-4 py-4 sm:px-6 space-y-4">
        
        {/* Telemetry Stale State Banner */}
        {isTelemetryStale ? (
          <div className="flex items-center justify-between gap-3 px-3.5 py-2 rounded border border-amber-500/30 bg-amber-500/[0.05] text-amber-800 dark:text-amber-300 text-xs font-mono">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              <span>
                Telemetry stream offline — last signal received {staleTimeAgo}. Displaying last known system state.
              </span>
            </div>
            <span className="hidden sm:inline text-[10px] text-muted-foreground uppercase tracking-wider">
              Snapshot Mode
            </span>
          </div>
        ) : null}

        {/* Operational KPI Hierarchy */}
        {data && data.length > 0 ? (
          <div className="bg-card border border-border rounded divide-y lg:divide-y-0 lg:divide-x divide-border grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            
            {/* Primary Hero: Fleet Operational Health (Spans 2 columns on lg) */}
            <div className="p-4 lg:col-span-2 flex flex-col justify-between">
              <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                <span>Fleet Operational Status</span>
                <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-bold border", healthBadgeStyle)}>
                  {healthPct.toFixed(1)}% {healthPct === 100 ? "HEALTHY" : healthPct >= 80 ? "DEGRADED" : "CRITICAL"}
                </span>
              </div>
              <div className="my-2 flex items-baseline gap-2.5">
                <span className="text-3xl font-bold font-mono tracking-tight text-foreground">
                  {healthyCount} / {totalServices}
                </span>
                <span className="text-xs text-muted-foreground font-mono">
                  services healthy
                </span>
              </div>
              
              {/* Segmented status blocks with service breakdown */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-1 h-2 w-full">
                  {data.map((s) => (
                    <div
                      key={s.id}
                      className={cn(
                        "flex-1 h-full rounded-xs",
                        s.status === "healthy"
                          ? "bg-emerald-500"
                          : s.status === "degraded"
                          ? "bg-amber-500"
                          : "bg-red-500"
                      )}
                      title={`${s.name}: ${s.status}`}
                    />
                  ))}
                </div>
                <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground pt-1">
                  <span className="flex items-center gap-3">
                    <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                      {downCount} Down
                    </span>
                    <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                      {degradedCount} Degraded
                    </span>
                    <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      {healthyCount} Healthy
                    </span>
                  </span>
                  <span>{totalServices} total</span>
                </div>
              </div>
            </div>

            {/* Metric 2: Active Incidents (1 col) */}
            <div className="p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                <span>Active Incidents</span>
                {totalIncidents > 0 ? (
                  highestSeverity === "P1" ? (
                    <span className="font-bold text-red-900 bg-red-100 dark:bg-red-500/20 dark:text-red-300 px-1.5 py-0.5 rounded border border-red-300 dark:border-red-500/30 text-[10px]">
                      P1 CRITICAL
                    </span>
                  ) : highestSeverity === "P2" ? (
                    <span className="font-bold text-amber-900 bg-amber-100 dark:bg-amber-500/20 dark:text-amber-300 px-1.5 py-0.5 rounded border border-amber-300 dark:border-amber-500/30 text-[10px]">
                      P2 ELEVATED
                    </span>
                  ) : (
                    <span className="font-bold text-blue-900 bg-blue-100 dark:bg-blue-500/20 dark:text-blue-300 px-1.5 py-0.5 rounded border border-blue-300 dark:border-blue-500/30 text-[10px]">
                      P3 ADVISORY
                    </span>
                  )
                ) : (
                  <span className="font-bold text-emerald-800 bg-emerald-50 dark:bg-emerald-500/20 dark:text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-200 text-[10px]">
                    ALL CLEAR
                  </span>
                )}
              </div>
              <div className="my-2 flex items-baseline gap-2">
                <span className="text-3xl font-bold font-mono tracking-tight text-foreground">
                  {totalIncidents}
                </span>
                <span className="text-xs font-mono text-muted-foreground">
                  {totalIncidents === 1 ? "active alert" : "active alerts"}
                </span>
              </div>
              <div className="text-[11px] font-mono text-muted-foreground border-t border-border pt-1.5">
                <span>
                  {data.filter((s) => s.open_incident_count > 0).length} of {totalServices} services affected
                </span>
              </div>
            </div>

            {/* Metric 3: Fleet Telemetry & Latency (1 col) */}
            <div className="p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                <span>Fleet Peak P99</span>
                <span className="text-muted-foreground/70 text-[10px]">
                  {isTelemetryStale ? "last known" : "window 60s"}
                </span>
              </div>
              <div className="my-2 flex items-baseline gap-1.5">
                <span className="text-3xl font-bold font-mono tracking-tight text-foreground">
                  {maxLatency !== null ? maxLatency : "—"}
                </span>
                <span className="text-xs font-mono text-muted-foreground">ms peak</span>
              </div>
              <div className="flex items-center justify-between text-[11px] font-mono border-t border-border pt-1.5 text-muted-foreground">
                <span>Fastest: {minLatency !== null ? `${minLatency} ms` : "—"}</span>
                <span>Reporting: {latencyValues.length}</span>
              </div>
            </div>

          </div>
        ) : null}

        {/* Operational Filter & Control Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            
            {/* Search Input with functional / hotkey */}
            <div className="relative">
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter services by name, env..."
                className="h-8 w-64 pl-3 pr-7 text-xs bg-card border border-border rounded focus:outline-none focus:border-primary text-foreground placeholder:text-muted-foreground font-mono"
              />
              <kbd
                title="Press / to focus search"
                className="absolute right-2 top-2 text-[10px] font-mono text-muted-foreground border border-border px-1.5 py-0.2 rounded bg-muted/60 pointer-events-none select-none"
              >
                /
              </kbd>
            </div>

            {/* Segmented Status Toggle Buttons */}
            <div className="inline-flex rounded border border-border bg-card p-0.5 text-xs font-mono">
              <button
                onClick={() => setStatusFilter("all")}
                className={cn(
                  "px-2.5 py-0.5 rounded-xs transition-colors",
                  statusFilter === "all"
                    ? "bg-foreground text-background font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                ALL ({totalServices})
              </button>
              {downCount > 0 ? (
                <button
                  onClick={() => setStatusFilter("down")}
                  className={cn(
                    "px-2.5 py-0.5 rounded-xs transition-colors",
                    statusFilter === "down"
                      ? "bg-red-600 text-white font-semibold"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  DOWN ({downCount})
                </button>
              ) : null}
              <button
                onClick={() => setStatusFilter("degraded")}
                className={cn(
                  "px-2.5 py-0.5 rounded-xs transition-colors",
                  statusFilter === "degraded"
                    ? "bg-amber-600 text-white font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                DEGRADED ({degradedCount})
              </button>
              <button
                onClick={() => setStatusFilter("healthy")}
                className={cn(
                  "px-2.5 py-0.5 rounded-xs transition-colors",
                  statusFilter === "healthy"
                    ? "bg-emerald-600 text-white font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                HEALTHY ({healthyCount})
              </button>
            </div>

            {/* Environment Dropdown */}
            <select
              value={envFilter}
              onChange={(e) => setEnvFilter(e.target.value)}
              className="h-8 px-2 text-xs bg-card border border-border rounded font-mono text-foreground focus:outline-none focus:border-primary uppercase"
            >
              {ENV_FILTERS.map((env) => (
                <option key={env} value={env}>
                  ENV: {env}
                </option>
              ))}
            </select>

          </div>

          <div className="text-xs font-mono text-muted-foreground">
            <span>{filteredServices.length} of {totalServices} services shown</span>
          </div>
        </div>

        {/* Loading State */}
        {isLoading ? (
          <div className="space-y-px border border-border rounded overflow-hidden">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 rounded-none" />
            ))}
          </div>
        ) : null}

        {/* Error State */}
        {error ? (
          <div className="border border-destructive/30 bg-destructive/10 px-4 py-3 rounded">
            <p className="font-mono text-xs text-destructive">
              {error instanceof Error ? error.message : "failed to load services"}
            </p>
          </div>
        ) : null}

        {/* Main Service Directory Table (High Density) */}
        {filteredServices.length > 0 ? (
          <section aria-label="Service directory" className="bg-card border border-border rounded overflow-hidden shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <div className="hidden grid-cols-[minmax(180px,1.5fr)_110px_100px_100px_110px_130px] gap-3 bg-muted/50 px-3 py-2 text-[11px] font-mono text-muted-foreground uppercase tracking-wider border-b border-border md:grid">
              <span>Service</span>
              <span>Status</span>
              <span className="text-right">P99 Latency</span>
              <span className="text-right">Error Rate</span>
              <span className="text-right">Open Incidents</span>
              <span className="text-right pr-6">Last Signal</span>
            </div>
            <div>
              {filteredServices.map((service) => (
                <ServiceRow key={service.id} service={service} />
              ))}
            </div>
          </section>
        ) : null}

        {data && data.length > 0 && filteredServices.length === 0 ? (
          <div className="border border-dashed border-border rounded px-4 py-8 text-center bg-card">
            <p className="text-sm font-mono text-muted-foreground">
              No services match current filters.
            </p>
          </div>
        ) : null}

        {/* Recent Incidents Panel */}
        <section className="pt-2">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-foreground font-mono uppercase tracking-wider">
                Recent Incidents
              </h2>
              <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.2 rounded border border-border">
                Last 15
              </span>
            </div>
            <Link
              href="/incidents"
              className="text-xs text-primary font-mono hover:underline flex items-center gap-1"
            >
              View incident archive →
            </Link>
          </div>

          {!incidents && isLoading ? (
            <div className="space-y-px border border-border rounded overflow-hidden">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded-none" />
              ))}
            </div>
          ) : null}

          {incidents && incidents.length === 0 ? (
            <div className="border border-dashed border-border bg-card rounded px-4 py-6 text-center">
              <p className="text-xs font-mono text-muted-foreground">
                No incidents recorded in the active fleet window.
              </p>
            </div>
          ) : null}

          {incidents && incidents.length > 0 ? (
            <div className="bg-card border border-border rounded overflow-hidden divide-y divide-border font-mono text-xs">
              {incidents.slice(0, 8).map((incident) => {
                const serviceName = incidentServiceLabel(incident);
                const badgeClass = incident.severity
                  ? SEVERITY_BADGE[incident.severity] ?? "bg-muted text-muted-foreground"
                  : "bg-muted text-muted-foreground";

                return (
                  <Link
                    key={incident.id}
                    href={`/incidents/${incident.id}`}
                    className="block hover:bg-muted/40 transition-colors px-3 py-2.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-mono border", badgeClass)}>
                          {incident.severity ?? "P3"}
                        </span>
                        <span className="font-semibold text-foreground truncate">
                          <span className="text-muted-foreground font-normal">[{serviceName}]</span>{" "}
                          {formatIncidentTitle(incident.title)}
                        </span>
                      </div>

                      <div className="flex items-center gap-4 text-[11px] text-muted-foreground ml-auto">
                        <span className="inline-flex items-center gap-1.5">
                          <span
                            className={cn(
                              "h-1.5 w-1.5 rounded-full",
                              STATUS_DOT[incident.status] ?? "bg-slate-400"
                            )}
                          />
                          {incident.status}
                        </span>
                        <span>{timeAgo(incident.started_at)}</span>
                        <ArrowUpRight className="h-3 w-3 text-muted-foreground/60" />
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : null}
        </section>

      </main>
    </div>
  );
}
