"use client";

import { useEffect, useState } from "react";
import { ArrowLeftRight, AudioLines, Bot, Check, Database, FileText, Layers3, Network, Plus, Rocket, RotateCcw, Save, Settings, Shield, Wrench, X } from "lucide-react";
import { active, basics, versions, type AgentBasics } from "./demo-settings";

const categories = [
  { title: "LLM", icon: Layers3, lines: ["gpt-4o", "Temperature 0.3 / 最大 4,096トークン"] },
  { title: "音声（STT / TTS）", icon: AudioLines, lines: ["STT: whisper-1", "TTS: gpt-4o-mini-tts"] },
  { title: "プロンプト", icon: FileText, lines: ["v12", "施設の受付時間と見学予約を案内します。"] },
  { title: "ツール", icon: Wrench, lines: ["3 / 4 有効", "外部操作には承認が必要"] },
  { title: "RAG", icon: Database, lines: ["施設案内 FAQ v3", "top-k: 5"] },
  { title: "メモリ", icon: Database, lines: ["ユーザー要約・利用履歴", "保持期間: 180日"] },
  { title: "ハーネス", icon: Network, lines: ["承認制御・安全制約・リトライ"] },
  { title: "安全ポリシー", icon: Shield, lines: ["基本ガードレール有効"] },
] as const;

const tabs = ["設定", "バージョン履歴", "比較", "実験（A/Bテスト）"] as const;

export default function AgentSettings() {
  const [tab, setTab] = useState<(typeof tabs)[number]>("設定");
  const [category, setCategory] = useState<string>("基本設定");
  const [savedDraft, setSavedDraft] = useState<AgentBasics>();
  const [draft, setDraft] = useState<AgentBasics>();
  const [tag, setTag] = useState("");
  const [message, setMessage] = useState("");
  const [source, setSource] = useState(versions[1].id);
  const [target, setTarget] = useState(active.id);
  const value = draft ?? savedDraft ?? active;
  const dirty = draft !== undefined && JSON.stringify(draft) !== JSON.stringify(savedDraft ?? basics(active));
  const selected = categories.find(({ title }) => title === category);
  const choices = savedDraft ? [...versions, { ...savedDraft, id: "draft" }] : versions;
  const from = choices.find(({ id }) => id === source) ?? active;
  const to = choices.find(({ id }) => id === target) ?? active;
  const differences = [
    ["設定名", from.name, to.name],
    ["説明", from.description, to.description],
    ["タグ", from.tags.join("、"), to.tags.join("、")],
  ].filter(([, before, after]) => before !== after);

  useEffect(() => {
    if (!dirty) return;
    function warn(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = true;
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function edit() {
    setTab("設定");
    setCategory("基本設定");
    setDraft((current) => current ?? savedDraft ?? basics(active));
    setMessage("");
  }

  function update(changes: Partial<AgentBasics>) {
    if (!draft) return;
    setDraft({ ...draft, ...changes });
    setMessage("");
  }

  function addTag() {
    const next = tag.trim();
    if (!draft || !next || draft.tags.includes(next)) return;
    update({ tags: [...draft.tags, next] });
    setTag("");
  }

  function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !draft.name.trim()) {
      setMessage("設定名を入力してください。");
      return;
    }
    if (tag.trim()) {
      setMessage("入力したタグを追加するか、タグ欄を空にしてください。");
      return;
    }
    setSavedDraft({ ...draft, name: draft.name.trim() });
    setDraft(undefined);
    setMessage("この画面にドラフトを保存しました。");
  }

  const history = <ul className="agent-history">{versions.map(({ id, date, author }) => <li key={id} className={id === active.id ? "agent-history-active" : undefined}>
    <strong>{id} {id === active.id && <span className="agent-active">アクティブ</span>}</strong>
    <time>{date} JST</time><span>{author}</span>
  </li>)}</ul>;

  return <main className="agent-main">
    <header className="agent-header">
      <div className="heading"><div className="home"><Bot size={29} /></div><div>
        <h1>Agent設定</h1><p>音声Agentの基本情報と構成を管理します。</p>
      </div></div>
      <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
    </header>
    <nav className="agent-tabs" aria-label="Agent設定の表示項目">{tabs.map((label) =>
      <button type="button" key={label} aria-pressed={tab === label} onClick={() => setTab(label)}>{label}</button>
    )}</nav>
    <div className="agent-grid">
      <div className="agent-stack">
        <section className="card agent-card">
          <div className="agent-card-head"><h2>設定バージョン</h2><span className="agent-active">アクティブ</span></div>
          <strong className="agent-version">{active.id}</strong>
          <p>Development に適用中</p>
          <dl className="agent-version-meta"><dt>最終更新</dt><dd>{active.date} JST</dd><dt>更新者</dt><dd>{active.author}</dd></dl>
          <button className="agent-button agent-full" type="button" onClick={edit}><Plus size={17} /> {savedDraft ? "ドラフトを編集" : "新しいドラフトを作成"}</button>
        </section>
        <nav className="card agent-card agent-categories" aria-label="設定カテゴリ">
          {[{ title: "基本設定", icon: Settings }, ...categories].map(({ title, icon: Icon }) =>
            <button key={title} type="button" aria-pressed={tab === "設定" && category === title} onClick={() => { setTab("設定"); setCategory(title); }}><Icon size={19} />{title}</button>
          )}
        </nav>
      </div>

      <div className="agent-stack">
        {tab === "設定" && !selected && <section className="card agent-card agent-editor">
          <div className="agent-card-head"><div><h2>基本設定</h2><p>Agentの名前、説明、タグを管理します。</p></div>
            {!draft && <button className="agent-button" type="button" onClick={edit}>{savedDraft ? "ドラフトを編集" : "アクティブ版から編集"}</button>}
          </div>
          <form onSubmit={save}>
            <div className="agent-fields">
              <label htmlFor="agent-name">設定名 <span aria-hidden="true">*</span></label>
              <input id="agent-name" required maxLength={100} readOnly={!draft} value={value.name} onChange={(event) => update({ name: event.target.value })} />
              <label htmlFor="agent-description">説明</label>
              <textarea id="agent-description" maxLength={1000} readOnly={!draft} value={value.description} onChange={(event) => update({ description: event.target.value })} />
              <span>タグ</span>
              <div className="agent-tags">{value.tags.map((text) => <span key={text}>{text}{draft && <button type="button" aria-label={`${text}を削除`} onClick={() => update({ tags: draft.tags.filter((item) => item !== text) })}><X size={13} /></button>}</span>)}
                {draft && <div className="agent-tag-input"><input aria-label="新しいタグ" maxLength={30} value={tag} onChange={(event) => setTag(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addTag(); } }} />
                  <button type="button" className="agent-button" onClick={addTag} disabled={!tag.trim() || draft.tags.includes(tag.trim())}><Plus size={15} /> 追加</button></div>}
              </div>
            </div>
            <div className="agent-structure">
              <h2>主要な構成（サマリー）</h2>
              <div className="agent-summary">{categories.map(({ title, icon: Icon, lines }) => <button key={title} type="button" onClick={() => setCategory(title)}>
                <span className="icon blue"><Icon size={22} /></span><span><strong>{title}</strong>{lines.map((line) => <span key={line}>{line}</span>)}</span>
              </button>)}</div>
            </div>
            <div className="agent-actions">
              <p role="status">{message || (draft ? "ドラフトを編集中です。" : savedDraft ? "ドラフトを表示中です。再読み込みすると消えます。" : "現在のアクティブ版を表示しています。")}</p>
              {draft && <>
                <button className="agent-button" type="button" onClick={() => { setDraft(savedDraft ?? basics(active)); setTag(""); setMessage("変更をリセットしました。"); }}><RotateCcw size={15} /> リセット</button>
                <button className="agent-button agent-primary" type="submit"><Save size={15} /> ドラフトとして保存</button>
              </>}
            </div>
          </form>
        </section>}
        {tab === "設定" && selected && <section className="card agent-card"><h2>{selected.title}</h2>
          <ul>{selected.lines.map((line) => <li key={line}>{line}</li>)}</ul>
          <button type="button" className="agent-button" onClick={() => setCategory("基本設定")}>基本設定に戻る</button>
        </section>}
        {tab === "バージョン履歴" && <section className="card agent-card"><h2>バージョン履歴</h2>{history}</section>}
        {tab === "比較" && <section className="card agent-card"><h2>設定の差分</h2><p>{source} → {target}</p>
          {differences.length === 0 ? <p>基本設定に差分はありません。</p> : <dl className="agent-diff">
            {differences.map(([label, before, after]) => <div key={label}><dt>{label}</dt><dd><del>{before || "（空）"}</del><ins>{after || "（空）"}</ins></dd></div>)}
          </dl>}
        </section>}
        {tab === "実験（A/Bテスト）" && <section className="card agent-card"><h2>実験（A/Bテスト）</h2><p>実験結果はありません。</p></section>}
      </div>

      <div className="agent-stack">
        <section className="card agent-card"><h2>設定の適用</h2>
          <div className="agent-apply"><Check size={16} /> 適用対象は新規セッションのみ</div>
          <button className="agent-button agent-full" type="button" disabled><Rocket size={17} /> アクティブに昇格</button>
          <p>モックのため、実行環境への適用はできません。</p>
        </section>
        <section className="card agent-card">
          <div className="agent-card-head"><h2>バージョン履歴</h2><button className="agent-link" type="button" onClick={() => setTab("バージョン履歴")}>すべて見る →</button></div>
          {history}
        </section>
        <section className="card agent-card">
          <h2>設定の比較</h2>
          <div className="agent-compare">
            <label>比較元<select value={source} onChange={(event) => setSource(event.target.value)}>{choices.map(({ id }) => <option key={id}>{id}</option>)}</select></label>
            <button type="button" className="agent-button" aria-label="比較元と比較先を入れ替える" onClick={() => { setSource(target); setTarget(source); }}><ArrowLeftRight size={17} /></button>
            <label>比較先<select value={target} onChange={(event) => setTarget(event.target.value)}>{choices.map(({ id }) => <option key={id}>{id}</option>)}</select></label>
          </div>
          <button className="agent-button agent-full" type="button" onClick={() => setTab("比較")}>差分を表示</button>
        </section>
      </div>
    </div>
  </main>;
}
