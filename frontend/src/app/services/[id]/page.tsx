"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  AlertTriangle,
  Activity,
  CheckCircle2,
  History,
  ArrowUpRight,
} from "lucide-react";
import { AppNav } from "@/components/AppNav";
import { EventStream } from "@/components/EventStream";
import { MetricChart } from "@/components/MetricChart";
import { StatusBadge, SeverityBadge } from "@/components/ServiceCard";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { Event } from "@/types";

type TabType = "incidents" | "telemetry" | "events";

function formatDetectionType(type: string | null | undefined): string {
  if (!type) return "heuristic";
  if (type === "rage_pattern") return "cascade_failure";
  if (type === "error_rate") return "error_burst";
  return type;
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

function formatPayload(event: Event): string {
  if (event.level === "METRIC" && event.payload) {
    const m = (event.payload.metric as string) ?? "metric";
    const v = event.payload.value;
    if (m === "cpu_pct" && v !== undefined) {
      return `metric=cpu_pct val=${Number(v).toFixed(1)}%`;
    }
    if (m === "error_rate" && v !== undefined) {
      return `metric=error_rate val=${Number(v).toFixed(4)}`;
    }
    const valStr = v !== undefined ? String(v) : "?";
    return `metric=${m} val=${valStr}`;
  }
  return event.message ?? (event.payload ? JSON.stringify(event.payload) : "—");
}

export default function ServiceDetailPage() {
  const params = useParams();
  const serviceId = Number(params.id);
  const [activeTab, setActiveTab] = useState<TabType>("incidents");

  const { data, isLoading, error } = useQuery({
    queryKey: ["service", serviceId],
    queryFn: () => api.getService(serviceId),
    enabled: Number.isFinite(serviceId),
    refetchInterval: 10_000,
  });

  return (
    <div className="min-h-screen bg-background">
      <AppNav />

      <main className="mx-auto max-w-[1380px] px-4 py-4 sm:px-6">
        {/* Back */}
        <Link
          href="/"
          className="mb-4 inline-flex items-center gap-1.5 font-mono text-xs text-muted-foreground/60 transition-colors hover:text-muted-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          services
        </Link>

        {/* Loading */}
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-12 w-full" />
            <div className="grid gap-3 lg:grid-cols-2">
              <Skeleton className="h-[480px] rounded-lg" />
              <Skeleton className="h-[480px] rounded-lg" />
            </div>
            <Skeleton className="h-48 w-full rounded-lg" />
          </div>
        ) : null}

        {/* Error */}
        {error ? (
          <div className="rounded-md border border-destructive/25 bg-destructive/8 px-4 py-3">
            <p className="font-mono text-xs text-red-400">
              {error instanceof Error ? error.message : "failed to load service"}
            </p>
          </div>
        ) : null}

        {/* Content */}
        {data ? (
          <div className="space-y-5">
            {/* Service header */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-xl font-bold font-mono tracking-tight text-foreground">
                  {data.name}
                </h1>
                <StatusBadge status={data.status} />
                <span className="rounded bg-muted/60 px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-muted-foreground">
                  {data.environment}
                </span>
                <span className="font-mono text-xs text-muted-foreground/60">
                  id:{data.id}
                </span>
              </div>
              <div className="flex items-center gap-3 font-mono text-xs text-muted-foreground">
                <span>
                  Last seen: {data.last_seen_at ? new Date(data.last_seen_at).toLocaleTimeString() : "Never"}
                </span>
              </div>
            </div>

            {/* Live Visualizations (2-Column Grid) */}
            <div className="grid gap-3 lg:grid-cols-2">
              <EventStream serviceId={serviceId} initialEvents={data.recent_events} />
              <MetricChart serviceId={serviceId} initialEvents={data.recent_events} />
            </div>

            {/* Contextual SRE Panel */}
            <div className="rounded-lg border border-border bg-card overflow-hidden shadow-sm">
              {/* Tab Navigation */}
              <div className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-2">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setActiveTab("incidents")}
                    className={cn(
                      "flex items-center gap-2 rounded px-3 py-1.5 font-mono text-xs font-medium transition-colors",
                      activeTab === "incidents"
                        ? "bg-background text-foreground shadow-xs border border-border"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    <span>Active Incidents</span>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.2 text-[10px] font-bold font-mono",
                        data.active_incidents.length > 0
                          ? "bg-red-500/15 text-red-600 dark:text-red-400"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {data.active_incidents.length}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab("telemetry")}
                    className={cn(
                      "flex items-center gap-2 rounded px-3 py-1.5 font-mono text-xs font-medium transition-colors",
                      activeTab === "telemetry"
                        ? "bg-background text-foreground shadow-xs border border-border"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <Activity className="h-3.5 w-3.5" />
                    <span>Service Metadata</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab("events")}
                    className={cn(
                      "flex items-center gap-2 rounded px-3 py-1.5 font-mono text-xs font-medium transition-colors",
                      activeTab === "events"
                        ? "bg-background text-foreground shadow-xs border border-border"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <History className="h-3.5 w-3.5" />
                    <span>Recent Events</span>
                    <span className="rounded bg-muted px-1.5 py-0.2 font-mono text-[10px] text-muted-foreground">
                      {data.recent_events.length}
                    </span>
                  </button>
                </div>
              </div>

              {/* Tab Content */}
              <div className="p-4">
                {activeTab === "incidents" && (
                  <div>
                    {data.active_incidents.length === 0 ? (
                      <div className="flex items-center gap-3 rounded border border-border bg-muted/20 px-3.5 py-2.5 font-mono text-xs">
                        <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                        <span className="font-semibold text-emerald-800 dark:text-emerald-400 uppercase tracking-wider text-[11px]">
                          All Systems Nominal
                        </span>
                        <span className="text-muted-foreground/40">•</span>
                        <span className="text-muted-foreground text-[11px]">
                          0 active incidents — all telemetry signals operating within SLA thresholds
                        </span>
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left font-mono text-xs">
                          <thead>
                            <tr className="border-b border-border text-muted-foreground text-[11px] uppercase tracking-wider">
                              <th className="pb-2 font-medium">Incident</th>
                              <th className="pb-2 font-medium">Severity</th>
                              <th className="pb-2 font-medium">Detection</th>
                              <th className="pb-2 font-medium">Status</th>
                              <th className="pb-2 font-medium">Started At</th>
                              <th className="pb-2 font-medium text-right">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {data.active_incidents.map((inc) => (
                              <tr key={inc.id} className="transition-colors hover:bg-muted/30">
                                <td className="py-2.5 font-medium text-foreground">
                                  <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">#{inc.id}</span>
                                    <span>{formatIncidentTitle(inc.title)}</span>
                                  </div>
                                </td>
                                <td className="py-2.5">
                                  <SeverityBadge severity={inc.severity} />
                                </td>
                                <td className="py-2.5 text-muted-foreground">
                                  <span className="rounded bg-muted px-1.5 py-0.5 text-[11px]">
                                    {formatDetectionType(inc.detection_type)}
                                  </span>
                                </td>
                                <td className="py-2.5 capitalize text-amber-600 dark:text-amber-400 font-semibold">
                                  {inc.status}
                                </td>
                                <td className="py-2.5 text-muted-foreground text-[11px]">
                                  {inc.started_at ? new Date(inc.started_at).toLocaleString() : "—"}
                                </td>
                                <td className="py-2.5 text-right">
                                  <Link
                                    href={`/incidents/${inc.id}`}
                                    className="inline-flex items-center gap-1 rounded border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-muted"
                                  >
                                    Inspect
                                    <ArrowUpRight className="h-3 w-3" />
                                  </Link>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "telemetry" && (
                  <div className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Service Identifier
                        </span>
                        <p className="mt-1 font-mono text-sm font-semibold text-foreground">
                          #{data.id} <span className="text-xs font-normal text-muted-foreground">({data.name})</span>
                        </p>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Deployment Environment
                        </span>
                        <p className="mt-1 font-mono text-sm font-semibold uppercase text-foreground">
                          {data.environment}
                        </p>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Operational Status
                        </span>
                        <div className="mt-1">
                          <StatusBadge status={data.status} />
                        </div>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Lifetime Incidents
                        </span>
                        <p className="mt-1 font-mono text-sm font-semibold text-foreground">
                          {data.recent_incident_count} recorded
                        </p>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Last Heartbeat
                        </span>
                        <p className="mt-1 font-mono text-xs text-foreground">
                          {data.last_seen_at ? new Date(data.last_seen_at).toLocaleString() : "Never"}
                        </p>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Registered At
                        </span>
                        <p className="mt-1 font-mono text-xs text-foreground">
                          {data.created_at ? new Date(data.created_at).toLocaleString() : "—"}
                        </p>
                      </div>

                      <div className="rounded border border-border bg-muted/10 p-3 sm:col-span-2">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Active Ingestion Channel
                        </span>
                        <p className="mt-1 font-mono text-xs text-foreground truncate">
                          Native WebSocket /ws/services/{data.id}
                        </p>
                      </div>
                    </div>

                    {data.description ? (
                      <div className="rounded border border-border bg-muted/10 p-3">
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Description
                        </span>
                        <p className="mt-1 text-xs text-foreground">
                          {data.description}
                        </p>
                      </div>
                    ) : null}
                  </div>
                )}

                {activeTab === "events" && (
                  <div>
                    {data.recent_events.length === 0 ? (
                      <p className="py-6 text-center font-mono text-xs text-muted-foreground">
                        No recent historical events recorded for this service.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left font-mono text-xs">
                          <thead>
                            <tr className="border-b border-border text-muted-foreground text-[11px] uppercase tracking-wider">
                              <th className="pb-2 font-medium w-[140px]">Timestamp</th>
                              <th className="pb-2 font-medium w-[70px]">Level</th>
                              <th className="pb-2 font-medium w-[90px]">Source</th>
                              <th className="pb-2 font-medium">Message / Payload</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {data.recent_events.map((evt) => (
                              <tr key={evt.id} className="transition-colors hover:bg-muted/30">
                                <td className="py-2 text-[11px] text-muted-foreground">
                                  {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : "—"}
                                </td>
                                <td className="py-2">
                                  <span
                                    className={cn(
                                      "rounded px-1.5 py-0.5 text-[10px] font-bold font-mono",
                                      evt.level === "ERROR" || evt.level === "FATAL"
                                        ? "bg-red-500/15 text-red-600 dark:text-red-400"
                                        : evt.level === "WARN"
                                        ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                                        : evt.level === "METRIC"
                                        ? "bg-sky-500/15 text-sky-600 dark:text-sky-400"
                                        : "bg-muted text-muted-foreground"
                                    )}
                                  >
                                    {evt.level}
                                  </span>
                                </td>
                                <td className="py-2 text-muted-foreground text-[11px]">
                                  {evt.source ?? "—"}
                                </td>
                                <td className="py-2 text-foreground truncate max-w-[450px]">
                                  {formatPayload(evt)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}
