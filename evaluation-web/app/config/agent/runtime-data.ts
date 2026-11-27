import "server-only";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseEnv } from "node:util";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { getLangfuseConnection } from "../../dashboard-data";

export const models = ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-flash"] as const;
export const tools = ["search_emails", "read_email", "send_email", "search_memories", "list_recent_memories", "save_memory", "search_documents", "search_web", "get_schedule", "get_tasks"] as const;
export const root = resolve(process.cwd(), "../Test-LiveKit");
export const configPath = resolve(root, ".agent-runtime-config.json");
export type Config = { model: string; llm: { temperature: number | null; reasoning_effort: string; max_tokens: number | null; prompt_caching: boolean }; prompt: string; disabled_tools: string[]; memory: { extraction_frequency: "session_end" | "every_response" }; rag: { top_k: number; similarity_threshold: number; chunk_size: number; chunk_overlap: number; embedding_model: string; metadata_filter: Record<string, unknown> | null; rerank_top_n: number | null; max_iterations: number | null; max_steps: number | null; max_execution_time: number | null; early_stopping_method: string | null }; harness: { memory_enabled: boolean; rag_enabled: boolean; memory_prompt_recent_limit: number; stt_model: string; tts_model: string; tts_voice: string } };

export function getRuntimeSettings(): Config {
  let env: Record<string, string | undefined> = {};
  try { env = parseEnv(readFileSync(resolve(root, ".env"), "utf8")); } catch { /* optional */ }
  env = { ...env, ...process.env };
  const version = /^v\d+$/.test(env.SYSTEM_PROMPT_VERSION || "") ? env.SYSTEM_PROMPT_VERSION : "v2";
  const prompt = readFileSync(resolve(root, "prompts", `system-${version}.md`), "utf8").trim();
  const number = (key: string, fallback: number) => Number(env[key] || fallback);
  const base: Config = { model: env.OPENROUTER_MODEL || models[1], llm: { temperature: null, reasoning_effort: "auto", max_tokens: null, prompt_caching: true }, prompt, disabled_tools: [], memory: { extraction_frequency: "session_end" }, rag: { top_k: number("RAG_TOP_K", 5), similarity_threshold: number("RAG_SIMILARITY_THRESHOLD", 0), chunk_size: number("RAG_CHUNK_SIZE", 450), chunk_overlap: number("RAG_CHUNK_OVERLAP", 80), embedding_model: env.EMBEDDING_MODEL || "embeddinggemma-2:270m", metadata_filter: null, rerank_top_n: 5, max_iterations: 5, max_steps: 10, max_execution_time: 30, early_stopping_method: "force" }, harness: { memory_enabled: !["0", "false", "no", "off"].includes((env.MEMORY_ENABLED || "true").toLowerCase()), rag_enabled: !["0", "false", "no", "off"].includes((env.RAG_ENABLED || "true").toLowerCase()), memory_prompt_recent_limit: number("MEMORY_PROMPT_RECENT_LIMIT", 5), stt_model: env.STT_MODEL || "", tts_model: env.TTS_MODEL || "", tts_voice: env.TTS_VOICE || "" } };
  try { const saved = JSON.parse(readFileSync(configPath, "utf8")) as Partial<Config>; return { ...base, ...saved, llm: { ...base.llm, ...saved.llm }, memory: { ...base.memory, ...saved.memory }, rag: { ...base.rag, ...saved.rag }, harness: { ...base.harness, ...saved.harness } }; }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return base; throw error; }
}

type Obs = { type?: string; name?: string; model?: string; traceId?: string; latency?: number; outputCost?: number | null };
type Score = { name: string; value: unknown; dataType: string; subject?: { kind: string; id: string; traceId?: string } };
export type ModelComparison = { model: string; count: number; latency: number | null; cost: number | null; score: number | null };
export async function getModelComparisons(): Promise<ModelComparison[] | null> {
  const connection = getLangfuseConnection();
  if (!connection) return null;
  try {
    async function pages<T>(path: string, params: Record<string, string>): Promise<T[]> {
      const values: T[] = []; const seen = new Set<string>(); let cursor: string | undefined;
      do {
        const url = new URL(path, connection!.base);
        for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
        if (cursor) url.searchParams.set("cursor", cursor);
        const response = await fetch(url, { headers: connection!.headers, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15000) });
        if (!response.ok) throw new Error("API failure");
        const page = await response.json() as { data: T[]; meta?: { cursor?: string } };
        if (!Array.isArray(page.data)) throw new Error("API response");
        values.push(...page.data); cursor = page.meta?.cursor || undefined;
        if (cursor && seen.has(cursor)) throw new Error("cursor");
        if (cursor) seen.add(cursor);
      } while (cursor);
      return values;
    }
    const end = new Date();
    const [observations, scores] = await Promise.all([
      pages<Obs>("/api/public/v2/observations", { fields: "core,basic,model,usage,metrics", type: "GENERATION", fromStartTime: new Date(end.getTime() - 365 * 86400000).toISOString(), toStartTime: end.toISOString(), limit: "1000" }),
      pages<Score>("/api/public/v3/scores", { fields: "subject", limit: "100" }),
    ]);
    const mean = (nums: number[]) => nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
    return models.map(model => {
      const rows = observations.filter(o => o.name === "llm_request" && (o.model === model || o.model === model.split("/")[1]));
      const ids = new Set(rows.map(o => o.traceId).filter(Boolean));
      const values = scores.filter(s => ["secretary.", "text.conv.", "voice.conv."].some(p => s.name.startsWith(p)) && s.dataType === "NUMERIC" && typeof s.value === "number" && s.value >= 0 && s.value <= 1 && !!s.subject && ids.has(s.subject.kind === "trace" ? s.subject.id : s.subject.traceId)).map(s => s.value as number);
      return { model, count: rows.length, latency: mean(rows.map(o => o.latency).filter((v): v is number => typeof v === "number" && Number.isFinite(v))), cost: mean(rows.map(o => o.outputCost).filter((v): v is number => typeof v === "number" && Number.isFinite(v))), score: mean(values) };
    });
  } catch { return null; }
}

export async function getMemoryOverview(): Promise<{ counts: Record<string, number>; history: { action: string; created_at: string }[] } | null> {
  try {
    const python = process.platform === "win32" ? resolve(root, ".venv/Scripts/python.exe") : resolve(root, ".venv/bin/python");
    const { stdout } = await promisify(execFile)(python, [resolve(root, "memory_dashboard.py")], { cwd: root, timeout: 10000, maxBuffer: 100000 });
    return JSON.parse(stdout);
  } catch { return null; }
}
