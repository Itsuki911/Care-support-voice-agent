import "server-only";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseEnv } from "node:util";

type Observation = { sessionId?: string; traceId?: string; startTime: string; type?: string; model?: string; totalCost?: number | null };
type Score = { name: string; value: unknown; timestamp: string; dataType?: string; subject?: { kind: string; id: string; traceId?: string } };
type Dashboard = { connected: boolean; start: string; end: string; count: number; average: number | null; cost: number | null; trend: { day: string; quality: number | null }[]; sessions: { id: string; time: string; model: string; score: number | null }[] };
const mean = (values: number[]) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
const dayKey = (date: Date) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(date);

export function dateRange(from?: string, to?: string) {
  const today = dayKey(new Date());
  const parse = (value?: string) => {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const date = new Date(`${value}T00:00:00+09:00`);
    return Number.isFinite(date.getTime()) && dayKey(date) === value ? date : null;
  };
  const first = parse(from);
  const last = parse(to);
  if (first && last && first <= last && last.getTime() - first.getTime() < 366 * 86400000) {
    return { start: first, end: new Date(last.getTime() + 86400000) };
  }
  const end = new Date(parse(today)!.getTime() + 86400000);
  return { start: new Date(end.getTime() - 7 * 86400000), end };
}

export function getLangfuseConnection() {
  // Prefer explicit web/server configuration. The existing agent .env is a local fallback.
  let config: Record<string, string | undefined> = process.env;
  if (![config.LANGFUSE_BASE_URL, config.LANGFUSE_HOST, config.LANGFUSE_PUBLIC_KEY, config.LANGFUSE_SECRET_KEY].some(Boolean)) {
    try {
      config = parseEnv(readFileSync(resolve(process.cwd(), "../Test-LiveKit/.env"), "utf8"));
    } catch {
      // No local agent configuration; leave the dashboard disconnected.
    }
  }
  const host = (config.LANGFUSE_BASE_URL || config.LANGFUSE_HOST)?.trim();
  const pk = config.LANGFUSE_PUBLIC_KEY?.trim();
  const sk = config.LANGFUSE_SECRET_KEY?.trim();
  if (!host || !pk || !sk) return null;
  try {
    const base = new URL(host);
    if (base.protocol !== "https:" && !(base.protocol === "http:" && ["localhost", "127.0.0.1", "::1", "[::1]"].includes(base.hostname))) return null;
    return { base, headers: { Authorization: `Basic ${Buffer.from(`${pk}:${sk}`).toString("base64")}` } };
  } catch {
    return null;
  }

}

export async function checkLangfuseConnection(): Promise<{ state: "connected" | "not_configured" | "unauthorized" | "unavailable"; checkedAt: string }> {
  const checkedAt = new Date().toISOString();
  const connection = getLangfuseConnection();
  if (!connection) return { state: "not_configured", checkedAt };
  try {
    const url = new URL("/api/public/v2/observations", connection.base);
    const now = new Date();
    url.searchParams.set("fromStartTime", new Date(now.getTime() - 86400000).toISOString());
    url.searchParams.set("toStartTime", now.toISOString());
    url.searchParams.set("fields", "core");
    url.searchParams.set("limit", "1");
    const response = await fetch(url, { headers: connection.headers, cache: "no-store", signal: AbortSignal.timeout(15000), redirect: "error" });
    if (response.status === 401 || response.status === 403) return { state: "unauthorized", checkedAt };
    if (!response.ok) return { state: "unavailable", checkedAt };
    const payload = await response.json() as { data?: unknown };
    return { state: Array.isArray(payload.data) ? "connected" : "unavailable", checkedAt };
  } catch {
    return { state: "unavailable", checkedAt };
  }
}

export async function getDashboard(from?: string, to?: string): Promise<Dashboard> {
  const { start, end } = dateRange(from, to);
  const empty: Dashboard = { connected: false, start: start.toISOString(), end: end.toISOString(), count: 0, average: null, cost: null, trend: [], sessions: [] };
  const connection = getLangfuseConnection();
  if (!connection) return empty;
  const { base, headers } = connection;
  try {
    async function pages<T>(path: string, params: Record<string, string>): Promise<T[]> {
      const result: T[] = [];
      const seen = new Set<string>();
      let cursor: string | undefined;
      do {
        const url = new URL(path, base);
        for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
        if (cursor) url.searchParams.set("cursor", cursor);
        const response = await fetch(url, { headers, cache: "no-store", signal: AbortSignal.timeout(15000), redirect: "error" });
        if (!response.ok) throw new Error("Langfuse request failed");
        const page = await response.json() as { data: T[]; meta?: { cursor?: string | null } };
        if (!Array.isArray(page.data)) throw new Error("Invalid Langfuse response");
        result.push(...page.data);
        cursor = page.meta?.cursor || undefined;
        if (cursor && seen.has(cursor)) throw new Error("Repeated cursor");
        if (cursor) seen.add(cursor);
      } while (cursor);
      return result;
    }
    const [observations, allScores] = await Promise.all([
      pages<Observation>("/api/public/v2/observations", { fields: "core,basic,model,usage", fromStartTime: start.toISOString(), toStartTime: end.toISOString(), limit: "1000" }),
      pages<Score>("/api/public/v3/scores", { fields: "subject", limit: "100" }),
    ]);
    const scores = allScores.filter(s => ["secretary.", "text.conv.", "voice.conv."].some(prefix => s.name.startsWith(prefix)) && s.dataType === "NUMERIC" && typeof s.value === "number" && Number.isFinite(s.value) && s.value >= 0 && s.value <= 1 && new Date(s.timestamp) >= start && new Date(s.timestamp) < end);
    const bySession = new Map<string, { id: string; time: string; models: Set<string>; traces: Set<string> }>();
    for (const o of observations) {
      if (!o.sessionId || !o.startTime) continue;
      let session = bySession.get(o.sessionId);
      if (!session) { session = { id: o.sessionId, time: o.startTime, models: new Set(), traces: new Set() }; bySession.set(o.sessionId, session); }
      if (o.startTime < session.time) session.time = o.startTime;
      if (o.type === "GENERATION" && o.model) session.models.add(o.model);
      if (o.traceId) session.traces.add(o.traceId);
    }
    const sessions = [...bySession.values()].sort((a, b) => b.time.localeCompare(a.time)).slice(0, 10).map(s => ({ id: s.id, time: s.time, model: [...s.models].join(", ") || "N/A", score: mean(scores.filter(x => x.subject && (x.subject.kind === "session" ? x.subject.id === s.id : s.traces.has(x.subject.kind === "trace" ? x.subject.id : x.subject.traceId || ""))).map(x => x.value as number)) }));
    const days = Array.from({ length: (end.getTime() - start.getTime()) / 86400000 }, (_, i) => dayKey(new Date(start.getTime() + i * 86400000)));
    const trend = days.map(day => ({ day: day.replaceAll("-", "/"), quality: mean(scores.filter(s => dayKey(new Date(s.timestamp)) === day).map(s => s.value as number)) }));
    const costs = observations.filter(o => o.type === "GENERATION" && typeof o.totalCost === "number" && Number.isFinite(o.totalCost)).map(o => o.totalCost as number);
    return { connected: true, start: empty.start, end: empty.end, count: bySession.size, average: mean(scores.map(s => s.value as number)), cost: costs.length ? costs.reduce((a, b) => a + b, 0) : null, trend, sessions };
  } catch {
    return empty;
  }
}
