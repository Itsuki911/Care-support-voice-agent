"use client";

import { useState } from "react";
import { Bot } from "lucide-react";
import { saveSettings } from "./actions";
import type { Config, ModelComparison } from "./runtime-data";

const modelOptions = ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-flash"];
const toolLabels: Record<string, string> = { search_emails: "メール検索", read_email: "メール本文の取得", send_email: "メール送信", search_memories: "メモリ検索", list_recent_memories: "最近のメモリ取得", save_memory: "メモリ保存", search_documents: "文書検索", search_web: "Web 検索", get_schedule: "予定取得（秘書）", get_tasks: "タスク取得（秘書）" };
type Memory = { counts: Record<string, number>; history: { action: string; created_at: string }[] } | null;
type Props = { settings: Config; comparisons: ModelComparison[] | null; memory: Memory };
const sections = ["LLM", "プロンプト", "ツール", "RAG", "メモリ", "ハーネス"];

export default function AgentSettings({ settings, comparisons, memory }: Props) {
  const [section, setSection] = useState("LLM");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(form: FormData) {
    setMessage("");
    setPending(true);
    try { await saveSettings(form); setMessage("保存しました。新しいセッションから反映されます。"); }
    catch { setMessage("保存できませんでした。入力値とサーバーの状態を確認してください。"); }
    finally { setPending(false); }
  }
  const button = <button className="agent-button agent-primary" type="submit" disabled={pending}>{pending ? "保存中…" : "保存"}</button>;
  return <main className="agent-main">
    <header className="agent-header"><div className="heading"><div className="home"><Bot size={29} /></div><div><h1>Agent設定</h1><p>設定は保存後、新しいセッションに反映されます。</p></div></div></header>
    <nav className="agent-tabs" aria-label="設定カテゴリ">{sections.map(name => <button type="button" key={name} aria-pressed={section === name} onClick={() => { setSection(name); setMessage(""); }}>{name}</button>)}</nav>
    <div className="llm-grid"><div className="agent-stack">
      {section === "LLM" && <section className="card agent-card"><h2>LLM設定</h2><p>provider: OpenRouter</p><form action={submit} className="agent-live-form"><input type="hidden" name="section" value="model" /><label>model<select name="model" defaultValue={settings.model}>{!modelOptions.includes(settings.model) && <option value={settings.model} disabled>{settings.model}（現在の設定）</option>}{modelOptions.map(model => <option key={model}>{model}</option>)}</select></label>
        <label>temperature<input type="number" name="temperature" min="0" max="2" step="0.01" defaultValue={settings.llm.temperature ?? ""} placeholder="auto" /></label>
        <label>reasoning_effort<select name="reasoning_effort" defaultValue={settings.llm.reasoning_effort}>{["auto", "none", "minimal", "low", "medium", "high", "xhigh"].map(level => <option key={level}>{level}</option>)}</select></label>
        <label>max_tokens<input type="number" name="max_tokens" min="1" max="32768" defaultValue={settings.llm.max_tokens ?? ""} placeholder="auto" /></label>
        <label className="agent-tool"><input type="checkbox" name="prompt_caching" defaultChecked={settings.llm.prompt_caching} />prompt_caching</label>
        <p>空欄または auto はプロバイダー既定値を使用します。モデル・プロバイダーによって対応しない設定があります。キャッシュを無効にしても、プロバイダー側の自動キャッシュは制御できない場合があります。</p>{button}</form></section>}
      {section === "プロンプト" && <section className="card agent-card"><h2>システムプロンプト</h2><p>通常の音声・テキストセッションに適用されます。秘書モードは専用プロンプトを使用します。</p><form action={submit} className="agent-live-form"><input type="hidden" name="section" value="prompt" /><label>system_prompt<textarea name="prompt" required maxLength={100000} rows={22} defaultValue={settings.prompt} /></label>{button}</form></section>}
      {section === "ツール" && <section className="card agent-card"><h2>ツール</h2><p>実際に利用できるツールは、モードと接続設定にも依存します。外部操作の承認は維持されます。</p><form action={submit} className="agent-live-form"><input type="hidden" name="section" value="tools" />{Object.entries(toolLabels).map(([name, label]) => <label className="agent-tool" key={name}><input type="checkbox" name="enabled" value={name} defaultChecked={!settings.disabled_tools.includes(name)} />{label} <small>{name}</small></label>)}{button}</form></section>}
      {section === "RAG" && <section className="card agent-card"><h2>RAG設定</h2><form action={submit} className="agent-live-form">
        <input type="hidden" name="section" value="rag" />
        <label>embedding_model<input name="embedding_model" maxLength={150} defaultValue={settings.rag.embedding_model} required /></label>
        <p>Ollama のモデル名を指定します。既存の 768 次元インデックスと互換のあるモデルを使用し、変更時は文書を再取り込みしてください。</p>
        <label>top_k<input name="top_k" type="number" min="1" max="50" defaultValue={settings.rag.top_k} required /></label>
        <label>similarity_threshold<input name="similarity_threshold" type="number" min="0" max="1" step="0.01" defaultValue={settings.rag.similarity_threshold} required /></label>
        <label>chunk_size<input name="chunk_size" type="number" min="100" max="4000" defaultValue={settings.rag.chunk_size} required /></label>
        <label>chunk_overlap<input name="chunk_overlap" type="number" min="0" max="2000" defaultValue={settings.rag.chunk_overlap} required /></label>
        <p>チャンク設定は新しく取り込む文書に適用されます。既存文書は自動で再取り込みされません。</p>
        <fieldset className="rag-future"><legend>将来用の設定（保存のみ・未適用）</legend>
          <p>次の項目の初期値は仮値です。保存できますが、現在の検索や Agent の動作には反映されません。</p>
          <label>metadata_filter (JSON object)<textarea name="metadata_filter" rows={3} defaultValue={settings.rag.metadata_filter == null ? "" : JSON.stringify(settings.rag.metadata_filter, null, 2)} placeholder={'{"category": "example"}'} /></label>
          <label>rerank_top_n<input name="rerank_top_n" type="number" min="1" max="1000" defaultValue={settings.rag.rerank_top_n ?? 5} /></label>
          <label>max_iterations<input name="max_iterations" type="number" min="1" max="1000" defaultValue={settings.rag.max_iterations ?? 5} /></label>
          <label>max_steps<input name="max_steps" type="number" min="1" max="1000" defaultValue={settings.rag.max_steps ?? 10} /></label>
          <label>max_execution_time (seconds)<input name="max_execution_time" type="number" min="1" max="86400" defaultValue={settings.rag.max_execution_time ?? 30} /></label>
          <label>early_stopping_method<select name="early_stopping_method" defaultValue={settings.rag.early_stopping_method ?? "force"}><option value="">未設定</option><option value="force">force</option><option value="generate">generate</option></select></label>
        </fieldset>{button}</form></section>}
      {section === "メモリ" && <section className="card agent-card"><h2>長期メモリ</h2><form action={submit} className="agent-live-form"><input type="hidden" name="section" value="memory" /><label>extraction_frequency<select name="extraction_frequency" defaultValue={settings.memory.extraction_frequency}><option value="session_end">session_end（会話終了ボタン）</option><option value="every_response">every_response（各回答後）</option></select></label><p>each response では会話中に未処理の発話をバックグラウンドで抽出します。利用回数・費用が増える場合があります。</p>{button}</form>{memory ? <><dl className="evaluator-summary">{Object.entries(memory.counts).map(([name, count]) => <div key={name}><dt>{name}</dt><dd>{count} 件</dd></div>)}</dl><h2>最近の履歴</h2>{memory.history.length ? <ul>{memory.history.map((item, i) => <li key={i}>{item.action} · {new Intl.DateTimeFormat("ja-JP", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Tokyo" }).format(new Date(item.created_at))} JST</li>)}</ul> : <p>履歴はありません。</p>}</> : <p>PostgreSQL のメモリ情報を取得できません。DB 接続設定と起動状態を確認してください。</p>}</section>}
      {section === "ハーネス" && <section className="card agent-card"><h2>ハーネス設定</h2><form action={submit} className="agent-live-form"><input type="hidden" name="section" value="harness" /><label className="agent-tool"><input type="checkbox" name="memory_enabled" defaultChecked={settings.harness.memory_enabled} />memory_enabled</label><label className="agent-tool"><input type="checkbox" name="rag_enabled" defaultChecked={settings.harness.rag_enabled} />rag_enabled</label><label>memory_prompt_recent_limit<input type="number" name="memory_prompt_recent_limit" min="1" max="5" defaultValue={settings.harness.memory_prompt_recent_limit} required /></label><label>stt_model<input name="stt_model" maxLength={150} defaultValue={settings.harness.stt_model} /></label><label>tts_model<input name="tts_model" maxLength={150} defaultValue={settings.harness.tts_model} /></label><label>tts_voice<input name="tts_voice" maxLength={150} defaultValue={settings.harness.tts_voice} /></label><p>音声設定は3項目すべてを入力、またはすべて空にしてください。認証情報は実行環境で管理します。</p>{button}</form></section>}
      <p role="status">{message}</p>
    </div><div className="agent-stack">{section === "LLM" && <section className="card agent-card"><h2>モデルの比較</h2><p>過去365日の Langfuse 実測値。評価条件やセッション数は異なります。</p>{comparisons ? <div className="table-wrap"><table><thead><tr><th>モデル</th><th>生成数</th><th>評価平均</th><th>平均時間</th><th>平均出力コスト</th></tr></thead><tbody>{comparisons.map(row => <tr key={row.model}><td>{row.model}</td><td>{row.count}</td><td>{row.score?.toFixed(2) ?? "N/A"}</td><td>{row.latency == null ? "N/A" : `${row.latency.toFixed(2)} 秒`}</td><td>{row.cost == null ? "N/A" : `$${row.cost.toFixed(5)}`}</td></tr>)}</tbody></table></div> : <p>Langfuse の比較データを取得できません。</p>}<p>評価はトレースに紐づく DeepEval の平均、出力コストは計測済み応答の平均です。</p></section>}</div></div>
  </main>;
}
