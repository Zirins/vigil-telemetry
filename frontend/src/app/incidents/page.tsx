"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { AppNav } from "@/components/AppNav";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import * as api from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_FILTERS = ["all", "open", "investigating", "resolved"] as const;

const STATUS_DOT: Record<string, string> = {
  open: "bg-red-500",
  investigating: "bg-amber-500",
  resolved: "bg-emerald-500",
};

const SEVERITY_MARK: Record<string, string> = {
  P1: "bg-red-500",
  P2: "bg-amber-500",
  P3: "bg-sky-500",
};

const SEVERITY_TEXT: Record<string, string> = {
  P1: "text-red-400",
  P2: "text-amber-400",
  P3: "text-sky-400",
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

export default function IncidentsPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data, isLoading, error } = useQuery({
    queryKey: ["incidents", statusFilter],
    queryFn: () =>
      api.getIncidents({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
    refetchInterval: 10_000,
  });

  return (
    <div className="min-h-screen bg-background">
      <AppNav />

      <main className="mx-auto max-w-[1380px] px-4 py-4 sm:px-6">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Incidents
            </h1>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Anomalies · active investigations · resolved
            </p>
          </div>
          <div className="w-44">
            <Select
              value={statusFilter}
              onValueChange={(value) => setStatusFilter(value ?? "all")}
            >
              <SelectTrigger aria-label="Filter incidents by status" className="h-8 text-xs">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_FILTERS.map((status) => (
                  <SelectItem key={status} value={status} className="text-xs">
                    {status === "all" ? "All statuses" : status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-px border-y border-border">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-[68px] rounded-none" />
            ))}
          </div>
        ) : null}

        {error ? (
          <div className="border-y border-destructive/25 bg-destructive/8 px-4 py-3">
            <p className="font-mono text-xs text-red-400">
              {error instanceof Error ? error.message : "failed to load incidents"}
            </p>
          </div>
        ) : null}

        {data && data.length === 0 ? (
          <div className="flex flex-col items-center justify-center border-y border-dashed border-border bg-card/30 py-20">
            <ShieldAlert className="mb-3 h-8 w-8 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">No incidents found</p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              {statusFilter !== "all"
                ? `No ${statusFilter} incidents.`
                : "Everything is quiet."}
            </p>
          </div>
        ) : null}

        {data && data.length > 0 ? (
          <div className="divide-y divide-border/70 border-y border-border bg-card/20">
            {data.map((incident) => {
              const severityMark = incident.severity
                ? SEVERITY_MARK[incident.severity] ?? "bg-muted-foreground"
                : "bg-muted-foreground";
              const severityText = incident.severity
                ? SEVERITY_TEXT[incident.severity] ?? "text-muted-foreground"
                : "text-muted-foreground";
              const statusDot = STATUS_DOT[incident.status] ?? "bg-zinc-500";
              const timestamp = timeAgo(incident.started_at);

              return (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  <div className="grid grid-cols-[3px_minmax(0,1fr)] items-center gap-3 px-1 py-2.5 transition-colors hover:bg-muted/20 sm:grid-cols-[3px_minmax(0,1fr)_auto] sm:px-3">
                    <span
                      className={cn("h-8 w-[3px]", severityMark)}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn(
                            "font-mono text-[11px] font-semibold",
                            severityText
                          )}
                        >
                          {incident.severity ?? "—"}
                        </span>
                        <span className="truncate text-sm font-semibold text-foreground">
                          {formatIncidentTitle(incident.title)}
                        </span>
                      </div>
                      <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="truncate">
                          {incident.service_name ?? `service ${incident.service_id}`}
                        </span>
                        {incident.detection_type ? (
                          <>
                            <span aria-hidden="true">·</span>
                            <span className="font-mono text-[11px]">
                              {formatDetectionType(incident.detection_type)}
                            </span>
                          </>
                        ) : null}
                        <span aria-hidden="true">·</span>
                        <span className="inline-flex items-center gap-1.5 capitalize">
                          <span className={cn("h-1.5 w-1.5", statusDot)} />
                          {incident.status}
                        </span>
                        <span className="ml-auto font-mono text-[11px] sm:hidden">
                          {timestamp}
                        </span>
                      </div>
                    </div>
                    <span className="hidden font-mono text-[11px] text-muted-foreground sm:block">
                      {timestamp}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : null}
      </main>
    </div>
  );
}
