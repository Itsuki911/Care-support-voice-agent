"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft, BarChart3, Bot, CalendarDays, Check, ClipboardList, Copy, Database,
  GitBranch, MessageCircle, Settings, Shield, UserRound, VolumeX, Wrench,
} from "lucide-react";
import { session } from "../demo-session";
import { demoTraceId } from "../../traces/demo-trace";

const views = [
  { label: "会話", icon: MessageCircle },
  { label: "トレース", icon: GitBranch },
  { label: "評価結果", icon: BarChart3 },
  { label: "ツール実行", icon: Wrench },
  { label: "設定", icon: Settings },
  { label: "関連データ", icon: Database },
] as const;

const metadata = [
  ["セッションID", session.id],
  ["開始日時", session.startedAt],
  ["継続時間", session.duration],
  ["使用LLM", session.model],
  ["Agent設定", session.agentConfig],
  ["評価設定", session.evaluatorConfig],
  ["アプリケーション", session.application],
] as const;

function EvaluationSummary() {
  return (
    <section className="card session-card">
      <div className="session-card-heading"><h2>評価サマリー</h2><span className="session-pill">総合スコア {session.score.toFixed(2)}</span></div>
      <ul className="session-metrics">
        {session.metrics.map(({ name, score }) => <li key={name}>
          <span>{name}</span>
          {score === null ? <span /> : <progress aria-label={name} value={score} max={1} />}
          <strong>{score?.toFixed(2) ?? "N/A"}</strong>
        </li>)}
      </ul>
      <p className="session-muted">音声指標は録音データがないため N/A です。</p>
    </section>
  );
}

function ToolExecutions() {
  return (
    <section className="card session-card">
      <h2><Wrench size={19} /> ツール実行（{session.tools.length}回）</h2>
      <div className="session-tools">{session.tools.map(({ name, time, description }) => (
        <details key={name}><summary><Check size={17} /><strong>{name}</strong><time>{time}</time></summary><p>{description}</p></details>
      ))}</div>
    </section>
  );
}

export default function SessionView() {
  const [view, setView] = useState<(typeof views)[number]["label"]>("会話");
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [showAudioStatus, setShowAudioStatus] = useState(true);
  const [annotationView, setAnnotationView] = useState<"コメント" | "ラベル">("コメント");
  const [draft, setDraft] = useState("");
  const [comments, setComments] = useState<string[]>([]);
  const [copyStatus, setCopyStatus] = useState("");

  async function copyId() {
    try {
      await navigator.clipboard.writeText(session.id);
      setCopyStatus("コピーしました");
    } catch {
      setCopyStatus("コピーできませんでした");
    }
  }

  return (
    <main className="session-main">
      <header className="session-header">
        <Link href="/" className="session-back"><ArrowLeft size={16} /> ダッシュボード</Link>
        <div className="session-title">
          <span className="icon purple"><Shield size={26} /></span>
          <div>
            <div className="session-title-row"><h1>{session.id}</h1><span className="session-pill"><Check size={15} /> 評価完了</span></div>
            <div className="session-meta">
              <span><CalendarDays size={16} /> {session.startedAt}（{session.duration}）</span>
              <span><Database size={16} /> Agent設定 {session.agentConfig}</span>
              <span><BarChart3 size={16} /> 評価設定 {session.evaluatorConfig}</span>
            </div>
          </div>
          <span className="session-demo">モックデータ</span>
        </div>
      </header>
      <nav className="session-tabs" aria-label="セッションの表示項目">
        {views.map(({ label, icon: Icon }) => <button key={label} type="button" aria-pressed={view === label} onClick={() => setView(label)}><Icon size={18} />{label}</button>)}
      </nav>
      <div className="session-grid">
        {view === "会話" && <>
          <section className="card session-card conversation">
            <div className="session-card-heading">
              <h2>会話ログ</h2>
              <div className="conversation-options">
                <label>表示 <select value={showAudioStatus ? "audio" : "text"} onChange={(event) => setShowAudioStatus(event.target.value === "audio")}><option value="audio">音声＋テキスト</option><option value="text">テキストのみ</option></select></label>
                <label><input type="checkbox" checked={showTimestamps} onChange={(event) => setShowTimestamps(event.target.checked)} /> タイムスタンプ表示</label>
              </div>
            </div>
            <ol className="conversation-turns">
              {session.turns.map(({ time, speaker, text }) => {
                const isAgent = speaker === "エージェント";
                return <li key={time} className={isAgent ? "agent-turn" : undefined}>
                  {showTimestamps && <time>{time}</time>}
                  <span className="speaker-icon">{isAgent ? <Bot size={21} /> : <UserRound size={21} />}</span>
                  <div><strong>{speaker}</strong><p className="speech">{text}</p>
                  {showAudioStatus && <p className="audio-unavailable"><VolumeX size={15} /> 音声データなし</p>}</div>
                </li>;
              })}
            </ol>
          </section>
          <div className="session-stack">
            <EvaluationSummary />
            <section className="card session-card">
              <div className="session-card-heading"><h2><Shield size={19} /> 安全性ステータス</h2><span className="status">未実施</span></div>
              <p className="session-muted">このセッションの安全性検証結果はありません。</p>
            </section>
            <ToolExecutions />
          </div>
        </>}
        {view === "評価結果" && <div className="session-wide"><EvaluationSummary /></div>}
        {view === "ツール実行" && <div className="session-wide"><ToolExecutions /></div>}
        {view === "設定" && <section className="card session-card session-wide">
          <h2>実行時設定</h2><dl className="session-fields">{metadata.slice(3, 6).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
          <p className="session-muted">設定の詳細スナップショットは未取得です。</p>
        </section>}
        {view === "トレース" && <section className="card session-card session-wide"><h2>トレース</h2><p className="session-muted"><Link href={`/traces/${demoTraceId}`}>{demoTraceId} の詳細を開く</Link></p></section>}
        {view === "関連データ" && <section className="card session-card session-wide"><h2>{view}</h2><p className="session-muted">このモックに表示できる{view}はありません。</p></section>}
        <div className="session-stack">
          <section className="card session-card">
            <h2>セッション詳細</h2>
            <dl className="session-fields">
              {metadata.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}
                {key === "セッションID" && <button type="button" className="copy-id" aria-label="セッションIDをコピー" onClick={copyId}><Copy size={15} /></button>}
              </dd></div>)}
              <div><dt>タグ</dt><dd className="session-labels">{session.labels.map((label) => <span key={label}>{label}</span>)}</dd></div>
            </dl>
            <p role="status" className="session-muted">{copyStatus}</p>
          </section>
          <section className="card session-card">
            <h2><ClipboardList size={19} /> アノテーション</h2>
            <div className="session-tabs annotation-tabs" role="group" aria-label="アノテーションの表示項目">
              {(["コメント", "ラベル"] as const).map((label) => <button key={label} type="button" aria-pressed={annotationView === label} onClick={() => setAnnotationView(label)}>{label}</button>)}
            </div>
            {annotationView === "コメント" ? <>
              <form className="session-comment-form" onSubmit={(event) => {
                event.preventDefault();
                const comment = draft.trim();
                if (!comment) return;
                setComments((previous) => [comment, ...previous]);
                setDraft("");
              }}>
                <textarea aria-label="コメント" placeholder="このセッションに関するコメントを入力…" maxLength={500} value={draft} onChange={(event) => setDraft(event.target.value)} />
                <div><span>{draft.length} / 500</span><button disabled={!draft.trim()} type="submit">追加</button></div>
              </form>
              <p className="session-muted">追加したコメントは再読み込みすると消えます。</p>
              <ul className="session-comments" aria-live="polite">
                {comments.map((comment, index) => <li key={comments.length - index}><strong>自分</strong><p>{comment}</p></li>)}
                <li><strong>評価者A</strong><time>2025/01/21 15:02 JST</time><p>受付時間と予約が必要な条件が明確です。曜日ごとの例外も案内できるとさらに分かりやすくなります。</p></li>
              </ul>
            </> : <div className="session-labels">{session.labels.map((label) => <span key={label}>{label}</span>)}</div>}
          </section>
        </div>
      </div>
    </main>
  );
}
