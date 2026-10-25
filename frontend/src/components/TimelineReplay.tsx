"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Event } from "@/types";

type LevelCfg = {
  dot: string;
  level: string;
  message: string;
};

const LEVEL: Record<string, LevelCfg> = {
  INFO: {
    dot: "bg-zinc-500",
    level: "text-zinc-500",
    message: "text-foreground/75",
  },
  WARN: {
    dot: "bg-amber-500",
    level: "text-amber-400",
    message: "text-amber-100/80",
  },
  ERROR: {
    dot: "bg-red-500",
    level: "text-red-400",
    message: "text-red-100/80",
  },
  FATAL: {
    dot: "bg-red-400",
    level: "text-red-300 font-semibold",
    message: "text-red-50",
  },
  METRIC: {
    dot: "bg-sky-500",
    level: "text-sky-400/70",
    message: "text-sky-200/70",
  },
};

function fmtMsg(event: Event): string {
  if (event.level === "METRIC" && event.payload) {
    return `${event.payload.metric ?? "metric"}=${event.payload.value ?? "?"}`;
  }
  return event.message ?? "(no message)";
}

function fmtTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function timestampKey(value: string | null): string {
  if (!value) return "na";
  return new Date(value).toISOString().slice(0, 19);
}

function metricName(event: Event): string | null {
  if (event.level !== "METRIC" || !event.payload?.metric) return null;
  return String(event.payload.metric);
}

/** One value per metric_name per group — last event wins. */
function dedupeMetricEvents(events: Event[]): Event[] {
  const nonMetrics: Event[] = [];
  const latestByMetric = new Map<string, Event>();

  for (const event of events) {
    const name = metricName(event);
    if (name) {
      latestByMetric.set(name, event);
    } else {
      nonMetrics.push(event);
    }
  }

  const metrics = [...latestByMetric.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, event]) => event);

  return [...nonMetrics, ...metrics];
}

interface TimelineGroup {
  key: string;
  timestamp: string | null;
  events: Event[];
}

function groupTimelineEvents(events: Event[]): TimelineGroup[] {
  const chronological = [...events].sort(
    (a, b) => new Date(a.timestamp ?? 0).getTime() - new Date(b.timestamp ?? 0).getTime()
  );

  const groups: TimelineGroup[] = [];

  for (const event of chronological) {
    const last = groups[groups.length - 1];
    const canMerge =
      last &&
      timestampKey(last.timestamp) === timestampKey(event.timestamp) &&
      event.level === "METRIC" &&
      last.events.every((item) => item.level === "METRIC");

    if (canMerge) {
      last.events = dedupeMetricEvents([...last.events, event]);
      continue;
    }

    groups.push({
      key: `${event.id}-${timestampKey(event.timestamp)}`,
      timestamp: event.timestamp,
      events: [event],
    });
  }

  return groups;
}

function groupLevel(events: Event[]): string {
  if (events.some((event) => event.level === "FATAL")) return "FATAL";
  if (events.some((event) => event.level === "ERROR")) return "ERROR";
  if (events.some((event) => event.level === "WARN")) return "WARN";
  if (events.every((event) => event.level === "METRIC")) return "METRIC";
  return events[0]?.level ?? "INFO";
}

function groupMessage(events: Event[]): string {
  const deduped = dedupeMetricEvents(events);
  if (deduped.length === 1) return fmtMsg(deduped[0]);
  if (deduped.every((event) => event.level === "METRIC")) {
    return deduped.map((event) => fmtMsg(event)).join(" · ");
  }
  return deduped.map((event) => `${event.level} ${fmtMsg(event)}`).join(" | ");
}

interface TimelineReplayProps {
  events: Event[];
  isLoading?: boolean;
  startedAt?: string | null;
  endAt?: string | null;
  serviceHref?: string;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString();
}

function formatWindow(startedAt?: string | null, endAt?: string | null): string {
  if (!startedAt || !endAt) return "Unknown";
  const minutes = Math.max(
    0,
    Math.round(
      (new Date(endAt).getTime() - new Date(startedAt).getTime()) / 60000
    )
  );
  return `${minutes} minutes after incident start`;
}

export function TimelineReplay({
  events,
  isLoading = false,
  startedAt,
  endAt,
  serviceHref,
}: TimelineReplayProps) {
  const groups = groupTimelineEvents(events);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border/60 bg-muted/30 px-4 py-2.5">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Incident Timeline</h2>
          <p className="font-mono text-[11px] text-muted-foreground/50">
            chronological · from incident start
          </p>
        </div>
      </div>

      <ul
        className="max-h-[480px] overflow-y-auto scroll-dark font-mono"
        style={{ fontSize: "11.5px", lineHeight: "1.55" }}
      >
        {isLoading ? (
          <li className="py-8 text-center text-xs text-muted-foreground">
            Loading correlated events…
          </li>
        ) : groups.length === 0 ? (
          <li className="px-4 py-8 text-center font-sans">
            <p className="text-sm text-muted-foreground">
              No correlated events were found in the incident window.
            </p>
            <dl className="mt-3 grid gap-2 text-xs text-muted-foreground/70 sm:flex sm:flex-wrap sm:justify-center sm:gap-x-4 sm:gap-y-1">
              <div className="grid gap-0.5 sm:flex sm:gap-1.5">
                <dt>Incident start</dt>
                <dd className="font-mono">{formatDateTime(startedAt)}</dd>
              </div>
              <div className="grid gap-0.5 sm:flex sm:gap-1.5">
                <dt>Correlation window</dt>
                <dd className="font-mono">{formatWindow(startedAt, endAt)}</dd>
              </div>
            </dl>
            {serviceHref ? (
              <Link
                href={serviceHref}
                className="mt-3 inline-flex text-xs font-medium text-primary/80 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                View related service event stream
              </Link>
            ) : null}
          </li>
        ) : (
          groups.map((group) => {
            const level = groupLevel(group.events);
            const cfg = LEVEL[level] ?? LEVEL.INFO;
            const source = group.events.find((event) => event.source)?.source;

            return (
              <li
                key={group.key}
                className={cn(
                  "flex gap-2 border-l-2 border-border/40 px-3 py-[3px]",
                  level === "ERROR" || level === "FATAL"
                    ? "border-l-red-500/60 bg-red-500/[0.04]"
                    : level === "WARN"
                      ? "border-l-amber-500/60 bg-amber-500/[0.03]"
                      : level === "METRIC"
                        ? "border-l-sky-500/50"
                        : "border-l-transparent"
                )}
              >
                <span className="w-[52px] shrink-0 tabular-nums text-zinc-600">
                  {fmtTime(group.timestamp)}
                </span>
                <span className={cn("w-[38px] shrink-0", cfg.level)}>
                  {(level === "METRIC" ? "METR" : level).padEnd(4, " ")}
                </span>
                {source ? (
                  <span className="hidden shrink-0 text-zinc-600 sm:inline">[{source}]</span>
                ) : null}
                <span className={cn("min-w-0 truncate", cfg.message)}>
                  {groupMessage(group.events)}
                </span>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
