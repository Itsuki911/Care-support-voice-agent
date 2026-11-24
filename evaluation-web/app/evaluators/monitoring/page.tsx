import Link from "next/link";
import { Activity, Clock3, Coins, Gauge, Search } from "lucide-react";
import { runs } from "../../evaluations/demo-runs";
import { formatUsd } from "../../format-usd";
import { session } from "../../sessions/demo-session";
import Sidebar from "../../sidebar";
import "../../observation-list.css";
import "./monitoring.css";

export const metadata = { title: "評価モニタリング | Voice Agent Lab" };

const judges = [...new Set(runs.map(({ judge }) => judge))];
const states = ["待機中", "実行中", "完了", "実行失敗"];

function percent(numerator: number, denominator: number) {
  return denominator ? `${(numerator / denominator * 100).toFixed(1)}%` : "N/A";
}

function seconds(value: number | undefined) {
  return value === undefined ? "N/A" : `${value.toFixed(2)} s`;
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function MonitoringPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const judge = judges.find((option) => option === params.judge) ?? "";
  const selected = runs.filter((run) => !judge || run.judge === judge);
  const completed = selected.filter((run) => run.status === "完了");
  const failed = selected.filter((run) => run.status === "実行失敗").length;
  const durations = selected.flatMap((run) => run.seconds === null ? [] : [run.seconds]).sort((a, b) => a - b);
  const p = (quantile: number) => durations[Math.ceil(quantile * durations.length) - 1];
  const costValues = selected.flatMap((run) => run.cost === null ? [] : [run.cost]);
  const outputChecks = selected.filter((run) => run.outputValid !== null);
  const sampleMetrics = completed.some((run) => run.target === session.id) ? session.metrics : [];
  const metrics = [
    { icon: Activity, label: "実行成功率", value: percent(completed.length, completed.length + failed), detail: `対象 ${completed.length + failed} 件（終了済み）` },
    { icon: Clock3, label: "P95 実行時間", value: seconds(p(0.95)), detail: `計測 ${durations.length} 件` },
    { icon: Coins, label: "Judge コスト小計", value: formatUsd(costValues.length ? costValues.reduce((sum, value) => sum + value, 0) : null), detail: `未計測 ${selected.length - costValues.length} 件` },
    { icon: Gauge, label: "構造化出力失敗率", value: percent(outputChecks.filter((run) => run.outputValid === false).length, outputChecks.length), detail: `検証済み ${outputChecks.length} 件` },
  ];

  return <div className="shell">
    <Sidebar section="evaluator-monitoring" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Activity size={27} /></span><div>
          <h1>評価モニタリング</h1><p>通常評価ジョブと Judge モデルの実行状況</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <div className="panel-heading"><h2>集計条件</h2><Link href="/evaluations">評価結果一覧 →</Link></div>
          <form key={judge} className="observation-filters" action="/evaluators/monitoring">
            <label>Judge モデル<select name="judge" defaultValue={judge}><option value="">すべて</option>{judges.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 絞り込む</button><Link href="/evaluators/monitoring">条件を解除</Link></div>
          </form>
          <p className="monitoring-caption">2025/01/20–01/21 JST · 通常評価 Run {selected.length} 件</p>
        </section>
        <section className="monitoring-kpis" aria-label="評価ジョブの主要指標">
          {metrics.map(({ icon: Icon, label, value, detail }) => <article key={label} className="card monitoring-kpi">
            <span className="icon blue"><Icon size={21} /></span><div><h2>{label}</h2><strong>{value}</strong><p>{detail}</p></div>
          </article>)}
        </section>
        <div className="monitoring-panels">
          <section className="card panel">
            <h2>ジョブ状態</h2>
            <dl className="monitoring-states">{states.map((state) => <div key={state}><dt>{state}</dt><dd>{selected.filter((run) => run.status === state).length} 件</dd></div>)}</dl>
          </section>
          <section className="card panel">
            <h2>実行時間の分布</h2>
            <dl className="monitoring-states">{[0.5, 0.95, 0.99].map((quantile) => <div key={quantile}><dt>P{quantile * 100}</dt><dd>{seconds(p(quantile))}</dd></div>)}</dl>
            <p className="monitoring-caption">終了済みの計測 {durations.length} 件 · 最近順位法</p>
          </section>
        </div>
        <section className="card panel">
          <h2>Judge モデル別の利用状況</h2>
          <div className="table-wrap"><table aria-label="Judge モデル別の利用状況">
            <thead><tr>{["モデル", "Run", "実行失敗", "リトライ", "計測トークン小計", "計測コスト小計（USD）"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{judges.filter((model) => !judge || model === judge).map((model) => {
              const group = selected.filter((run) => run.judge === model);
              const tokenValues = group.flatMap((run) => run.tokens === null ? [] : [run.tokens]);
              const groupCosts = group.flatMap((run) => run.cost === null ? [] : [run.cost]);
              return <tr key={model}>
                <td>{model}</td><td>{group.length}</td><td>{group.filter((run) => run.status === "実行失敗").length}</td><td>{group.reduce((sum, run) => sum + run.retries, 0)}</td>
                <td>{tokenValues.length ? tokenValues.reduce((sum, value) => sum + value, 0).toLocaleString("ja-JP") : "N/A"}</td>
                <td>{formatUsd(groupCosts.length ? groupCosts.reduce((sum, value) => sum + value, 0) : null)}</td>
              </tr>;
            })}</tbody>
          </table></div>
        </section>
        <section className="card panel">
          <h2>評価指標の欠損</h2>
          <p className="monitoring-caption">完了 Run の指標結果に占める N/A は {percent(sampleMetrics.filter((metric) => metric.score === null).length, sampleMetrics.length)}（{sampleMetrics.length} 指標）です。</p>
          <p className="monitoring-caption">セッションの評価カバレッジ、人手評価との一致率、固定データセットでの判定変動は N/A です。</p>
        </section>
      </div>
    </main>
  </div>;
}
