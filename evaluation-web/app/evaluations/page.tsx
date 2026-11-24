import Link from "next/link";
import { BarChart3, CheckCircle2, CircleAlert, Clock3, Search } from "lucide-react";
import Sidebar from "../sidebar";
import { session } from "../sessions/demo-session";
import { demoTraceId } from "../traces/demo-trace";
import "../observation-list.css";
import "./evaluations.css";

export const metadata = { title: "評価結果一覧 | Voice Agent Lab" };

const runs = [
  { id: "eval_demo_004", target: session.id, kind: "セッション", trigger: "自動", version: session.evaluatorConfig, time: "2025/01/21 14:40", status: "完了", score: session.score },
  { id: "eval_demo_003", target: demoTraceId, kind: "トレース", trigger: "手動", version: session.evaluatorConfig, time: "2025/01/21 14:35", status: "実行中", score: null },
  { id: "eval_demo_002", target: "dataset_demo_voice_v2", kind: "データセット", trigger: "手動", version: "v4", time: "2025/01/21 10:15", status: "待機中", score: null },
  { id: "eval_demo_001", target: "sess_demo_voice", kind: "セッション", trigger: "自動", version: "v4", time: "2025/01/20 09:22", status: "実行失敗", score: null },
];
const states = ["完了", "実行中", "待機中", "実行失敗"];
const kinds = ["セッション", "トレース", "データセット"];
const versions = [...new Set(runs.map((run) => run.version))];
const counters = [
  { label: "完了", icon: CheckCircle2, color: "green" },
  { label: "実行中・待機中", icon: Clock3, color: "blue" },
  { label: "実行失敗", icon: CircleAlert, color: "purple" },
].map((counter, index) => ({ ...counter, count: runs.filter((run) =>
  index === 1 ? run.status === "実行中" || run.status === "待機中" : run.status === counter.label
).length }));

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function EvaluationsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const status = states.find((value) => value === params.status) ?? "";
  const kind = kinds.find((value) => value === params.kind) ?? "";
  const version = versions.find((value) => value === params.version) ?? "";
  const matching = runs.filter((run) =>
    (!term || run.id.toLowerCase().includes(term) || run.target.toLowerCase().includes(term)) &&
    (!status || run.status === status) && (!kind || run.kind === kind) && (!version || run.version === version)
  );

  return <div className="shell">
    <Sidebar section="evaluations" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><BarChart3 size={26} /></span><div>
          <h1>評価結果一覧</h1><p>通常評価の実行状況と結果を Run 単位で確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="evaluation-counters" aria-label="サンプル全体の Run 件数">
          {counters.map(({ icon: Icon, label, count, color }) => <article className="card evaluation-counter" key={label}>
            <span className={`icon ${color}`}><Icon size={22} /></span><div><h2>{label}</h2><strong>{count} 件</strong></div>
          </article>)}
        </section>
        <section className="card panel">
          <h2>検索条件</h2>
          <form action="/evaluations" className="observation-filters">
            <label>Run ID・対象ID<input name="q" type="search" placeholder="eval_demo_…" defaultValue={query} /></label>
            <label>状態<select name="status" defaultValue={status}><option value="">すべて</option>{states.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>対象種別<select name="kind" defaultValue={kind}><option value="">すべて</option>{kinds.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>評価設定<select name="version" defaultValue={version}><option value="">すべて</option>{versions.map((value) => <option key={value}>{value}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/evaluations">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>評価 Run</h2><span>{matching.length} 件</span></div>
          {matching.length === 0 ? <p className="observation-list-empty">一致する評価 Run がありません。</p> :
            <div className="table-wrap"><table aria-label="評価 Run 検索結果">
              <thead><tr>{["Run ID", "対象", "開始方式", "評価設定", "登録日時（JST）", "状態", "スコア", "結果"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{matching.map((run) => {
                const targetHref = run.target === session.id ? `/sessions/${session.id}` : run.target === demoTraceId ? `/traces/${demoTraceId}` : null;
                return <tr key={run.id}>
                  <th scope="row" className="evaluation-run-id">{run.id}</th>
                  <td><small className="evaluation-kind">{run.kind}</small>{targetHref ? <Link href={targetHref}>{run.target}</Link> : run.target}</td>
                  <td>{run.trigger}</td><td>{run.version}</td><td>{run.time}</td>
                  <td><span className="status" data-run-status={run.status}>{run.status}</span></td>
                  <td>{run.score?.toFixed(2) ?? "N/A"}</td>
                  <td>{run.target === session.id ? <Link href={`/sessions/${session.id}?tab=evaluation`}>評価サマリー</Link> : "—"}</td>
                </tr>;
              })}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
