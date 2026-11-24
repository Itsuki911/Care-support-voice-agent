"use client";

import { useState } from "react";
import {
  AudioLines, BarChart3, CalendarDays, Clock3, Database, FileText, House,
  MessageCircle, Play, Settings, Shield, SlidersHorizontal, Tag, TrendingUp,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { findings, sessions, trend } from "./demo-data";

const groups = [
  { label: "観測・分析", items: [[MessageCircle, "セッション"], [TrendingUp, "トレース"], [BarChart3, "評価結果"]] },
  { label: "安全性評価", items: [[Shield, "Safety Evaluation"]] },
  { label: "設定管理", items: [[SlidersHorizontal, "Agent設定"], [FileText, "評価設定（DeepEval）"], [Shield, "安全性設定"]] },
  { label: "データ管理", items: [[Database, "データセット"]] },
  { label: "その他", items: [[Tag, "アノテーション"], [Clock3, "実行履歴"]] },
] as const;

const metrics = [
  { icon: MessageCircle, label: "セッション数", value: "1,248", change: "+12.4%", color: "blue" },
  { icon: BarChart3, label: "評価平均スコア", detail: "DeepEval · 同一評価設定", value: "0.86", change: "+0.03", color: "green" },
  { icon: Shield, label: "安全性テスト合格率", detail: "独立テスト · 500件", value: "94.2%", change: "+2.1pt", color: "purple" },
  { icon: Database, label: "推定コスト（LLM）", value: "$142.68", change: "−8.7%", color: "blue" },
] as const;

const tabs = ["概要", "通常評価", "安全性評価", "利用状況", "最近の変更"] as const;
const actions = [
  { icon: Play, title: "Safety Evaluationを実行", detail: "Inspect AI / garak / PyRIT", color: "purple" },
  { icon: Database, title: "データセットを管理", detail: "評価・安全性テスト", color: "blue" },
  { icon: SlidersHorizontal, title: "Agent設定を編集", detail: "プロンプト・LLM・ツール", color: "green" },
  { icon: FileText, title: "評価設定を編集", detail: "DeepEval・評価用LLM", color: "purple" },
];

export default function Dashboard() {
  const [tab, setTab] = useState<(typeof tabs)[number]>("概要");
  const overview = tab === "概要";
  const total = findings.reduce((sum, finding) => sum + finding.value, 0);

  return (
    <div className="shell">
      <aside>
        <div className="brand"><AudioLines size={42} /> <span>Voice Agent<br />Evaluation Platform</span></div>
        <nav aria-label="管理画面">
          <a className="current" href="/" aria-current="page"><House /> ダッシュボード</a>
          {groups.map(({ label, items }) => (
            <div className="nav-group" key={label}>
              <div className="nav-label">{label}</div>
              {items.map(([Icon, name]) => <div className="nav-item" key={name}><Icon />{name}</div>)}
            </div>
          ))}
        </nav>
        <div className="nav-footer"><Settings size={20} /> 設定</div>
      </aside>
      <main>
        <header>
          <div className="heading"><div className="home"><House size={30} /></div><div>
            <h1>ダッシュボード</h1>
            <p>音声Agentの観測・評価・安全性検証・設定管理</p>
          </div></div>
          <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
        </header>
        <div className="content">
          <div className="toolbar">
            <div className="tabs" role="group" aria-label="表示セクション">
              {tabs.map((name) => <button type="button" key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}
            </div>
            <div className="date"><CalendarDays size={19} /> 対象7日間　2025/01/15 – 2025/01/21 JST</div>
          </div>
          {(overview || tab === "利用状況") && <section className="metrics" aria-label="主要指標">
            {metrics.map(({ icon: Icon, label, value, change, color, ...rest }) => (
              <article className="card metric" key={label}>
                <div className={`icon ${color}`}><Icon size={26} /></div>
                <div><h2>{label}</h2>{"detail" in rest && <div className="detail">{rest.detail}</div>}
                <div className="metric-value">{value}</div><p><b>{change}</b>　<span>前週比</span></p></div>
              </article>
            ))}
          </section>}
          <div className="panels">
            {(overview || tab === "通常評価") && <section className="card panel">
              <h2>通常評価スコアの推移</h2>
              <div className="chart" role="img" aria-label="DeepEval の平均スコアは 0.83 から 0.864 に上昇">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 600, height: 220 }}>
                  <AreaChart data={trend} margin={{ top: 10, right: 18, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="#e4eaf2" />
                    <XAxis dataKey="day" axisLine={false} tickLine={false} tickMargin={10} />
                    <YAxis domain={[0.75, 1]} ticks={[0.75, 0.8, 0.85, 0.9, 0.95, 1]} tickFormatter={(value: number) => value.toFixed(2)} axisLine={false} tickLine={false} width={44} />
                    <Tooltip />
                    <Legend verticalAlign="top" align="right" />
                    <Area dataKey="quality" name="通常評価（DeepEval）" stroke="#2488fb" strokeWidth={3} fill="#dcecff" dot={{ r: 4, fill: "#fff" }} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>}
            {(overview || tab === "安全性評価") && <section className="card panel">
              <h2>安全性評価の結果</h2>
              <div className="safety">
                <div className="donut" role="img" aria-label={`${total}件中、${findings[0].value}件合格`}>
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 190, height: 190 }}>
                    <PieChart><Pie data={findings} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="96%" startAngle={90} endAngle={-270} isAnimationActive={false} /></PieChart>
                  </ResponsiveContainer>
                  <div className="donut-label"><strong>{total}</strong><span>テスト</span></div>
                </div>
                <ul className="findings">{findings.map(({ name, value, fill }) => <li key={name}>
                  <span className="dot" style={{ background: fill }} /><span>{name}</span>
                  <span>{(value / total * 100).toFixed(1)}%</span><span>({value})</span>
                </li>)}</ul>
              </div>
            </section>}
            {(overview || tab === "最近の変更") && <section className="card panel">
              <h2>最近のセッション</h2>
              <div className="table-wrap"><table><thead><tr>
                {["セッションID", "日時（JST）", "LLM", "評価スコア", "安全性"].map((label) => <th key={label} scope="col">{label}</th>)}
              </tr></thead><tbody>{sessions.map(({ id, time, model, score }) => <tr key={id}>
                <td>{id}</td><td>2025/01/21 {time}</td><td>{model}</td><td>{score.toFixed(2)}</td><td><span className="status">未実施</span></td>
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
