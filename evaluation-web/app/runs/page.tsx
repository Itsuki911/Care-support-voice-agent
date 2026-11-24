import Link from "next/link";
import { Clock3, Search } from "lucide-react";
import { runs } from "../evaluations/demo-runs";
import { safetyRuns } from "../safety/demo-safety";
import { formatUsd } from "../format-usd";
import Sidebar from "../sidebar";
import "../observation-list.css";

export const metadata = { title: "実行履歴 | Voice Agent Lab" };

const entries = [
  ...runs.map((run) => ({
    id: run.id, kind: "通常評価", target: run.target, version: run.version,
    time: run.time, timeType: "登録", status: run.status, seconds: run.seconds, cost: run.cost,
    href: `/evaluations?q=${encodeURIComponent(run.id)}`,
  })),
  ...safetyRuns.map((run) => ({
    id: run.id, kind: "安全性評価", target: run.dataset, version: run.config,
    time: run.started, timeType: "開始", status: run.result ? "完了" : "実行失敗",
    seconds: run.seconds, cost: run.cost, href: `/safety/history?q=${encodeURIComponent(run.id)}`,
  })),
].sort((a, b) => b.time.localeCompare(a.time) || a.id.localeCompare(b.id));
const kinds = ["通常評価", "安全性評価"];
const states = ["待機中", "実行中", "完了", "実行失敗"];
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function RunsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const kind = kinds.find((option) => option === params.kind) ?? "";
  const status = states.find((option) => option === params.status) ?? "";
  const rows = entries.filter((run) =>
    (!kind || run.kind === kind) && (!status || run.status === status) &&
    [run.id, run.target].some((value) => value.toLowerCase().includes(term))
  );

  return <div className="shell">
    <Sidebar section="runs" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Clock3 size={27} /></span><div>
          <h1>実行履歴</h1><p>通常評価と安全性評価の Run を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, kind, status])} action="/runs" className="observation-filters">
            <label>Run ID・対象 ID<input name="q" type="search" placeholder="eval_demo_… / safety_demo_…" defaultValue={query} /></label>
            <label>種別<select name="kind" defaultValue={kind}><option value="">すべて</option>{kinds.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>実行状態<select name="status" defaultValue={status}><option value="">すべて</option>{states.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/runs">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>Run 一覧</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致する Run がありません。</p> :
            <div className="table-wrap"><table aria-label="評価の実行履歴">
              <thead><tr>{["Run ID", "種別", "対象 ID", "設定版", "日時（JST）", "実行状態", "所要時間", "コスト（USD）"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map((run) => <tr key={run.id}>
                <td><Link href={run.href}>{run.id}</Link></td><td>{run.kind}</td><td>{run.target}</td><td>{run.version}</td>
                <td>{run.time} <small>（{run.timeType}）</small></td>
                <td><span className="status" data-evaluation={run.status === "完了" ? "評価完了" : run.status === "実行失敗" ? "評価失敗" : undefined}>{run.status}</span></td>
                <td>{run.seconds === null ? "N/A" : `${run.seconds.toFixed(2)} s`}</td><td>{formatUsd(run.cost)}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
