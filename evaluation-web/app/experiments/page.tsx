import Link from "next/link";
import { GitCompareArrows } from "lucide-react";
import Sidebar from "../sidebar";
import "../observation-list.css";
import "./experiments.css";

export const metadata = { title: "実験（A/B テスト） | Voice Agent Lab" };

const experiments = [
  {
    id: "agent", label: "Agent 設定 A/B", mode: "Agent を条件ごとに新規実行",
    variable: "Agent 設定版", fixed: "データセット版・評価設定 v5・Judge モデル",
    a: "v11", b: "v12",
    pairs: [
      { caseId: "case_01", label: "受付時間の案内", a: 0.8, b: 0.9 },
      { caseId: "case_02", label: "見学予約の案内", a: 0.7, b: 0.85 },
      { caseId: "case_03", label: "案内先の確認", a: null, b: 0.8 },
    ],
  },
  {
    id: "judge", label: "Judge モデル比較", mode: "同一の保存済み出力を再採点",
    variable: "Judge モデル", fixed: "データセット版・Agent 出力・採点指標",
    a: "gpt-4o-mini", b: "gpt-4o",
    pairs: [
      { caseId: "case_01", label: "受付時間の案内", a: 0.85, b: 0.8 },
      { caseId: "case_02", label: "見学予約の案内", a: 0.9, b: 0.85 },
      { caseId: "case_03", label: "案内先の確認", a: 0.75, b: 0.75 },
    ],
  },
];

type SearchParams = Promise<{ experiment?: string | string[] }>;

function score(value: number | null) {
  return value === null ? "N/A" : value.toFixed(2);
}

function delta(a: number, b: number) {
  const change = Number((b - a).toFixed(2));
  return `${change > 0 ? "+" : ""}${change.toFixed(2)}`;
}

export default async function ExperimentsPage({ searchParams }: { searchParams: SearchParams }) {
  const { experiment } = await searchParams;
  const selected = experiments.find(({ id }) => id === experiment) ?? experiments[0];
  const paired = selected.pairs.flatMap(({ a, b }) => a === null || b === null ? [] : [{ a, b }]);
  const missing = selected.pairs.length - paired.length;
  const average = (side: "a" | "b") => paired.length ? paired.reduce((total, pair) => total + pair[side], 0) / paired.length : null;
  const averageA = average("a");
  const averageB = average("b");

  return <div className="shell">
    <Sidebar section="experiments" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><GitCompareArrows size={27} /></span><div>
          <h1>実験（A/B テスト）</h1><p>同じケースに対する2つの条件の評価結果を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>比較対象</h2>
          <nav className="experiment-nav" aria-label="実験サンプル">
            {experiments.map(({ id, label }) => <Link key={id} href={`/experiments?experiment=${id}`} aria-current={selected.id === id ? "page" : undefined}>{label}</Link>)}
          </nav>
          <dl className="experiment-setup">
            <div><dt>実行方式</dt><dd>{selected.mode}</dd></div>
            <div><dt>変更変数</dt><dd>{selected.variable}</dd></div>
            <div><dt>固定条件</dt><dd>{selected.fixed}</dd></div>
            <div><dt>データセット版</dt><dd><Link href="/datasets?q=dataset_demo_voice_v2">dataset_demo_voice_v2</Link></dd></div>
          </dl>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>回答の関連性スコア</h2><span>{paired.length} / {selected.pairs.length} ケースを比較</span></div>
          <p className="experiment-caption">A または B が欠損したケースは {missing} 件（{(missing / selected.pairs.length * 100).toFixed(1)}%）です。平均は両方のスコアが揃ったケースで算出します。</p>
          <div className="table-wrap"><table aria-label="ケース別の A/B スコア">
            <thead><tr><th scope="col">ケース</th><th scope="col">A · {selected.a}</th><th scope="col">B · {selected.b}</th><th scope="col">差分（B − A）</th></tr></thead>
            <tbody>{selected.pairs.map(({ caseId, label, a, b }) => <tr key={caseId}>
              <td>{label}<small className="experiment-case-id">{caseId}</small></td><td>{score(a)}</td><td>{score(b)}</td><td>{a === null || b === null ? "N/A" : delta(a, b)}</td>
            </tr>)}</tbody>
            <tfoot><tr><th scope="row">比較ケースの平均</th><td>{score(averageA)}</td><td>{score(averageB)}</td><td>{averageA === null || averageB === null ? "N/A" : delta(averageA, averageB)}</td></tr></tfoot>
          </table></div>
          <p className="experiment-caption">合成ケースによる表示例です。新規実験の実行と保存は未接続です。</p>
        </section>
      </div>
    </main>
  </div>;
}
