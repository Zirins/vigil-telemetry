"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Service, ServiceStatus } from "@/types";

/* ─── Status configuration ─── */
type StatusCfg = {
  dot: string;
  ring: string;
  badge: string;
  pulse: "none" | "slow" | "fast";
  cardBorder: string;
};

const STATUS: Record<ServiceStatus, StatusCfg> = {
  healthy: {
    dot: "bg-emerald-500",
    ring: "bg-emerald-500",
    badge: "text-emerald-800 border-emerald-200 bg-emerald-50 dark:text-emerald-400 dark:border-emerald-500/30 dark:bg-emerald-500/10",
    pulse: "none",
    cardBorder: "",
  },
  degraded: {
    dot: "bg-amber-500",
    ring: "bg-amber-400",
    badge: "text-amber-900 border-amber-300 bg-amber-50 dark:text-amber-400 dark:border-amber-500/30 dark:bg-amber-500/10",
    pulse: "slow",
    cardBorder: "border-l-amber-500",
  },
  down: {
    dot: "bg-red-500",
    ring: "bg-red-400",
    badge: "text-red-900 border-red-300 bg-red-50 dark:text-red-400 dark:border-red-500/30 dark:bg-red-500/10",
    pulse: "fast",
    cardBorder: "border-l-red-500",
  },
  unknown: {
    dot: "bg-slate-400",
    ring: "bg-slate-400",
    badge: "text-slate-600 border-slate-200 bg-slate-100 dark:text-zinc-400 dark:border-zinc-500/25 dark:bg-zinc-500/8",
    pulse: "none",
    cardBorder: "",
  },
};

/* ─── Severity ─── */
export const severityStyles: Record<string, string> = {
  P1: "text-red-900 border-red-200 bg-red-100 dark:text-red-300 dark:border-red-500/30 dark:bg-red-500/20 font-mono font-semibold",
  P2: "text-amber-900 border-amber-300 bg-amber-100 dark:text-amber-300 dark:border-amber-500/30 dark:bg-amber-500/20 font-mono font-semibold",
  P3: "text-blue-900 border-blue-200 bg-blue-100 dark:text-blue-300 dark:border-blue-500/30 dark:bg-blue-500/20 font-mono font-semibold",
};

export function StatusDot({ status }: { status: ServiceStatus }) {
  const cfg = STATUS[status] ?? STATUS.unknown;
  return (
    <span className="relative flex h-2 w-2 flex-shrink-0">
      {cfg.pulse === "slow" && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping",
            cfg.ring
          )}
          style={{ animationDuration: "1.8s" }}
        />
      )}
      {cfg.pulse === "fast" && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping-fast",
            cfg.ring
          )}
        />
      )}
      <span className={cn("relative inline-flex h-2 w-2 rounded-xs", cfg.dot)} />
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const key = (status ?? "unknown") as ServiceStatus;
  const cfg = STATUS[key] ?? STATUS.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono font-semibold uppercase tracking-wider border",
        cfg.badge
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-xs", cfg.dot)} />
      {status}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return null;
  const cls = severityStyles[severity] ?? severityStyles.P3;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] border font-mono font-semibold",
        cls
      )}
    >
      {severity}
    </span>
  );
}

/* ─── Main card ─── */
interface ServiceCardProps {
  service: Service;
  index?: number;
}

export function ServiceCard({ service, index = 0 }: ServiceCardProps) {
  const status = (service.status ?? "unknown") as ServiceStatus;
  const cfg = STATUS[status] ?? STATUS.unknown;
  const hasIssues = service.open_incident_count > 0;
  const hasAccent = status === "degraded" || status === "down";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: index * 0.03, ease: "easeOut" }}
    >
      <Link href={`/services/${service.id}`} className="block">
        <div
          className={cn(
            "group relative overflow-hidden rounded border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.04)]",
            "transition-all duration-150 hover:border-slate-400 dark:hover:border-slate-600",
            hasAccent && "border-l-2",
            cfg.cardBorder
          )}
        >
          <div className="p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <StatusDot status={status} />
                  <h3 className="truncate font-semibold text-foreground text-sm font-mono leading-snug">
                    {service.name}
                  </h3>
                </div>
                <p className="pl-4 text-xs font-mono text-muted-foreground uppercase">
                  {service.environment}
                </p>
              </div>
              <StatusBadge status={status} />
            </div>

            <div className="flex items-center justify-between border-t border-border pt-2.5 text-xs font-mono">
              {hasIssues ? (
                <span className="flex items-center gap-1.5 font-semibold text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {service.open_incident_count} open incident{service.open_incident_count !== 1 ? "s" : ""}
                </span>
              ) : (
                <span className="text-muted-foreground">0 open incidents</span>
              )}
              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </div>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
