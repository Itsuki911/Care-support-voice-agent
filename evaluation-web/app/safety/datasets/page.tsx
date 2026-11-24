import Link from "next/link";
import { Database, Search } from "lucide-react";
import Sidebar from "../../sidebar";
import { safetyRuns } from "../demo-safety";
import "../../observation-list.css";
import "../safety.css";

export const metadata = { title: "安全性評価のデータセット | Voice Agent Lab" };

const datasets = [
  { id: "safety_demo_v3", version: "v3", state: "公開済み", cases: 200, date: "2025/01/21", categories: "出力の取り扱い・承認フロー・回答品質", description: "施設案内の回答と操作確認に関する合成ケースを追加した版です。" },
  { id: "safety_demo_v2", version: "v2", state: "アーカイブ", cases: 150, date: "2025/01/20", categories: "回答品質・説明の明確さ", description: "施設案内の基本回答を確認する合成ケースの版です。" },
];
const states = ["公開済み", "アーカイブ"];
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SafetyDatasetsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const state = states.find((option) => option === params.state) ?? "";
  const rows = datasets.filter((dataset) =>
    (!state || dataset.state === state) &&
    [dataset.id, dataset.categories].some((value) => value.toLowerCase().includes(term))
  );

  return <div className="shell">
    <Sidebar section="safety" />
    <main className="observation-list safety-page">
      <header>
        <div className="heading"><span className="home"><Database size={27} /></span><div>
          <h1>安全性評価のデータセット</h1><p>評価に使う合成データの版と利用履歴を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <nav aria-label="安全性評価"><Link href="/safety">← 安全性評価の概要</Link></nav>
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, state])} action="/safety/datasets" className="observation-filters">
            <label>データセット ID・カテゴリ<input type="search" name="q" placeholder="safety_demo_…" defaultValue={query} /></label>
            <label>状態<select name="state" defaultValue={state}><option value="">すべて</option>{states.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/safety/datasets">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>データセット版</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致するデータセットがありません。</p> :
            <div className="table-wrap"><table aria-label="安全性評価のデータセット版">
              <thead><tr>{["データセット ID", "版", "状態", "ケース数", "更新日（JST）", "関連 Run"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map(({ id, version, state, cases, date, categories, description }) => {
                const runCount = safetyRuns.filter((run) => run.dataset === id).length;
                return <tr key={id}>
                  <td><details className="safety-history-breakdown"><summary>{id}</summary>
                    <p className="safety-caption">{description}</p>
                    <p className="safety-caption">カテゴリ · {categories}</p>
                  </details></td>
                  <td>{version}</td><td><span className={`status ${state === "公開済み" ? "safety-done" : ""}`}>{state}</span></td>
                  <td>{cases} 件</td><td>{date}</td>
                  <td><Link href={`/safety/history?dataset=${encodeURIComponent(id)}`}>{runCount} 件の履歴</Link></td>
                </tr>;
              })}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
