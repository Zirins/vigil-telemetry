"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity } from "lucide-react";
import { wsClient } from "@/lib/ws";
import type { Event, MetricDataPoint } from "@/types";

const MAX_POINTS = 60;

/* ── SRE Telemetry colors (Zero-slop Royal Blue + Crimson) ── */
const CPU_COLOR = "#2563EB";    // blue-600
const ERR_COLOR = "#DC2626";    // red-600

/* ── Data helpers (unchanged logic) ── */
function buildPointsFromEvents(events: Event[]): MetricDataPoint[] {
  const sorted = [...events]
    .filter((e) => e.level === "METRIC" && e.timestamp)
    .sort((a, b) => new Date(a.timestamp ?? 0).getTime() - new Date(b.timestamp ?? 0).getTime());

  const buckets = new Map<string, MetricDataPoint>();
  for (const event of sorted) {
    const t = event.timestamp as string;
    const existing = buckets.get(t) ?? { timestamp: t, cpu_pct: null, error_rate: null };
    const metric = event.payload?.metric as string | undefined;
    const value = event.payload?.value;
    if (metric === "cpu_pct" && value !== undefined) existing.cpu_pct = Number(value);
    if (metric === "error_rate" && value !== undefined) existing.error_rate = Number(value);
    buckets.set(t, existing);
  }
  return Array.from(buckets.values()).slice(-MAX_POINTS);
}

function upsertPoint(points: MetricDataPoint[], event: Event): MetricDataPoint[] {
  if (event.level !== "METRIC" || !event.timestamp) return points;
  const metric = event.payload?.metric as string | undefined;
  const value = event.payload?.value;
  if (!metric || value === undefined) return points;
  if (metric !== "cpu_pct" && metric !== "error_rate") return points;

  const t = event.timestamp;
  const next = [...points];
  const last = next[next.length - 1];
  if (last && last.timestamp === t) {
    next[next.length - 1] = { ...last, [metric]: Number(value) };
  } else {
    next.push({
      timestamp: t,
      cpu_pct: metric === "cpu_pct" ? Number(value) : null,
      error_rate: metric === "error_rate" ? Number(value) : null,
    });
  }
  return next.slice(-MAX_POINTS);
}

/* ── Custom SRE tooltips ── */
function CpuTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value?: number | null }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const val = payload[0]?.value;
  return (
    <div className="rounded border border-border bg-card p-1.5 text-xs font-mono shadow-md">
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <p className="font-bold text-blue-600 mt-0.5">
        CPU: {val != null ? `${Number(val).toFixed(2)}%` : "—"}
      </p>
    </div>
  );
}

function ErrorTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value?: number | null }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const val = payload[0]?.value;
  return (
    <div className="rounded border border-border bg-card p-1.5 text-xs font-mono shadow-md">
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <p className="font-bold text-red-600 mt-0.5">
        Error: {val != null ? `${Number(val).toFixed(3)}%` : "—"}
      </p>
    </div>
  );
}

/* ── Axis tick styles ── */
const TICK_STYLE = {
  fontSize: 10,
  fill: "#64748B",
  fontFamily: "JetBrains Mono, ui-monospace, monospace",
};

interface MetricChartProps {
  serviceId: number;
  initialEvents?: Event[];
}

export function MetricChart({ serviceId, initialEvents = [] }: MetricChartProps) {
  const initialPoints = useMemo(() => buildPointsFromEvents(initialEvents), [initialEvents]);
  const [points, setPoints] = useState<MetricDataPoint[]>(initialPoints);

  useEffect(() => {
    setPoints(buildPointsFromEvents(initialEvents));
  }, [initialEvents, serviceId]);

  useEffect(() => {
    wsClient.connect(serviceId);
    const unsub = wsClient.subscribe((msg) => {
      if (msg.type !== "event" || msg.data.level !== "METRIC") return;
      setPoints((prev) => upsertPoint(prev, msg.data));
    });
    return () => unsub();
  }, [serviceId]);

  const chartData = points.map((p) => ({
    ...p,
    time: new Date(p.timestamp).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }),
    error_rate_pct: p.error_rate !== null ? p.error_rate * 100 : null,
  }));

  const maxCpu = chartData.reduce((max, point) => {
    if (point.cpu_pct === null) return max;
    return Math.max(max, point.cpu_pct);
  }, 0);
  const cpuAxisMax = Math.min(100, Math.max(25, Math.ceil((maxCpu + 5) / 10) * 10));

  const maxErrorPct = chartData.reduce((max, point) => {
    if (point.error_rate_pct === null) return max;
    return Math.max(max, point.error_rate_pct);
  }, 0);
  const errorAxisMax = Math.max(1, Math.ceil(maxErrorPct * 1.5 * 10) / 10);

  const latestPoint = chartData[chartData.length - 1];
  const latestCpu = latestPoint?.cpu_pct ?? 0;
  const latestErr = latestPoint?.error_rate_pct ?? 0;

  return (
    <div className="flex h-[480px] flex-col rounded-lg border border-border bg-card overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-bold font-mono uppercase tracking-wider text-foreground">
            Live Telemetry Tracks
          </span>
          <span className="text-muted-foreground/40 font-mono text-xs hidden sm:inline">•</span>
          <span className="font-mono text-[11px] text-muted-foreground hidden sm:inline">
            last {MAX_POINTS} samples
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono text-muted-foreground">
          <span>sync: realtime</span>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="font-mono text-xs text-muted-foreground/60">
            no metric data — start the simulator
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col min-h-0">
          {/* Track 1: CPU Utilization */}
          <div className="flex-1 min-h-0 px-3 pt-2.5 pb-1 flex flex-col">
            <div className="flex items-center justify-between text-[11px] font-mono px-1 mb-1">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-xs bg-blue-600" />
                <span className="font-semibold text-foreground">CPU Utilization</span>
                <span className="text-muted-foreground/40">•</span>
                <span className="text-muted-foreground">
                  now: <span className="font-semibold text-foreground">{latestCpu.toFixed(1)}%</span>
                </span>
              </div>
              <span className="text-muted-foreground text-[10px]">peak: {maxCpu.toFixed(1)}%</span>
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 2, left: -16 }}>
                  <CartesianGrid
                    strokeDasharray="2 2"
                    stroke="rgba(150, 150, 150, 0.15)"
                    vertical={false}
                  />
                  <XAxis dataKey="time" hide />
                  <YAxis
                    domain={[0, cpuAxisMax]}
                    tick={TICK_STYLE}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip content={<CpuTooltip />} />
                  <Line
                    type="linear"
                    dataKey="cpu_pct"
                    stroke={CPU_COLOR}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Track 2: Error Rate */}
          <div className="flex-1 min-h-0 px-3 pt-2 pb-2 flex flex-col border-t border-border">
            <div className="flex items-center justify-between text-[11px] font-mono px-1 mb-1">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-xs bg-red-600" />
                <span className="font-semibold text-foreground">Error Rate</span>
                <span className="text-muted-foreground/40">•</span>
                <span className="text-muted-foreground">
                  now: <span className="font-semibold text-foreground">{latestErr.toFixed(3)}%</span>
                </span>
              </div>
              <span className="text-muted-foreground text-[10px]">peak: {maxErrorPct.toFixed(3)}%</span>
            </div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid
                    strokeDasharray="2 2"
                    stroke="rgba(150, 150, 150, 0.15)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="time"
                    tick={TICK_STYLE}
                    minTickGap={40}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, errorAxisMax]}
                    tick={TICK_STYLE}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip content={<ErrorTooltip />} />
                  <Line
                    type="linear"
                    dataKey="error_rate_pct"
                    stroke={ERR_COLOR}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
