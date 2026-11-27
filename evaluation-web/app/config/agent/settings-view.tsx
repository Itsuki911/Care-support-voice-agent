"use client";

import { useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Database,
  FileText,
  Info,
  Mic,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";
import { saveSettings } from "./actions";
import type { Config, ModelComparison } from "./runtime-data";

const modelOptions: { id: string; tag: string; note: string }[] = [
  { id: "anthropic/claude-haiku-5.5", tag: "高速・安定", note: "応答速度と日本語品質のバランスが良好" },
  { id: "openai/gpt-6-luna", tag: "日本語・切替", note: "自然な日本語と多言語切替に強い" },
  { id: "deepseek/deepseek-v4.1-flash-1017", tag: "高速・低コスト", note: "軽量で高速な応答向け" },
  { id: "qwen/qwen3.8-flash", tag: "忠実性重視", note: "ツール結果に沿った正確な回答向け" },
];

const reasoningOptions: { value: string; label: string }[] = [
  { value: "auto", label: "auto（モデル既定におまかせ）" },
  { value: "none", label: "none（思考なし・最速）" },
  { value: "minimal", label: "minimal（最小限の思考）" },
  { value: "low", label: "low（軽め・音声対話向け）" },
  { value: "medium", label: "medium（標準）" },
  { value: "high", label: "high（じっくり推論）" },
  { value: "xhigh", label: "xhigh（最大推論・低速）" },
];

type ToolMeta = {
  name: string;
  label: string;
  description: string;
  requiresApproval?: boolean;
};

const toolGroups: { title: string; badge: string; items: ToolMeta[] }[] = [
  {
    title: "外部サービス（人の承認が必要）",
    badge: "承認必須",
    items: [
      { name: "search_emails", label: "メール検索", description: "Gmail の受信トレイから条件に合うメールを探します", requiresApproval: true },
      { name: "read_email", label: "メール本文の取得", description: "指定したメールの内容を読み取ります（既読にしません）", requiresApproval: true },
      { name: "send_email", label: "メール送信", description: "確認画面で許可された宛先・本文でメールを送信します", requiresApproval: true },
      { name: "search_web", label: "Web 検索", description: "最新情報や外部知識を Tavily 経由で検索します", requiresApproval: true },
    ],
  },
  {
    title: "長期メモリ・ローカル文書検索（内部処理）",
    badge: "自動実行可",
    items: [
      { name: "search_memories", label: "メモリ検索", description: "過去の会話から保存した記憶を意味検索で探します" },
      { name: "list_recent_memories", label: "最近のメモリ取得", description: "直近で保存・更新された記憶の一覧を取得します" },
      { name: "save_memory", label: "メモリ保存", description: "「覚えておいて」と頼まれた内容を即時保存します" },
      { name: "search_documents", label: "文書検索（RAG）", description: "登録済みの PDF / Markdown / TXT から根拠を検索します" },
    ],
  },
  {
    title: "TEST-秘書モード専用ツール",
    badge: "秘書モード",
    items: [
      { name: "get_schedule", label: "予定取得（秘書）", description: "照合済み社員の会議・予定を DB から取得します" },
      { name: "get_tasks", label: "タスク取得（秘書）", description: "照合済み社員の締切・タスクを DB から取得します" },
    ],
  },
];

const allToolNames = toolGroups.flatMap((g) => g.items.map((item) => item.name));

type Memory = { counts: Record<string, number>; history: { action: string; created_at: string }[] } | null;
type Props = { settings: Config; comparisons: ModelComparison[] | null; memory: Memory };

const sectionDefs = [
  { id: "LLM", label: "LLM", icon: Cpu, hint: "使用するAIモデルと応答の調整" },
  { id: "プロンプト", label: "プロンプト", icon: FileText, hint: "AIの話し方・振る舞いの指示" },
  { id: "ツール", label: "ツール", icon: Wrench, hint: "メール・検索・メモリ機能のON/OFF" },
  { id: "RAG", label: "RAG（文書検索）", icon: BookOpen, hint: "資料検索の件数・分割サイズ" },
  { id: "メモリ", label: "長期メモリ", icon: Brain, hint: "会話から記憶を抽出するタイミング" },
  { id: "ハーネス", label: "ハーネス・音声", icon: SlidersHorizontal, hint: "機能全体のON/OFFと音声モデル" },
] as const;

type SectionId = (typeof sectionDefs)[number]["id"];

export default function AgentSettings({ settings, comparisons, memory }: Props) {
  const [section, setSection] = useState<SectionId>("LLM");
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [promptDraft, setPromptDraft] = useState(settings.prompt);

  const enabledToolCount = allToolNames.filter((name) => !settings.disabled_tools.includes(name)).length;
  const voiceConfigured = Boolean(
    settings.harness.stt_model && settings.harness.tts_model && settings.harness.tts_voice,
  );
  const totalMemories = memory
    ? Object.values(memory.counts).reduce((sum, count) => sum + count, 0)
    : null;

  async function submit(form: FormData) {
    setFeedback(null);
    setPending(true);
    try {
      await saveSettings(form);
      setFeedback({
        kind: "success",
        text: "設定を保存しました。次に開始する新しいセッションから反映されます。",
      });
    } catch {
      setFeedback({
        kind: "error",
        text: "保存できませんでした。入力値の範囲や JSON 形式、サーバー状態を確認してください。",
      });
    } finally {
      setPending(false);
    }
  }

  const saveBar = (
    <div className="agent-form-footer">
      <button className="agent-button agent-primary agent-save-btn" type="submit" disabled={pending}>
        <Save size={15} />
        {pending ? "保存中…" : "この設定を保存"}
      </button>
      <span className="agent-apply-hint">保存後、新しいセッション開始時に自動で読み込まれます</span>
    </div>
  );

  const activeSectionMeta = sectionDefs.find((s) => s.id === section) ?? sectionDefs[0];

  return (
    <main className="agent-main">
      <header className="agent-header">
        <div className="heading">
          <div className="home">
            <Bot size={28} />
          </div>
          <div>
            <h1>Agent設定</h1>
            <p>AI モデル・話し方・使えるツール・記憶や文書検索の動作をまとめて管理します。</p>
          </div>
        </div>
        <div className="environment">
          <strong>ライブ設定</strong>
          <span>新規セッションから反映</span>
        </div>
      </header>

      <div className="content">
        {/* ひと目で現在の構成がわかる4枚サマリーカード */}
        <section className="metrics agent-kpi-grid" aria-label="現在の設定概要">
          <button type="button" className="card metric agent-kpi-card" onClick={() => { setSection("LLM"); setFeedback(null); }}>
            <div className="icon blue"><Cpu size={24} /></div>
            <div className="agent-kpi-body">
              <h2>使用中の LLM</h2>
              <div className="detail">OpenRouter · キャッシュ {settings.llm.prompt_caching ? "ON" : "OFF"}</div>
              <div className="agent-kpi-value">{settings.model.split("/")[1] || settings.model}</div>
            </div>
          </button>

          <button type="button" className="card metric agent-kpi-card" onClick={() => { setSection("ツール"); setFeedback(null); }}>
            <div className="icon green"><Wrench size={24} /></div>
            <div className="agent-kpi-body">
              <h2>有効なツール</h2>
              <div className="detail">外部操作は承認 UI 必須</div>
              <div className="agent-kpi-value">{enabledToolCount} / {allToolNames.length}</div>
            </div>
          </button>

          <button type="button" className="card metric agent-kpi-card" onClick={() => { setSection("RAG"); setFeedback(null); }}>
            <div className="icon purple"><BookOpen size={24} /></div>
            <div className="agent-kpi-body">
              <h2>RAG 文書検索</h2>
              <div className="detail">{settings.harness.rag_enabled ? `上位 ${settings.rag.top_k} 件を取得` : "ハーネスで無効化中"}</div>
              <div className="agent-kpi-value">{settings.harness.rag_enabled ? "有効" : "無効"}</div>
            </div>
          </button>

          <button type="button" className="card metric agent-kpi-card" onClick={() => { setSection("メモリ"); setFeedback(null); }}>
            <div className="icon blue"><Brain size={24} /></div>
            <div className="agent-kpi-body">
              <h2>長期メモリ</h2>
              <div className="detail">
                {settings.harness.memory_enabled
                  ? settings.memory.extraction_frequency === "session_end"
                    ? "終了ボタン時に抽出"
                    : "各回答後に抽出"
                  : "ハーネスで無効化中"}
              </div>
              <div className="agent-kpi-value">
                {totalMemories == null ? (settings.harness.memory_enabled ? "有効" : "無効") : `${totalMemories} 件`}
              </div>
            </div>
          </button>
        </section>

        {/* タブバー（他画面の .toolbar + .tabs と統一） */}
        <div className="toolbar agent-toolbar">
          <nav className="tabs agent-pill-tabs" aria-label="設定カテゴリ">
            {sectionDefs.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                aria-pressed={section === id}
                onClick={() => {
                  setSection(id);
                  setFeedback(null);
                }}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </nav>
          <span className="agent-section-hint">
            <Info size={15} />
            {activeSectionMeta.hint}
          </span>
        </div>

        {/* 保存結果のフィードバックバナー */}
        {feedback && (
          <div
            role="status"
            className={`agent-feedback-banner ${feedback.kind === "success" ? "is-success" : "is-error"}`}
          >
            {feedback.kind === "success" ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
            <span>{feedback.text}</span>
          </div>
        )}

        {/* メインレイアウト（LLM / メモリのみ実測データ付きの 2 カラム） */}
        <div className={section === "LLM" || section === "メモリ" ? "agent-two-col" : "agent-single-col"}>
          {/* 左カラム：設定フォーム */}
          <div className="agent-stack">
            {section === "LLM" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>LLM（AI モデル）設定</h2>
                  <span className="agent-badge-neutral">プロバイダー: OpenRouter</span>
                </div>
                <p className="agent-panel-lead">
                  会話の応答を生成するモデルと、回答の安定性・速度を調整します。迷ったら「空欄 / auto」のままで問題ありません。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="model" />

                  <div className="agent-field">
                    <label htmlFor="llm-model">
                      <span className="agent-field-title">
                        使用モデル <code className="agent-param-key">model</code>
                      </span>
                      <span className="agent-field-help">
                        音声対話では応答開始（TTFT）が速い軽量モデルがおすすめです。
                      </span>
                    </label>
                    <select id="llm-model" name="model" defaultValue={settings.model}>
                      {!modelOptions.some((m) => m.id === settings.model) && (
                        <option value={settings.model} disabled>
                          {settings.model}（現在の設定）
                        </option>
                      )}
                      {modelOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.id} — [{m.tag}] {m.note}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="agent-field-grid">
                    <div className="agent-field">
                      <label htmlFor="llm-temperature">
                        <span className="agent-field-title">
                          応答のランダムさ <code className="agent-param-key">temperature</code>
                        </span>
                        <span className="agent-field-help">
                          0 に近いほど正確・安定、高いほど表現が多様（0〜2 / 空欄で自動）
                        </span>
                      </label>
                      <input
                        id="llm-temperature"
                        type="number"
                        name="temperature"
                        min="0"
                        max="2"
                        step="0.01"
                        defaultValue={settings.llm.temperature ?? ""}
                        placeholder="auto（推奨）"
                      />
                    </div>

                    <div className="agent-field">
                      <label htmlFor="llm-max-tokens">
                        <span className="agent-field-title">
                          最大出力トークン数 <code className="agent-param-key">max_tokens</code>
                        </span>
                        <span className="agent-field-help">
                          1 回の回答の長さ上限（1〜32768 / 空欄でモデル既定）
                        </span>
                      </label>
                      <input
                        id="llm-max-tokens"
                        type="number"
                        name="max_tokens"
                        min="1"
                        max="32768"
                        defaultValue={settings.llm.max_tokens ?? ""}
                        placeholder="auto（制限なし）"
                      />
                    </div>
                  </div>

                  <div className="agent-field">
                    <label htmlFor="llm-reasoning">
                      <span className="agent-field-title">
                        推論の深さ <code className="agent-param-key">reasoning_effort</code>
                      </span>
                      <span className="agent-field-help">
                        深く考えるほど正確になりますが返答まで時間がかかります。対応モデルのみ反映されます。
                      </span>
                    </label>
                    <select
                      id="llm-reasoning"
                      name="reasoning_effort"
                      defaultValue={settings.llm.reasoning_effort}
                    >
                      {reasoningOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <label className="agent-toggle-card">
                    <input
                      type="checkbox"
                      name="prompt_caching"
                      defaultChecked={settings.llm.prompt_caching}
                    />
                    <div>
                      <strong>
                        プロンプトキャッシュを有効にする <code className="agent-param-key">prompt_caching</code>
                      </strong>
                      <span>
                        システムプロンプトや会話履歴を再利用して、2 ターン目以降のコストと応答時間を抑えます。
                      </span>
                    </div>
                  </label>

                  <p className="agent-callout-note">
                    <Info size={16} />
                    <span>
                      空欄または <code>auto</code> はプロバイダー既定値を使います。モデルによっては未対応の項目や、プロバイダー側で自動キャッシュが働く場合があります。
                    </span>
                  </p>

                  {saveBar}
                </form>
              </section>
            )}

            {section === "プロンプト" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>システムプロンプト（AI の基本指示）</h2>
                  <span className="agent-badge-neutral">
                    {promptDraft.length.toLocaleString()} 文字 · {promptDraft.split(/\r?\n/).length} 行
                  </span>
                </div>
                <p className="agent-panel-lead">
                  通常の音声セッション・テキストセッションで AI に渡される基本ルールです。口調、回答の長さ（例：3 文以内）、ツールの使い分けをここで調整できます。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="prompt" />
                  <div className="agent-field">
                    <label htmlFor="system-prompt-editor">
                      <span className="agent-field-title">
                        プロンプト本文 <code className="agent-param-key">system_prompt</code>
                      </span>
                      <span className="agent-field-help">
                        ※ TEST-秘書モードは専用のプロンプトファイルを使用するため、この設定の影響を受けません。
                      </span>
                    </label>
                    <textarea
                      id="system-prompt-editor"
                      name="prompt"
                      required
                      maxLength={100000}
                      rows={20}
                      className="agent-prompt-textarea"
                      value={promptDraft}
                      onChange={(e) => setPromptDraft(e.target.value)}
                    />
                  </div>
                  {saveBar}
                </form>
              </section>
            )}

            {section === "ツール" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>利用可能なツール</h2>
                  <span className="agent-badge-neutral">{enabledToolCount} / {allToolNames.length} 有効</span>
                </div>
                <p className="agent-panel-lead">
                  AI が会話中に呼び出せる機能を切り替えます。チェックを外したツールは AI に渡されなくなります。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="tools" />
                  <div className="agent-tool-groups">
                    {toolGroups.map((group) => (
                      <div key={group.title} className="agent-tool-group">
                        <div className="agent-tool-group-head">
                          <h3>{group.title}</h3>
                          <span className="agent-badge-subtle">{group.badge}</span>
                        </div>
                        <div className="agent-tool-list">
                          {group.items.map((tool) => (
                            <label className="agent-toggle-card" key={tool.name}>
                              <input
                                type="checkbox"
                                name="enabled"
                                value={tool.name}
                                defaultChecked={!settings.disabled_tools.includes(tool.name)}
                              />
                              <div>
                                <strong>
                                  {tool.label}
                                  <code className="agent-param-key">{tool.name}</code>
                                  {tool.requiresApproval && (
                                    <span className="agent-badge-warn">承認必須</span>
                                  )}
                                </strong>
                                <span>{tool.description}</span>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  {saveBar}
                </form>
              </section>
            )}

            {section === "RAG" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>RAG（ローカル文書検索）設定</h2>
                  <span className={settings.harness.rag_enabled ? "agent-active" : "agent-badge-muted"}>
                    {settings.harness.rag_enabled ? "RAG 有効" : "RAG 無効"}
                  </span>
                </div>
                <p className="agent-panel-lead">
                  PDF・Markdown・TXT の資料から質問に近い箇所を探すときの検索条件と、文書の分割ルールを設定します。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="rag" />

                  <div className="agent-field">
                    <label htmlFor="rag-embedding-model">
                      <span className="agent-field-title">
                        埋め込みモデル（Ollama） <code className="agent-param-key">embedding_model</code>
                      </span>
                      <span className="agent-field-help">
                        文章をベクトル化するローカルモデル名です。既存の 768 次元インデックスと互換のあるモデルを指定し、変更した場合は文書を再取り込みしてください。
                      </span>
                    </label>
                    <input
                      id="rag-embedding-model"
                      name="embedding_model"
                      maxLength={150}
                      defaultValue={settings.rag.embedding_model}
                      required
                    />
                  </div>

                  <div className="agent-field-grid">
                    <div className="agent-field">
                      <label htmlFor="rag-top-k">
                        <span className="agent-field-title">
                          取得する候補件数 <code className="agent-param-key">top_k</code>
                        </span>
                        <span className="agent-field-help">
                          1 回の検索で AI に渡す関連箇所の最大数（1〜50 / 目安: 5）
                        </span>
                      </label>
                      <input
                        id="rag-top-k"
                        name="top_k"
                        type="number"
                        min="1"
                        max="50"
                        defaultValue={settings.rag.top_k}
                        required
                      />
                    </div>

                    <div className="agent-field">
                      <label htmlFor="rag-threshold">
                        <span className="agent-field-title">
                          類似度の下限しきい値 <code className="agent-param-key">similarity_threshold</code>
                        </span>
                        <span className="agent-field-help">
                          この値未満の候補を除外します（0.00〜1.00 / 0 で全件対象）
                        </span>
                      </label>
                      <input
                        id="rag-threshold"
                        name="similarity_threshold"
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        defaultValue={settings.rag.similarity_threshold}
                        required
                      />
                    </div>
                  </div>

                  <div className="agent-field-grid">
                    <div className="agent-field">
                      <label htmlFor="rag-chunk-size">
                        <span className="agent-field-title">
                          分割チャンク文字数 <code className="agent-param-key">chunk_size</code>
                        </span>
                        <span className="agent-field-help">
                          1 ブロックあたりの目安文字数（100〜4000 / 目安: 450）
                        </span>
                      </label>
                      <input
                        id="rag-chunk-size"
                        name="chunk_size"
                        type="number"
                        min="100"
                        max="4000"
                        defaultValue={settings.rag.chunk_size}
                        required
                      />
                    </div>

                    <div className="agent-field">
                      <label htmlFor="rag-chunk-overlap">
                        <span className="agent-field-title">
                          チャンクの重複文字数 <code className="agent-param-key">chunk_overlap</code>
                        </span>
                        <span className="agent-field-help">
                          前後チャンクで重ねる文字数（文脈切れ防止 / chunk_size 未満）
                        </span>
                      </label>
                      <input
                        id="rag-chunk-overlap"
                        name="chunk_overlap"
                        type="number"
                        min="0"
                        max="2000"
                        defaultValue={settings.rag.chunk_overlap}
                        required
                      />
                    </div>
                  </div>

                  <p className="agent-callout-note">
                    <Info size={16} />
                    <span>
                      分割サイズ（<code>chunk_size</code> / <code>chunk_overlap</code>）は新しく取り込む文書に適用されます。既存文書は自動で再取り込みされません。
                    </span>
                  </p>

                  <details className="agent-advanced-box">
                    <summary>
                      <ChevronDown size={16} />
                      将来拡張用の詳細設定（保存のみ・現在の検索動作には未適用）
                    </summary>
                    <p className="agent-advanced-desc">
                      将来の高度な RAG・エージェント制御向けに値を先行保存できます。初期値は仮値であり、現時点の検索結果には影響しません。
                    </p>
                    <div className="agent-field">
                      <label htmlFor="rag-metadata-filter">
                        <span className="agent-field-title">
                          メタデータフィルタ（JSON） <code className="agent-param-key">metadata_filter</code>
                        </span>
                      </label>
                      <textarea
                        id="rag-metadata-filter"
                        name="metadata_filter"
                        rows={3}
                        defaultValue={
                          settings.rag.metadata_filter == null
                            ? ""
                            : JSON.stringify(settings.rag.metadata_filter, null, 2)
                        }
                        placeholder='{"category": "example"}'
                      />
                    </div>
                    <div className="agent-field-grid">
                      <div className="agent-field">
                        <label htmlFor="rag-rerank">
                          <span className="agent-field-title">
                            リランク件数 <code className="agent-param-key">rerank_top_n</code>
                          </span>
                        </label>
                        <input
                          id="rag-rerank"
                          name="rerank_top_n"
                          type="number"
                          min="1"
                          max="1000"
                          defaultValue={settings.rag.rerank_top_n ?? 5}
                        />
                      </div>
                      <div className="agent-field">
                        <label htmlFor="rag-iterations">
                          <span className="agent-field-title">
                            最大反復回数 <code className="agent-param-key">max_iterations</code>
                          </span>
                        </label>
                        <input
                          id="rag-iterations"
                          name="max_iterations"
                          type="number"
                          min="1"
                          max="1000"
                          defaultValue={settings.rag.max_iterations ?? 5}
                        />
                      </div>
                      <div className="agent-field">
                        <label htmlFor="rag-steps">
                          <span className="agent-field-title">
                            最大ステップ数 <code className="agent-param-key">max_steps</code>
                          </span>
                        </label>
                        <input
                          id="rag-steps"
                          name="max_steps"
                          type="number"
                          min="1"
                          max="1000"
                          defaultValue={settings.rag.max_steps ?? 10}
                        />
                      </div>
                      <div className="agent-field">
                        <label htmlFor="rag-exec-time">
                          <span className="agent-field-title">
                            最大実行時間（秒） <code className="agent-param-key">max_execution_time</code>
                          </span>
                        </label>
                        <input
                          id="rag-exec-time"
                          name="max_execution_time"
                          type="number"
                          min="1"
                          max="86400"
                          defaultValue={settings.rag.max_execution_time ?? 30}
                        />
                      </div>
                    </div>
                    <div className="agent-field">
                      <label htmlFor="rag-early-stop">
                        <span className="agent-field-title">
                          早期終了方式 <code className="agent-param-key">early_stopping_method</code>
                        </span>
                      </label>
                      <select
                        id="rag-early-stop"
                        name="early_stopping_method"
                        defaultValue={settings.rag.early_stopping_method ?? "force"}
                      >
                        <option value="">未設定</option>
                        <option value="force">force（上限到達で即終了）</option>
                        <option value="generate">generate（最終回答を生成して終了）</option>
                      </select>
                    </div>
                  </details>

                  {saveBar}
                </form>
              </section>
            )}

            {section === "メモリ" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>長期メモリ抽出設定</h2>
                  <span className={settings.harness.memory_enabled ? "agent-active" : "agent-badge-muted"}>
                    {settings.harness.memory_enabled ? "メモリ有効" : "メモリ無効"}
                  </span>
                </div>
                <p className="agent-panel-lead">
                  ユーザーの好み・習慣・基本情報を会話から自動抽出し、PostgreSQL（pgvector）へ保存するタイミングを選びます。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="memory" />
                  <div className="agent-field">
                    <label htmlFor="memory-freq">
                      <span className="agent-field-title">
                        記憶を抽出するタイミング <code className="agent-param-key">extraction_frequency</code>
                      </span>
                      <span className="agent-field-help">
                        通常は「会話終了ボタン時」が低コストで安定します。「各回答後」は会話中でもリアルタイムに記憶を更新します。
                      </span>
                    </label>
                    <select
                      id="memory-freq"
                      name="extraction_frequency"
                      defaultValue={settings.memory.extraction_frequency}
                    >
                      <option value="session_end">会話終了ボタン時（推奨・低コスト） — session_end</option>
                      <option value="every_response">各回答ごとに裏で抽出 — every_response</option>
                    </select>
                  </div>

                  <p className="agent-callout-note">
                    <Info size={16} />
                    <span>
                      <code>every_response</code> を選ぶと、AI の各回答後に未処理の発話をバックグラウンド抽出するため、LLM 呼び出し回数とコストが増える場合があります。
                    </span>
                  </p>
                  {saveBar}
                </form>
              </section>
            )}

            {section === "ハーネス" && (
              <section className="card panel agent-panel">
                <div className="panel-heading">
                  <h2>ハーネス・音声入出力設定</h2>
                  <span className="agent-badge-neutral">
                    {voiceConfigured ? "音声 + テキスト対応" : "テキスト専用構成"}
                  </span>
                </div>
                <p className="agent-panel-lead">
                  Agent 全体の機能スイッチ（長期メモリ・RAG）と、音声セッションで使う音声認識（STT）・音声合成（TTS）モデルを管理します。
                </p>

                <form action={submit} className="agent-live-form">
                  <input type="hidden" name="section" value="harness" />

                  <div className="agent-tool-list">
                    <label className="agent-toggle-card">
                      <input
                        type="checkbox"
                        name="memory_enabled"
                        defaultChecked={settings.harness.memory_enabled}
                      />
                      <div>
                        <strong>
                          長期メモリ機能を有効にする <code className="agent-param-key">memory_enabled</code>
                        </strong>
                        <span>
                          セッション開始時の直近記憶の読み込みと、記憶検索・保存ツールを有効化します。
                        </span>
                      </div>
                    </label>

                    <label className="agent-toggle-card">
                      <input
                        type="checkbox"
                        name="rag_enabled"
                        defaultChecked={settings.harness.rag_enabled}
                      />
                      <div>
                        <strong>
                          RAG 文書検索を有効にする <code className="agent-param-key">rag_enabled</code>
                        </strong>
                        <span>
                          ローカル PostgreSQL に登録した PDF / Markdown / TXT の検索機能を有効化します。
                        </span>
                      </div>
                    </label>
                  </div>

                  <div className="agent-field">
                    <label htmlFor="harness-recent-limit">
                      <span className="agent-field-title">
                        開始時に読み込む直近メモリ件数{" "}
                        <code className="agent-param-key">memory_prompt_recent_limit</code>
                      </span>
                      <span className="agent-field-help">
                        セッション開始時にシステムプロンプトへ自動注入する記憶の上限（1〜5 件）
                      </span>
                    </label>
                    <input
                      id="harness-recent-limit"
                      type="number"
                      name="memory_prompt_recent_limit"
                      min="1"
                      max="5"
                      defaultValue={settings.harness.memory_prompt_recent_limit}
                      required
                    />
                  </div>

                  <div className="agent-subbox">
                    <h3>
                      <Mic size={16} /> 音声モデル設定（STT / TTS）
                    </h3>
                    <p className="agent-field-help">
                      音声モードを使う場合は 3 項目すべてを入力してください。テキスト専用で動かす場合は 3 項目すべてを空欄にします。
                    </p>
                    <div className="agent-field-grid agent-field-grid-3">
                      <div className="agent-field">
                        <label htmlFor="harness-stt">
                          <span className="agent-field-title">
                            音声認識 <code className="agent-param-key">stt_model</code>
                          </span>
                        </label>
                        <input
                          id="harness-stt"
                          name="stt_model"
                          maxLength={150}
                          defaultValue={settings.harness.stt_model}
                          placeholder="例: deepgram/nova-3"
                        />
                      </div>
                      <div className="agent-field">
                        <label htmlFor="harness-tts">
                          <span className="agent-field-title">
                            音声合成 <code className="agent-param-key">tts_model</code>
                          </span>
                        </label>
                        <input
                          id="harness-tts"
                          name="tts_model"
                          maxLength={150}
                          defaultValue={settings.harness.tts_model}
                          placeholder="例: cartesia/sonic-3"
                        />
                      </div>
                      <div className="agent-field">
                        <label htmlFor="harness-voice">
                          <span className="agent-field-title">
                            声 ID <code className="agent-param-key">tts_voice</code>
                          </span>
                        </label>
                        <input
                          id="harness-voice"
                          name="tts_voice"
                          maxLength={150}
                          defaultValue={settings.harness.tts_voice}
                          placeholder="例: voice-id"
                        />
                      </div>
                    </div>
                  </div>

                  <p className="agent-callout-note">
                    <ShieldCheck size={16} />
                    <span>API キーや OAuth 認証情報はセキュリティのため、画面ではなくサーバー側の環境変数（.env）で管理します。</span>
                  </p>
                  {saveBar}
                </form>
              </section>
            )}
          </div>

          {/* 右カラム：実測データ・DB 状況（LLM / メモリのみ表示。style.css の aside サイドバー規則を避けるため div を使用） */}
          {(section === "LLM" || section === "メモリ") && (
            <div className="agent-side-stack">
              {section === "LLM" && (
                <section className="card panel agent-panel">
                  <div className="panel-heading">
                    <h2>モデル実測比較</h2>
                    <span className="agent-badge-subtle">Langfuse 過去365日</span>
                  </div>
                  <p className="agent-panel-lead">
                    これまでの実会話トレースから集計した平均値です。モデル選びの参考にしてください。
                  </p>
                  {comparisons ? (
                    <div className="table-wrap agent-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th scope="col">モデル</th>
                            <th scope="col">回数</th>
                            <th scope="col">評価</th>
                            <th scope="col">平均時間</th>
                            <th scope="col">出力コスト</th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparisons.map((row) => {
                            const isCurrent = row.model === settings.model;
                            return (
                              <tr key={row.model} className={isCurrent ? "agent-row-active" : undefined}>
                                <td>
                                  <span className="agent-model-cell">
                                    {row.model.split("/")[1] || row.model}
                                    {isCurrent && <span className="agent-active">使用中</span>}
                                  </span>
                                </td>
                                <td>{row.count}</td>
                                <td>{row.score?.toFixed(2) ?? "N/A"}</td>
                                <td>{row.latency == null ? "N/A" : `${row.latency.toFixed(2)} 秒`}</td>
                                <td>{row.cost == null ? "N/A" : `$${row.cost.toFixed(5)}`}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="agent-empty-note">Langfuse の比較データを取得できません。</p>
                  )}
                  <p className="agent-side-caption">
                    評価はトレースに紐づく DeepEval の平均、出力コストは計測済み応答の平均です（評価条件・セッション数はモデルごとに異なります）。
                  </p>
                </section>
              )}

              {section === "メモリ" && (
                <section className="card panel agent-panel">
                  <div className="panel-heading">
                    <h2>PostgreSQL メモリ状況</h2>
                    <span className={memory ? "agent-active" : "agent-badge-muted"}>
                      {memory ? "DB 接続済み" : "未接続"}
                    </span>
                  </div>
                  {memory ? (
                    <>
                      <div className="table-wrap agent-table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th scope="col">テーブル</th>
                              <th scope="col" className="agent-num-col">件数</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(memory.counts).map(([name, count]) => (
                              <tr key={name}>
                                <td><code>{name}</code></td>
                                <td className="agent-num-col">{count.toLocaleString("ja-JP")} 件</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <h3 className="agent-subheading">最近の更新履歴</h3>
                      {memory.history.length ? (
                        <ul className="agent-memory-history">
                          {memory.history.map((item, i) => (
                            <li key={i}>
                              <span className="agent-badge-subtle">{item.action}</span>
                              <time>
                                {new Intl.DateTimeFormat("ja-JP", {
                                  dateStyle: "short",
                                  timeStyle: "short",
                                  timeZone: "Asia/Tokyo",
                                }).format(new Date(item.created_at))}{" "}
                                JST
                              </time>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="agent-empty-note">まだ更新履歴はありません。</p>
                      )}
                    </>
                  ) : (
                    <p className="agent-empty-note">
                      PostgreSQL のメモリ情報を取得できません。DB の起動状態と <code>DATABASE_URL</code> を確認してください。
                    </p>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
