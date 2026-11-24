"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Box, Check, ChevronDown, ChevronLeft, ChevronRight, Clock3, Coins, Database, Layers3, Search, Shield } from "lucide-react";
import { formatUsd } from "../../format-usd";
import { session } from "../../sessions/demo-session";
import { demoTraceId, relatedSessionId, root, spans, traceCostSubtotal, unmeasuredLeafCount, type Span } from "../demo-trace";

const sections = ["概要", "入力 / 出力", "ツール呼び出し", "メタデータ", "評価・注釈"] as const;

function SpanDetail({ span, move, index }: { span: Span; move: (index: number) => void; index: number }) {
  const [section, setSection] = useState<(typeof sections)[number]>("概要");
  const llm = span.id === "llm1" || span.id === "llm2";
  const fields = [
    ["開始時刻", `2025/01/21 ${span.start} JST`], ["所要時間", `${span.duration.toFixed(2)} s`],
    ["ステータス", "完了"], ["モデル", llm ? session.model : "N/A"],
    ["トークン数", span.tokens?.toLocaleString("ja-JP") ?? "N/A"], ["推定コスト", formatUsd(span.cost)],
  ];

  return <section className="card trace-panel" aria-label="選択したスパン">
    <div className="trace-detail-head">
      <div><h2>{span.name}</h2><p>{span.description}</p></div>
      <div className="trace-pager">
        <button type="button" aria-label="前のスパン" disabled={index === 0} onClick={() => move(index - 1)}><ChevronLeft size={16} /></button>
        <span>{index + 1} / {spans.length}</span>
        <button type="button" aria-label="次のスパン" disabled={index === spans.length - 1} onClick={() => move(index + 1)}><ChevronRight size={16} /></button>
      </div>
    </div>
    <div className="trace-tabs" role="group" aria-label="スパン詳細の表示項目">
      {sections.map((label) => <button type="button" key={label} aria-pressed={section === label} onClick={() => setSection(label)}>{label}</button>)}
    </div>
    {section === "概要" && <div className="trace-block"><h3>基本情報</h3>
      <dl>{fields.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
    </div>}
    {(section === "概要" || section === "入力 / 出力") && <>
      <div className="trace-block"><h3>入力</h3><p className="trace-value">{llm ? session.turns[0].text : "入力データなし"}</p></div>
      <div className="trace-block"><h3>出力</h3><p className="trace-value">{span.id === "llm2" ? session.turns[1].text : "出力データなし"}</p></div>
    </>}
    {(section === "概要" || section === "ツール呼び出し") && <div className="trace-block"><h3>ツール呼び出し</h3>
      {span.id === "llm1" ? <button className="trace-tool" type="button" onClick={() => move(spans.findIndex(({ span }) => span.id === "tool"))}>search_knowledge <ChevronRight size={16} /></button> : <p>関連するツール呼び出しはありません。</p>}
    </div>}
    {section === "メタデータ" && <div className="trace-block"><h3>メタデータ</h3><dl><div><dt>Span ID</dt><dd>{span.id}</dd></div><div><dt>Agent設定</dt><dd>{session.agentConfig}</dd></div><div><dt>データの出典</dt><dd>合成データ</dd></div></dl></div>}
    {(section === "概要" || section === "評価・注釈") && <div className="trace-block"><h3>安全性・アノテーション</h3><p>このスパンの安全性評価は未実施です。</p><Link href={`/sessions/${relatedSessionId}`}>セッションの評価・注釈を開く</Link></div>}
  </section>;
}

export default function TraceView() {
  const [selected, setSelected] = useState(3);
  const [closed, setClosed] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [knownCostOnly, setKnownCostOnly] = useState(false);
  const term = query.trim().toLowerCase();
  const searching = Boolean(term || knownCostOnly);
  const showTree = (span: Span, depth = 0): { span: Span; depth: number }[] => [
    { span, depth }, ...(closed.includes(span.id) ? [] : (span.children ?? []).flatMap((child) => showTree(child, depth + 1))),
  ];
  const rows = searching ? spans.filter(({ span }) =>
    `${span.name} ${span.description} ${span.id}`.toLowerCase().includes(term) && (!knownCostOnly || span.cost !== null)
  ).map(({ span }) => ({ span, depth: 0 })) : showTree(root);

  const metrics = [
    { icon: Clock3, label: "合計実行時間", value: `${root.duration.toFixed(2)} s` },
    { icon: Layers3, label: "スパン数", value: spans.length },
    { icon: Database, label: "トークン数（合計）", value: root.tokens?.toLocaleString("ja-JP") },
    { icon: Coins, label: "推定コスト（小計）", value: formatUsd(traceCostSubtotal) },
    { icon: Shield, label: "安全性", value: "未実施" },
  ];

  return <main className="trace-main">
    <header className="trace-header">
      <div>
        <Link href="/traces" className="trace-back"><ArrowLeft size={16} /> トレース一覧</Link>
        <div className="trace-title"><h1>Trace: {demoTraceId}</h1><span className="trace-done"><Check size={15} /> 完了</span></div>
        <p>{session.startedAt} ・ Voice Agent ・ Agent Config {session.agentConfig} ・ {session.model}</p>
      </div>
      <span className="trace-demo">モックデータ</span>
    </header>
    <nav className="trace-nav" aria-label="関連画面"><span aria-current="page">トレース</span><Link href={`/sessions/${relatedSessionId}`}>関連セッション</Link></nav>
    <div className="trace-grid">
      <div className="trace-left">
        <section className="trace-metrics" aria-label="トレースの主要指標">{metrics.map(({ icon: Icon, label, value }) =>
          <article className="card trace-metric" key={label}><Icon size={21} /><div><h2>{label}</h2><strong>{value}</strong></div></article>
        )}</section>
        <section className="card trace-panel">
          <div className="trace-controls">
            <label className="trace-search"><Search size={17} /><input type="search" aria-label="スパンを検索" placeholder="スパン名・説明・IDで検索" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <label className="trace-filter"><input type="checkbox" checked={knownCostOnly} onChange={(event) => setKnownCostOnly(event.target.checked)} /> コスト計測済み</label>
            <button type="button" disabled={searching || closed.length === 0} onClick={() => setClosed([])}>すべて展開</button>
          </div>
          <p className="trace-help">コストは末端スパンの計測値を合算（未計測 {unmeasuredLeafCount}件）。時刻は JST。</p>
          <div className="table-wrap"><table className="trace-table">
            <thead><tr>{["スパン / 処理", "開始時刻", "所要時間", "トークン", "コスト ($)", "状態"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{rows.map(({ span, depth }) => <tr key={span.id} className={spans[selected].span.id === span.id ? "trace-selected" : undefined}>
              <td><div className="trace-span" style={{ paddingInlineStart: depth * 16 }}>
                {!searching && span.children ? <button type="button" className="trace-disclosure" aria-label={`${span.name} の子スパン`} aria-expanded={!closed.includes(span.id)} onClick={() => setClosed((previous) => previous.includes(span.id) ? previous.filter((id) => id !== span.id) : [...previous, span.id])}>
                  {closed.includes(span.id) ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                </button> : <Box size={16} />}
                <button type="button" className="trace-select" aria-pressed={spans[selected].span.id === span.id} onClick={() => setSelected(spans.findIndex((row) => row.span.id === span.id))}>
                  <strong>{span.name}</strong><span>{span.description}</span>
                </button>
              </div></td>
              <td>{span.start}</td><td>{span.duration.toFixed(2)} s</td><td>{span.tokens?.toLocaleString("ja-JP") ?? "N/A"}</td><td>{formatUsd(span.cost)}</td><td><span className="trace-done"><Check size={13} /> 完了</span></td>
            </tr>)}
            {rows.length === 0 && <tr><td colSpan={6}>条件に一致するスパンはありません。</td></tr>}</tbody>
          </table></div>
        </section>
      </div>
      <SpanDetail span={spans[selected].span} index={selected} move={setSelected} />
    </div>
  </main>;
}
