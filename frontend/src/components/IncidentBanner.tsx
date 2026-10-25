"use client";

import Link from "next/link";
import { AlertTriangle, ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { SeverityBadge } from "@/components/ServiceCard";
import type { Incident } from "@/types";
import { cn } from "@/lib/utils";

interface IncidentBannerProps {
  incidents: Incident[];
}

const severityBorderColor: Record<string, string> = {
  P1: "border-l-red-500",
  P2: "border-l-amber-500",
  P3: "border-l-blue-500",
};

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

export function IncidentBanner({ incidents }: IncidentBannerProps) {
  const active = incidents.filter((i) => i.status !== "resolved");

  return (
    <AnimatePresence>
      {active.length > 0 ? (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="space-y-1.5"
        >
          {active.map((incident) => {
            const borderCls = incident.severity
              ? (severityBorderColor[incident.severity] ?? "border-l-red-500")
              : "border-l-red-500";

            return (
              <Link key={incident.id} href={`/incidents/${incident.id}`}>
                <div
                  className={cn(
                    "group flex items-center justify-between gap-3",
                    "rounded-md border border-border border-l-2 bg-card",
                    "px-4 py-2.5 transition-colors hover:bg-muted/40",
                    borderCls
                  )}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    {/* Pulsing alert icon */}
                    <span className="relative flex h-4 w-4 flex-shrink-0">
                      <span className="absolute h-4 w-4 animate-ping rounded-full bg-red-500/30" />
                      <AlertTriangle className="relative h-4 w-4 text-red-400" />
                    </span>

                    <span className="truncate text-sm font-medium text-foreground">
                      {formatIncidentTitle(incident.title)}
                    </span>
                    <SeverityBadge severity={incident.severity} />

                    {incident.detection_type ? (
                      <span className="hidden rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground sm:inline">
                        {formatDetectionType(incident.detection_type)}
                      </span>
                    ) : null}
                  </div>

                  <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground/60" />
                </div>
              </Link>
            );
          })}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
