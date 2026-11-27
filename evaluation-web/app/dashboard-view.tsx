"use client";

import Sidebar from "./sidebar";
import { useState } from "react";
import {
  BarChart3, CalendarDays, Database, FileText, House,
  MessageCircle, Play, Shield, SlidersHorizontal,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";


const tabs = ["概要", "通常評価", "安全性評価", "利用状況", "最近の変更"] as const;
const actions = [
  { icon: Play, title: "Safety Evaluationを実行", detail: "Inspect AI / garak / PyRIT", color: "purple" },
  { icon: Database, title: "データセットを管理", detail: "評価・安全性テスト", color: "blue" },
  { icon: SlidersHorizontal, title: "Agent設定を編集", detail: "プロンプト・LLM・ツール", color: "green" },
  { icon: FileText, title: "評価設定を編集", detail: "DeepEval・評価用LLM", color: "purple" },
];

type Data = Awaited<ReturnType<typeof import("./dashboard-data").getDashboard>>;

export default function DashboardView({ data }: { data: Data }) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("概要");
  const overview = tab === "概要";
  const dateKey = (value: string | number) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(new Date(value));
  const [from, setFrom] = useState(() => dateKey(data.start));
  const [to, setTo] = useState(() => dateKey(new Date(data.end).getTime() - 1));
  const [open, setOpen] = useState(false);
  const invalidRange = !from || !to || from > to || (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) >= 366 * 86400000;
  const metrics = [
    { icon: MessageCircle, label: "セッション数", value: data.connected ? String(data.count) : "N/A", detail: "期間内に観測されたセッション", color: "blue" },
    { icon: BarChart3, label: "評価平均スコア", value: data.average?.toFixed(2) ?? "N/A", detail: "DeepEval · 会話評価の平均", color: "green" },
    { icon: Shield, label: "安全性テスト合格率", value: "N/A", detail: "独立テスト · 未接続", color: "purple" },
    { icon: Database, label: "推定コスト（LLM）", value: data.cost == null ? "N/A" : `$${data.cost.toFixed(4)}`, detail: "計測済み生成コストの小計", color: "blue" },
  ];
  const date = (value: string) => new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", dateStyle: "short", timeStyle: "short" }).format(new Date(value));

  return (
    <div className="shell">
      <Sidebar section="dashboard" />
      <main>
        <header>
          <div className="heading"><div className="home"><House size={30} /></div><div>
            <h1>ダッシュボード</h1>
            <p>音声Agentの観測・評価・安全性検証・設定管理</p>
          </div></div>
          <div className="environment"><strong>観測データ</strong><span>{data.connected ? "Langfuse 接続済み" : "Langfuse 未接続"}</span></div>
        </header>
        <div className="content">
          <div className="toolbar">
            <div className="tabs" role="group" aria-label="表示セクション">
              {tabs.map((name) => <button type="button" key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}
            </div>
            <div className="date-picker">
              <button type="button" className="date" aria-expanded={open} aria-controls="dashboard-date-picker" onClick={() => setOpen(!open)}><CalendarDays size={19} /> {dateKey(data.start)} – {dateKey(new Date(data.end).getTime() - 1)} JST</button>
              {open && <form id="dashboard-date-picker" className="date-popover" action="/" method="get">
                <strong>表示期間（日本時間）</strong>
                <label>開始日<input type="date" name="from" required value={from} onChange={event => setFrom(event.target.value)} /></label>
                <label>終了日<input type="date" name="to" required value={to} onChange={event => setTo(event.target.value)} /></label>
                {invalidRange && <p role="alert">開始日から終了日までを366日以内で選択してください。</p>}
                <div className="date-actions"><button type="button" onClick={() => setOpen(false)}>キャンセル</button><button type="submit" disabled={invalidRange}>適用</button></div>
              </form>}
            </div>
          </div>
          {(overview || tab === "利用状況") && <section className="metrics" aria-label="主要指標">
            {metrics.map(({ icon: Icon, label, value, detail, color }) => (
              <article className="card metric" key={label}>
                <div className={`icon ${color}`}><Icon size={26} /></div>
                <div><h2>{label}</h2><div className="detail">{detail}</div>
                <div className="metric-value">{value}</div></div>
              </article>
            ))}
          </section>}
          <div className="panels">
            {(overview || tab === "通常評価") && <section className="card panel">
              <h2>通常評価スコアの推移</h2>
              {data.average == null ? <p>この期間に評価データはありません。</p> : <div className="chart" role="img" aria-label="DeepEval の日別平均スコア">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 600, height: 220 }}>
                  <AreaChart data={data.trend} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="#e4eaf2" />
                    <XAxis dataKey="day" axisLine={false} tickLine={false} tickMargin={10} />
                    <YAxis domain={[0, 1]} tickFormatter={(value: number) => value.toFixed(2)} axisLine={false} tickLine={false} width={44} />
                    <Tooltip />
                    <Legend verticalAlign="top" align="right" />
                    <Area dataKey="quality" name="通常評価（DeepEval）" stroke="#2488fb" strokeWidth={3} fill="#dcecff" dot={{ r: 4, fill: "#fff" }} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>}
            </section>}
            {(overview || tab === "安全性評価") && <section className="card panel">
              <h2>安全性評価の結果</h2>
              <p>安全性テストの実データは未接続です。</p>
            </section>}
            {(overview || tab === "最近の変更") && <section className="card panel">
              <div className="panel-heading"><h2>最近のセッション</h2></div>
              <div className="table-wrap"><table><thead><tr>
                {["セッションID", "日時（JST）", "LLM", "評価スコア", "安全性"].map((label) => <th key={label} scope="col">{label}</th>)}
              </tr></thead><tbody>{data.sessions.map(({ id, time, model, score }) => <tr key={id}>
                <td>{id}</td><td>{date(time)}</td><td>{model}</td><td>{score?.toFixed(2) ?? "N/A"}</td><td><span className="status">未取得</span></td>
              </tr>)}</tbody></table></div>
            </section>}
            {overview && <section className="card panel">
              <h2>クイックアクション <small>準備中</small></h2>
              <div className="actions">{actions.map(({ icon: Icon, title, detail, color }) =>
                <div className={`action ${color}`} key={title}><div className={`icon ${color}`}><Icon size={23} /></div>
                  <div><strong>{title}</strong><span>{detail}</span></div></div>
              )}</div>
            </section>}
          </div>
        </div>
      </main>
    </div>
  );
}
