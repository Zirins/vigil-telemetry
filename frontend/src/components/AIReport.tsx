"use client";

import { motion } from "framer-motion";
import {
  ChevronRight,
  CircleAlert,
  CircleSlash2,
  Cpu,
  LoaderCircle,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AIAnalysisStatus, AIReport as AIReportData } from "@/types";

interface AIReportProps {
  report: AIReportData;
}

function SectionLabel({
  icon: Icon,
  label,
}: {
  icon: React.ElementType;
  label: string;
}) {
  return (
    <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
      <Icon className="h-3.5 w-3.5" />
      <span>{label}</span>
    </div>
  );
}

const EMPTY_STATE: Record<
  Exclude<AIAnalysisStatus, "completed" | "processing">,
  { title: string; description: string }
> = {
  failed: {
    title: "Analysis job failed",
    description: "The triage pipeline could not complete inference. Check backend logs.",
  },
  unavailable: {
    title: "No triage generated",
    description: "Automated analysis was not triggered for this incident.",
  },
  not_generated: {
    title: "Triage pending",
    description: "Run scripts/analyze_one_incident.py to backfill telemetry analysis.",
  },
};

function AnalysisState({ status }: { status: Exclude<AIAnalysisStatus, "completed"> }) {
  if (status === "processing") {
    return (
      <div className="flex items-start gap-3 p-4 font-mono text-xs" aria-live="polite">
        <LoaderCircle className="mt-0.5 h-4 w-4 animate-spin text-primary" />
        <div>
          <p className="font-bold text-foreground">Analysis in progress</p>
          <p className="mt-0.5 text-muted-foreground">
            Evaluating recent error patterns and metric baseline deltas
          </p>
        </div>
      </div>
    );
  }

  const copy = EMPTY_STATE[status];
  const Icon = status === "failed" ? CircleAlert : CircleSlash2;
  return (
    <div className="flex items-start gap-3 p-4 font-mono text-xs">
      <Icon
        className={cn(
          "mt-0.5 h-4 w-4 flex-shrink-0",
          status === "failed" ? "text-destructive" : "text-muted-foreground"
        )}
      />
      <div>
        <p className="font-bold text-foreground">{copy.title}</p>
        <p className="mt-0.5 text-muted-foreground">{copy.description}</p>
      </div>
    </div>
  );
}

export function AIReport({ report }: AIReportProps) {
  const status: AIAnalysisStatus =
    report.ai_analysis_status ??
    (report.ai_analyzed_at ? "completed" : "unavailable");

  return (
    <div className="overflow-hidden rounded border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-muted/40 px-4 py-2.5 font-mono text-xs">
        <div className="flex items-center gap-2">
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
            TRIAGE
          </span>
          <span className="font-bold text-foreground">Automated Incident Postmortem</span>
        </div>

        {status === "completed" && report.ai_analyzed_at ? (
          <span className="text-[11px] text-muted-foreground">
            {new Date(report.ai_analyzed_at).toLocaleString([], {
              dateStyle: "short",
              timeStyle: "medium",
            })}
          </span>
        ) : status === "processing" ? (
          <span className="text-xs text-primary font-bold animate-pulse">Running…</span>
        ) : null}
      </div>

      {status !== "completed" ? (
        <AnalysisState status={status} />
      ) : (
        <motion.div
          className="divide-y divide-border text-xs"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.15 }}
        >
          {report.ai_summary ? (
            <div className="p-4">
              <SectionLabel icon={ChevronRight} label="Incident Summary" />
              <p className="leading-relaxed text-foreground font-mono bg-muted/30 p-2.5 rounded border border-border">
                {report.ai_summary}
              </p>
            </div>
          ) : null}

          {report.ai_root_cause ? (
            <div className="p-4">
              <SectionLabel icon={Cpu} label="Identified Root Cause" />
              <p className="leading-relaxed text-foreground font-mono bg-muted/30 p-2.5 rounded border border-border">
                {report.ai_root_cause}
              </p>
            </div>
          ) : null}

          {report.ai_affected_components && report.ai_affected_components.length > 0 ? (
            <div className="p-4">
              <SectionLabel icon={ShieldCheck} label="Affected Components" />
              <div className="flex flex-wrap gap-1.5 font-mono">
                {report.ai_affected_components.map((component) => (
                  <span
                    key={component}
                    className="rounded border border-border bg-muted/60 px-2 py-0.5 text-[11px] text-foreground font-medium"
                  >
                    {component}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {report.ai_remediation_steps && report.ai_remediation_steps.length > 0 ? (
            <div className="p-4">
              <SectionLabel icon={Wrench} label="Actionable Remediation" />
              <ol className="space-y-1.5 font-mono text-[12px]">
                {report.ai_remediation_steps.map((step, index) => (
                  <li key={`${index}-${step.slice(0, 20)}`} className="flex items-start gap-2 bg-muted/30 p-2 rounded border border-border">
                    <span className="font-bold text-primary flex-shrink-0">
                      [{index + 1}]
                    </span>
                    <span className="leading-relaxed text-foreground">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          {report.ai_confidence != null ? (
            <div className="flex items-center justify-between px-4 py-2.5 font-mono text-xs bg-muted/20">
              <span className="text-muted-foreground uppercase text-[11px]">
                Heuristic Assessment Confidence
              </span>
              <span className="font-bold text-foreground">
                {(Number(report.ai_confidence) * 100).toFixed(0)}% (scalar: {Number(report.ai_confidence).toFixed(2)})
              </span>
            </div>
          ) : null}
        </motion.div>
      )}
    </div>
  );
}
