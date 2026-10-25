"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "lucide-react";
import { wsClient } from "@/lib/ws";
import type { Event } from "@/types";
import { cn } from "@/lib/utils";

/* ─── Per-level terminal styling (dual-theme adapted) ─── */
type LevelStyle = {
  border: string;   // left border accent
  level: string;    // level label text color
  message: string;  // message text color
  rowBg: string;    // optional row tint
  label: string;    // fixed-width display label
};

const LEVEL: Record<string, LevelStyle> = {
  INFO: {
    border: "border-l-zinc-400 dark:border-l-zinc-700",
    level: "text-zinc-600 dark:text-zinc-400 font-semibold",
    message: "text-zinc-800 dark:text-zinc-300",
    rowBg: "",
    label: "INFO ",
  },
  WARN: {
    border: "border-l-amber-500",
    level: "text-amber-700 dark:text-amber-400 font-semibold",
    message: "text-amber-900 dark:text-amber-200",
    rowBg: "bg-amber-500/[0.08] dark:bg-amber-500/[0.06]",
    label: "WARN ",
  },
  ERROR: {
    border: "border-l-red-500",
    level: "text-red-700 dark:text-red-400 font-semibold",
    message: "text-red-900 dark:text-red-200",
    rowBg: "bg-red-500/[0.08] dark:bg-red-500/[0.08]",
    label: "ERROR",
  },
  FATAL: {
    border: "border-l-red-600 dark:border-l-red-400",
    level: "text-red-800 dark:text-red-300 font-bold",
    message: "text-red-950 dark:text-red-100",
    rowBg: "bg-red-500/[0.12]",
    label: "FATAL",
  },
  METRIC: {
    border: "border-l-sky-500/80",
    level: "text-sky-700 dark:text-sky-400 font-semibold",
    message: "text-sky-900 dark:text-sky-200",
    rowBg: "",
    label: "METR ",
  },
};

function formatLine(event: Event): string {
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
  return event.message ?? "(empty)";
}

function ts(value: string | null): string {
  if (!value) return "──────";
  const d = new Date(value);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

interface EventStreamProps {
  serviceId: number;
  initialEvents?: Event[];
}

export function EventStream({ serviceId, initialEvents = [] }: EventStreamProps) {
  const [events, setEvents] = useState<Event[]>(initialEvents);
  const [wsState, setWsState] = useState<"idle" | "live">("idle");
  const [newId, setNewId] = useState<number | null>(null);
  const seenIds = useRef(new Set(initialEvents.map((e) => e.id)));
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    setEvents(initialEvents);
    seenIds.current = new Set(initialEvents.map((e) => e.id));
  }, [initialEvents, serviceId]);

  useEffect(() => {
    wsClient.connect(serviceId);

    const unsub = wsClient.subscribe((msg) => {
      if (msg.type !== "event") return;
      const e = msg.data;
      if (seenIds.current.has(e.id)) return;
      seenIds.current.add(e.id);
      setWsState("live");
      setNewId(e.id);
      setEvents((prev) => [e, ...prev].slice(0, 200));
      setTimeout(() => setNewId(null), 1200);
    });

    return () => unsub();
  }, [serviceId]);

  return (
    <div className="flex h-[480px] flex-col rounded-lg border border-border bg-zinc-100/70 dark:bg-zinc-950 dark:border-zinc-800 overflow-hidden shadow-sm">
      {/* ── Terminal header bar ── */}
      <div className="flex items-center justify-between border-b border-border bg-zinc-200/60 dark:bg-zinc-900/80 dark:border-zinc-800/80 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-zinc-500 dark:text-zinc-400" />
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-zinc-800 dark:text-zinc-200">
            Live Event Stream
          </span>
          <span className="text-zinc-400 dark:text-zinc-600 font-mono text-xs">•</span>
          <span className="font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
            svc:{serviceId}
          </span>
        </div>

        {/* WS indicator */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 hidden sm:inline">
            auto-scroll: on
          </span>
          <div className="flex items-center gap-1.5 pl-2 border-l border-zinc-300 dark:border-zinc-800">
            <span className="relative flex h-2 w-2">
              {wsState === "live" && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              )}
              <span
                className={cn(
                  "relative inline-flex h-2 w-2 rounded-full transition-colors",
                  wsState === "live" ? "bg-emerald-500" : "bg-zinc-400 dark:bg-zinc-600"
                )}
              />
            </span>
            <span
              className={cn(
                "font-mono text-[11px] transition-colors",
                wsState === "live" ? "text-emerald-700 dark:text-emerald-400 font-semibold" : "text-zinc-500"
              )}
            >
              {wsState === "live" ? "connected" : "waiting"}
            </span>
          </div>
        </div>
      </div>

      {/* ── Log body ── */}
      <ul
        ref={listRef}
        className="scroll-dark flex-1 overflow-y-auto font-mono text-[11.5px] leading-[1.55]"
      >
        {events.length === 0 ? (
          <li className="flex h-full items-center justify-center">
            <span className="text-muted-foreground/50 font-mono text-xs">
              no events — waiting for stream
            </span>
          </li>
        ) : (
          <>
            {events.map((event) => {
              const style = LEVEL[event.level] ?? LEVEL.INFO;
              const isNew = event.id === newId;
              return (
                <li
                  key={event.id}
                  className={cn(
                    "flex gap-0 border-l-2 px-0 transition-colors",
                    style.border,
                    style.rowBg,
                    isNew && "bg-primary/[0.06]"
                  )}
                >
                  <div className="flex min-w-0 w-full gap-2 px-3 py-[3px]">
                    {/* Timestamp */}
                    <span className="w-[52px] shrink-0 select-none text-zinc-400 dark:text-zinc-600">
                      {ts(event.timestamp)}
                    </span>
                    {/* Level */}
                    <span className={cn("w-[38px] shrink-0", style.level)}>
                      {style.label}
                    </span>
                    {/* Source */}
                    {event.source ? (
                      <span className="shrink-0 text-zinc-400 dark:text-zinc-600 hidden sm:inline">
                        [{event.source}]
                      </span>
                    ) : null}
                    {/* Message */}
                    <span className={cn("min-w-0 truncate", style.message)}>
                      {formatLine(event)}
                    </span>
                  </div>
                </li>
              );
            })}
            {/* Blinking cursor */}
            <li className="flex items-center gap-2 border-l-2 border-l-transparent px-3 py-[3px]">
              <span className="w-[52px] select-none text-zinc-300 dark:text-zinc-700">
                {ts(events[0]?.timestamp ?? null)}
              </span>
              <span className="text-zinc-400 dark:text-zinc-500">
                <span className="cursor-blink inline-block w-[7px] h-[13px] bg-zinc-400/80 dark:bg-zinc-500/60 align-[-2px]" />
              </span>
            </li>
          </>
        )}
      </ul>
    </div>
  );
}
