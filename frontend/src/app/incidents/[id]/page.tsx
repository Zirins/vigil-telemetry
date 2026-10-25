"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, FileText } from "lucide-react";
import { AIReport } from "@/components/AIReport";
import { AppNav } from "@/components/AppNav";
import { SeverityBadge } from "@/components/ServiceCard";
import { TimelineReplay } from "@/components/TimelineReplay";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import * as api from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_DOT: Record<string, string> = {
  open: "bg-red-500",
  investigating: "bg-amber-500",
  resolved: "bg-emerald-500",
};

const STATUS_TEXT: Record<string, string> = {
  open: "text-red-400",
  investigating: "text-amber-400",
  resolved: "text-emerald-400",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "Unknown start time";
  return new Date(iso).toLocaleString();
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

export default function IncidentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const incidentId = Number(params.id);
  const [postmortem, setPostmortem] = useState("");

  const { data: incident, isLoading, error } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => api.getIncident(incidentId),
    enabled: Number.isFinite(incidentId),
    refetchInterval: (query) =>
      query.state.data?.ai_analysis_status === "processing" ? 3_000 : false,
  });

  const { data: service } = useQuery({
    queryKey: ["service", incident?.service_id],
    queryFn: () => api.getService(incident!.service_id),
    enabled: Boolean(incident?.service_id),
  });

  const correlationEnd = useMemo(() => {
    if (!incident?.started_at) return null;
    return new Date(
      new Date(incident.started_at).getTime() + 45 * 60 * 1000
    ).toISOString();
  }, [incident?.started_at]);

  const timelineQuery = useQuery({
    queryKey: ["incident-events", incidentId, incident?.started_at, correlationEnd],
    queryFn: () =>
      api.getEvents(incident!.service_id, {
        since: incident!.started_at ?? undefined,
        until: correlationEnd ?? undefined,
        limit: 200,
      }),
    enabled: Boolean(incident?.service_id && incident?.started_at && correlationEnd),
  });

  const timelineEvents = useMemo(() => {
    const raw = timelineQuery.data ?? [];
    if (!incident?.started_at) return raw;

    const startedMs = new Date(incident.started_at).getTime();
    const endMs = correlationEnd
      ? new Date(correlationEnd).getTime()
      : startedMs + 45 * 60 * 1000;

    return raw.filter((event) => {
      if (!event.timestamp) return true;
      const ts = new Date(event.timestamp).getTime();
      return ts >= startedMs && ts <= endMs;
    });
  }, [timelineQuery.data, incident?.started_at, correlationEnd]);

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveIncident(incidentId, postmortem || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["services"] });
      router.push("/incidents");
    },
  });

  const isResolved = incident?.status === "resolved";

  return (
    <div className="min-h-screen bg-background">
      <AppNav />

      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
        {/* Back */}
        <Link
          href="/incidents"
          className="mb-6 inline-flex items-center gap-1.5 font-mono text-xs text-muted-foreground/60 transition-colors hover:text-muted-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          incidents
        </Link>

        {/* Loading */}
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-80" />
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-72 w-full rounded-lg" />
            <Skeleton className="h-96 w-full rounded-lg" />
          </div>
        ) : null}

        {/* Error */}
        {error ? (
          <div className="rounded-md border border-destructive/25 bg-destructive/8 px-4 py-3">
            <p className="font-mono text-xs text-red-400">
              {error instanceof Error ? error.message : "failed to load incident"}
            </p>
          </div>
        ) : null}

        {/* Content */}
        {incident ? (
          <div className="space-y-5">
            {/* Header */}
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2.5">
                <h1 className="text-xl font-semibold text-foreground">
                  {formatIncidentTitle(incident.title)}
                </h1>
                <SeverityBadge severity={incident.severity} />
                <span className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      STATUS_DOT[incident.status] ?? "bg-zinc-500"
                    )}
                  />
                  <span
                    className={cn(
                      "text-xs font-medium capitalize",
                      STATUS_TEXT[incident.status] ?? "text-muted-foreground"
                    )}
                  >
                    {incident.status}
                  </span>
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                {service ? (
                  <Link
                    href={`/services/${service.id}`}
                    className="font-medium text-primary/80 hover:text-primary"
                  >
                    {service.name}
                  </Link>
                ) : (
                  <span className="font-mono">service #{incident.service_id}</span>
                )}
                {service ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="inline-flex items-center gap-1.5 capitalize">
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          service.status === "healthy"
                            ? "bg-emerald-500"
                            : service.status === "degraded"
                              ? "bg-amber-500"
                              : service.status === "down"
                                ? "bg-red-500"
                                : "bg-zinc-500"
                        )}
                      />
                      {service.status}
                    </span>
                  </>
                ) : null}
                {incident.detection_type ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="font-mono">{formatDetectionType(incident.detection_type)}</span>
                  </>
                ) : null}
                <span aria-hidden="true">·</span>
                <span title={formatDateTime(incident.started_at)}>
                  Started {timeAgo(incident.started_at)}
                </span>
              </div>
            </div>

            {/* AI Analysis */}
            <AIReport report={incident} />

            {/* Timeline */}
            <TimelineReplay
              events={timelineEvents}
              isLoading={timelineQuery.isLoading}
              startedAt={incident.started_at}
              endAt={correlationEnd}
              serviceHref={`/services/${incident.service_id}`}
            />

            {/* Resolve / Postmortem */}
            {!isResolved ? (
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="mb-3 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-muted-foreground/50" />
                  <h2 className="text-sm font-semibold text-foreground">
                    Resolve Incident
                  </h2>
                </div>
                <p className="mb-4 text-sm text-muted-foreground/60">
                  Optionally add a postmortem note before marking resolved.
                </p>
                <Textarea
                  value={postmortem}
                  onChange={(e) => setPostmortem(e.target.value)}
                  placeholder="What happened? How was it fixed?"
                  className="mb-4 min-h-[80px] resize-none font-mono text-xs"
                />
                <Button
                  onClick={() => resolveMutation.mutate()}
                  disabled={resolveMutation.isPending}
                  size="sm"
                  className="gap-2"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {resolveMutation.isPending ? "Resolving…" : "Mark Resolved"}
                </Button>
                {resolveMutation.error ? (
                  <p className="mt-2 font-mono text-xs text-red-400">
                    {resolveMutation.error instanceof Error
                      ? resolveMutation.error.message
                      : "failed to resolve"}
                  </p>
                ) : null}
              </div>
            ) : incident.postmortem ? (
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="mb-3 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground/50" />
                  <h2 className="text-sm font-semibold text-foreground">Postmortem</h2>
                </div>
                <p className="font-mono text-xs leading-relaxed text-muted-foreground/70">
                  {incident.postmortem}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </main>
    </div>
  );
}
