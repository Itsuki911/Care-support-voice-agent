import Link from "next/link";
import { Clock3, Search } from "lucide-react";
import { formatUsd } from "../../format-usd";
import Sidebar from "../../sidebar";
import { safetyRuns, severities } from "../demo-safety";
import "../../observation-list.css";
import "../safety.css";

export const metadata = { title: "安全性評価の実行履歴 | Voice Agent Lab" };

const frameworks = [...new Set(safetyRuns.map((run) => run.framework))];
const datasets = [...new Set(safetyRuns.map((run) => run.dataset))];
const states = ["完了", "実行失敗"];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SafetyHistoryPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const framework = frameworks.find((value) => value === params.framework) ?? "";
  const dataset = datasets.find((value) => value === params.dataset) ?? "";
  const state = states.find((value) => value === params.state) ?? "";
  const rows = safetyRuns.filter((run) =>
    run.id.toLowerCase().includes(query.toLowerCase()) &&
    (!framework || run.framework === framework) &&
    (!dataset || run.dataset === dataset) &&
    (!state || (run.result ? "完了" : "実行失敗") === state)
  );

  return <div className="shell">
    <Sidebar section="safety" />
    <main className="observation-list safety-page">
      <header>
        <div className="heading"><span className="home"><Clock3 size={27} /></span><div>
          <h1>安全性評価の実行履歴</h1><p>過去の Run の評価対象、判定結果、利用量を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <nav aria-label="安全性評価"><Link href="/safety">← 安全性評価の概要</Link></nav>
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, framework, dataset, state])} action="/safety/history" className="observation-filters">
            <label>Run ID<input type="search" name="q" placeholder="safety_demo_…" defaultValue={query} /></label>
            <label>フレームワーク<select name="framework" defaultValue={framework}><option value="">すべて</option>{frameworks.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>データセット版<select name="dataset" defaultValue={dataset}><option value="">すべて</option>{datasets.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>実行状態<select name="state" defaultValue={state}><option value="">すべて</option>{states.map((value) => <option key={value}>{value}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/safety/history">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>安全性評価 Run</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致する安全性評価 Run がありません。</p> :
            <div className="table-wrap"><table aria-label="安全性評価の実行履歴">
              <thead><tr>{["Run ID", "フレームワーク・対象", "設定・データセット版", "開始日時（JST）", "状態", "判定済み", "不合格", "所要時間", "コスト（USD）"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map(({ id, framework, target, config, dataset, started, result, seconds, cost }) => {
                const failed = result?.failed.reduce((sum, count) => sum + count, 0) ?? null;
                return <tr key={id}>
                  <td>{id}</td><td>{framework}<small className="safety-history-subtitle">{target}</small></td>
                  <td>{config}<small className="safety-history-subtitle">{dataset}</small></td><td>{started}</td>
                  <td><span className={`status ${result ? "safety-done" : "safety-failed"}`}>{result ? "完了" : "実行失敗"}</span></td>
                  <td>{result && failed !== null ? result.passed + failed : "N/A"}</td>
                  <td>{result ? <details className="safety-history-breakdown">
                    <summary aria-label={`${id} の不合格ケース内訳（${failed} 件）`}>{failed} 件</summary>
                    <dl>{severities.map(({ label }, index) => <div key={label}><dt>{label}</dt><dd>{result.failed[index]}</dd></div>)}</dl>
                  </details> : "N/A"}</td>
                  <td>{seconds === null ? "N/A" : `${seconds} s`}</td><td>{formatUsd(cost)}</td>
                </tr>;
              })}</tbody>
            </table></div>}
          <p className="safety-caption">実行失敗で判定が得られなかった Run は、ケース件数を N/A と表示します。</p>
        </section>
      </div>
    </main>
  </div>;
}
