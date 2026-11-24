import Link from "next/link";
import { CheckCircle2, CircleAlert, ClipboardList, Shield } from "lucide-react";
import Sidebar from "../sidebar";
import { safetyRuns, severities } from "./demo-safety";
import "../observation-list.css";
import "./safety.css";

export const metadata = { title: "安全性評価の概要 | Voice Agent Lab" };

const frameworks = [...new Set(safetyRuns.map((run) => run.framework))];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SafetyPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const framework = frameworks.find((option) => option === params.framework) ?? "";
  const runs = safetyRuns.filter((run) => !framework || run.framework === framework);
  const results = runs.flatMap(({ result }) => result ? [result] : []);
  const failedBySeverity = severities.map(({ label, color }, index) => ({
    label, color, count: results.reduce((sum, result) => sum + result.failed[index], 0),
  }));
  const failed = failedBySeverity.reduce((sum, entry) => sum + entry.count, 0);
  const assessed = results.reduce((sum, result) => sum + result.passed, failed);
  const metrics = [
    { label: "対象 Run", value: runs.length, icon: ClipboardList, detail: "合成の安全性評価" },
    { label: "完了 Run", value: results.length, icon: CheckCircle2, detail: "判定結果あり" },
    { label: "実行失敗", value: runs.length - results.length, icon: CircleAlert, detail: "判定結果なし" },
    { label: "判定済みケース", value: assessed, icon: Shield, detail: `不合格 ${failed} 件` },
  ];

  return <div className="shell">
    <Sidebar section="safety" />
    <main className="observation-list safety-page">
      <header>
        <div className="heading"><span className="home"><Shield size={27} /></span><div>
          <h1>安全性評価の概要</h1><p>独立した安全性評価 Run の状態とケース結果を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>集計条件</h2>
          <form key={framework} className="observation-filters" action="/safety">
            <label>フレームワーク<select name="framework" defaultValue={framework}><option value="">すべて</option>{frameworks.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit">絞り込む</button><Link href="/safety">条件を解除</Link></div>
          </form>
          <p className="safety-caption">2025/01/20–01/21 JST · 新規実行は未接続です。</p>
        </section>
        <section className="metrics" aria-label="安全性評価の主要指標">
          {metrics.map(({ label, value, icon: Icon, detail }) => <article key={label} className="card metric">
            <span className="icon blue"><Icon size={21} /></span><div><h2>{label}</h2><div className="metric-value">{value} 件</div><p>{detail}</p></div>
          </article>)}
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>不合格ケースの重大度</h2><span>{failed} / {assessed} 件</span></div>
          <dl className="safety-severity">
            {failedBySeverity.map(({ label, color, count }) => <div key={label}>
              <dt><span style={{ backgroundColor: color }} />{label}</dt><dd>{count} 件</dd>
            </div>)}
          </dl>
          <p className="safety-caption">完了 Run に含まれるケースの件数です。同じケースを複数 Run で実施した場合は各 Run に計上します。</p>
        </section>
        <section className="card panel">
          <h2>最近の安全性評価 Run</h2>
          <div className="table-wrap"><table aria-label="最近の安全性評価 Run">
            <thead><tr>{["Run ID", "フレームワーク", "データセット", "開始日時（JST）", "状態", "合格", "不合格"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{runs.map(({ id, framework, dataset, started, result }) => <tr key={id}>
              <td>{id}</td><td>{framework}</td><td>{dataset}</td><td>{started}</td>
              <td><span className={`status ${result ? "safety-done" : "safety-failed"}`}>{result ? "完了" : "実行失敗"}</span></td>
              <td>{result?.passed ?? "N/A"}</td><td>{result ? result.failed.reduce((sum, count) => sum + count, 0) : "N/A"}</td>
            </tr>)}</tbody>
          </table></div>
        </section>
      </div>
    </main>
  </div>;
}
