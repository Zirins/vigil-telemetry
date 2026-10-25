"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Service, ServiceStatus } from "@/types";

function formatMetric(value: number | null, unit: string): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (unit === "pct") return `${(value * 100).toFixed(2)} %`;
  if (unit === "ms") return `${value.toFixed(0)} ms`;
  return value.toFixed(2);
}

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

interface ServiceRowProps {
  service: Service;
}

export function ServiceRow({ service }: ServiceRowProps) {
  const status = (service.status ?? "unknown") as ServiceStatus;
  const errorRate =
    service.latest_error_rate !== null ? Number(service.latest_error_rate) : null;
  const latency =
    service.latest_latency_p99 !== null ? Number(service.latest_latency_p99) : null;

  // Threshold-driven metric colors: quiet neutrals unless breaching SLAs
  const latencyClass =
    latency === null
      ? "text-muted-foreground"
      : latency >= 500
      ? "text-red-700 dark:text-red-400 font-bold"
      : latency >= 200
      ? "text-amber-700 dark:text-amber-400 font-medium"
      : "text-foreground font-normal";

  const errorRateClass =
    errorRate === null
      ? "text-muted-foreground"
      : errorRate >= 0.1 // > 10%
      ? "text-red-700 dark:text-red-400 font-bold"
      : errorRate >= 0.01 // >= 1%
      ? "text-amber-700 dark:text-amber-400 font-medium"
      : "text-muted-foreground font-normal";

  const rowBorderClass =
    status === "down"
      ? "border-l-2 border-l-red-500 bg-red-500/[0.03] hover:bg-red-500/[0.06] dark:bg-red-500/[0.04]"
      : status === "degraded"
      ? "border-l-2 border-l-amber-500 bg-amber-500/[0.03] hover:bg-amber-500/[0.06] dark:bg-amber-500/[0.04]"
      : "border-l-2 border-l-transparent hover:bg-muted/30";

  return (
    <Link
      href={`/services/${service.id}`}
      className="block focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <div
        className={cn(
          "group grid grid-cols-[minmax(180px,1.5fr)_110px_100px_100px_110px_130px] items-center gap-3 px-3 py-2.5 transition-colors border-b border-border/60 font-mono text-xs",
          rowBorderClass
        )}
      >
        {/* Service Name & Env */}
        <div className="min-w-0 pr-2">
          <span className="truncate font-bold text-foreground text-[13px] group-hover:text-primary transition-colors block">
            {service.name}
          </span>
          <p className="text-[11px] font-mono text-muted-foreground uppercase">
            {service.environment}
          </p>
        </div>

        {/* Status: clean text + dot indicator, no pill bloat */}
        <div className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider font-semibold">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full flex-shrink-0",
              status === "healthy"
                ? "bg-emerald-500"
                : status === "degraded"
                ? "bg-amber-500"
                : status === "down"
                ? "bg-red-500"
                : "bg-zinc-500"
            )}
          />
          <span
            className={cn(
              status === "healthy"
                ? "text-emerald-700 dark:text-emerald-400"
                : status === "degraded"
                ? "text-amber-700 dark:text-amber-400"
                : status === "down"
                ? "text-red-700 dark:text-red-400"
                : "text-muted-foreground"
            )}
          >
            {status}
          </span>
        </div>

        {/* P99 Latency */}
        <div className="text-right">
          <span className={cn("tabular-nums", latencyClass)}>
            {formatMetric(latency, "ms")}
          </span>
        </div>

        {/* Error Rate */}
        <div className="text-right">
          <span className={cn("tabular-nums", errorRateClass)}>
            {formatMetric(errorRate, "pct")}
          </span>
        </div>

        {/* Open Incidents: only P1 gets filled badge */}
        <div className="text-right">
          {service.open_incident_count > 0 ? (
            service.highest_open_severity === "P1" ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-red-500/30 bg-red-500/15 text-red-700 dark:text-red-300 font-bold text-[11px] tabular-nums">
                <span className="h-1 w-1 rounded-full bg-red-500" />
                {service.open_incident_count} (P1)
              </span>
            ) : service.highest_open_severity === "P2" ? (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400 font-medium text-[11px] tabular-nums">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                {service.open_incident_count} (P2)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-muted-foreground text-[11px] tabular-nums">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                {service.open_incident_count} (P3)
              </span>
            )
          ) : (
            <span className="text-muted-foreground/40 tabular-nums">0</span>
          )}
        </div>

        {/* Last Signal & Action */}
        <div className="flex items-center justify-end gap-3 text-right pl-2">
          <span className="text-muted-foreground tabular-nums text-[11px]">
            {timeAgo(service.last_seen_at)}
          </span>
          <span className="text-primary font-sans text-xs group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
            Inspect <ArrowRight className="h-3 w-3" />
          </span>
        </div>
      </div>
    </Link>
  );
}
