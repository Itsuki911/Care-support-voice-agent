"use server";

import { writeFile, rename, unlink } from "node:fs/promises";
import { openSync, closeSync, readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { configPath, getRuntimeSettings, models, tools } from "./runtime-data";

export async function saveSettings(form: FormData) {
  const config = getRuntimeSettings();
  const section = form.get("section");
  if (section === "model") {
    const model = String(form.get("model") || "");
    if (!(models as readonly string[]).includes(model)) throw new Error("モデルを確認してください。");
    const tempText = String(form.get("temperature") || "").trim();
    const tokenText = String(form.get("max_tokens") || "").trim();
    const temperature = tempText ? Number(tempText) : null;
    const max_tokens = tokenText ? Number(tokenText) : null;
    const reasoning_effort = String(form.get("reasoning_effort") || "auto");
    if (temperature !== null && (!Number.isFinite(temperature) || temperature < 0 || temperature > 2)) throw new Error("temperature is invalid.");
    if (max_tokens !== null && (!Number.isInteger(max_tokens) || max_tokens < 1 || max_tokens > 32768)) throw new Error("max_tokens is invalid.");
    if (!["auto", "none", "minimal", "low", "medium", "high", "xhigh"].includes(reasoning_effort)) throw new Error("reasoning_effort is invalid.");
    config.model = model;
    config.llm = { temperature, max_tokens, reasoning_effort, prompt_caching: form.has("prompt_caching") };
  } else if (section === "prompt") {
    const prompt = String(form.get("prompt") || "").trim();
    if (!prompt || prompt.length > 100000) throw new Error("プロンプトを確認してください。");
    config.prompt = prompt;
  } else if (section === "tools") {
    const enabled = form.getAll("enabled").map(String);
    if (enabled.some(name => !(tools as readonly string[]).includes(name))) throw new Error("ツールを確認してください。");
    config.disabled_tools = tools.filter(name => !enabled.includes(name));
  } else if (section === "memory") {
    const extraction_frequency = String(form.get("extraction_frequency") || "");
    if (extraction_frequency !== "session_end" && extraction_frequency !== "every_response") throw new Error("extraction_frequency is invalid.");
    config.memory = { extraction_frequency };
  } else if (section === "rag") {
    const top_k = Number(form.get("top_k")), similarity_threshold = Number(form.get("similarity_threshold")), chunk_size = Number(form.get("chunk_size")), chunk_overlap = Number(form.get("chunk_overlap"));
    if (!Number.isInteger(top_k) || top_k < 1 || top_k > 50 || !Number.isFinite(similarity_threshold) || similarity_threshold < 0 || similarity_threshold > 1 || !Number.isInteger(chunk_size) || chunk_size < 100 || chunk_size > 4000 || !Number.isInteger(chunk_overlap) || chunk_overlap < 0 || chunk_overlap > 2000 || chunk_overlap >= chunk_size) throw new Error("RAG パラメーターを確認してください。");
    const embedding_model = String(form.get("embedding_model") || "").trim();
    if (!embedding_model || embedding_model.length > 150 || !/^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$/.test(embedding_model)) throw new Error("Embedding model is invalid.");
    const optionalNumber = (name: string, max: number) => {
      const raw = String(form.get(name) || "").trim();
      if (!raw) return null;
      const value = Number(raw);
      if (!Number.isInteger(value) || value < 1 || value > max) throw new Error(`${name} is invalid.`);
      return value;
    };
    const rawFilter = String(form.get("metadata_filter") || "").trim();
    let metadata_filter: Record<string, unknown> | null = null;
    if (rawFilter) {
      if (rawFilter.length > 10000) throw new Error("metadata_filter is too large.");
      const parsed: unknown = JSON.parse(rawFilter);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("metadata_filter must be an object.");
      metadata_filter = parsed as Record<string, unknown>;
    }
    const early = String(form.get("early_stopping_method") || "");
    if (early && !["force", "generate"].includes(early)) throw new Error("early_stopping_method is invalid.");
    config.rag = { top_k, similarity_threshold, chunk_size, chunk_overlap, embedding_model, metadata_filter, rerank_top_n: optionalNumber("rerank_top_n", 1000), max_iterations: optionalNumber("max_iterations", 1000), max_steps: optionalNumber("max_steps", 1000), max_execution_time: optionalNumber("max_execution_time", 86400), early_stopping_method: early || null };
  } else if (section === "harness") {
    const limit = Number(form.get("memory_prompt_recent_limit"));
    if (!Number.isInteger(limit) || limit < 1 || limit > 5) throw new Error("メモリ件数を確認してください。");
    const stt_model = String(form.get("stt_model") || "").trim(), tts_model = String(form.get("tts_model") || "").trim(), tts_voice = String(form.get("tts_voice") || "").trim();
    if ([stt_model, tts_model, tts_voice].some(value => value.length > 150) || ([stt_model, tts_model, tts_voice].some(Boolean) && ![stt_model, tts_model, tts_voice].every(Boolean))) throw new Error("音声設定を確認してください。");
    config.harness = { memory_enabled: form.has("memory_enabled"), rag_enabled: form.has("rag_enabled"), memory_prompt_recent_limit: limit, stt_model, tts_model, tts_voice };
  } else throw new Error("設定項目が不正です。");
  const lock = `${configPath}.lock`;
  const fd = openSync(lock, "wx", 0o600);
  const temp = `${configPath}.${randomUUID()}.tmp`;
  try {
    let saved: Partial<typeof config> = {};
    try { saved = JSON.parse(readFileSync(configPath, "utf8")); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    if (section === "model") { saved.model = config.model; saved.llm = config.llm; }
    if (section === "prompt") saved.prompt = config.prompt;
    if (section === "tools") saved.disabled_tools = config.disabled_tools;
    if (section === "memory") saved.memory = config.memory;
    if (section === "rag") saved.rag = config.rag;
    if (section === "harness") saved.harness = config.harness;
    await writeFile(temp, JSON.stringify(saved, null, 2), { encoding: "utf8", mode: 0o600, flag: "wx" });
    await rename(temp, configPath);
  } finally { closeSync(fd); await unlink(temp).catch(() => {}); await unlink(lock).catch(() => {}); }
  revalidatePath("/config/agent");
}
