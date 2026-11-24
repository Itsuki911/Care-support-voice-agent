import Link from "next/link";
import { Database, Search } from "lucide-react";
import { runs } from "../evaluations/demo-runs";
import { session } from "../sessions/demo-session";
import Sidebar from "../sidebar";
import "../observation-list.css";
import "./datasets.css";

export const metadata = { title: "通常評価データセット | Voice Agent Lab" };

const datasets = [
  { id: "dataset_demo_voice_v2", name: "施設案内の音声会話", version: "v2", state: "公開済み", category: "音声会話", cases: 24, complete: 18, requirements: "会話ログ・期待結果・録音", source: "合成セッション", expected: "受付時間と見学予約の要否を案内する。", failure: "受付時間または予約条件が資料と異なる。", sessionId: session.id },
  { id: "dataset_demo_text_v1", name: "受付 FAQ", version: "v1", state: "公開済み", category: "テキスト会話", cases: 12, complete: 12, requirements: "会話ログ・期待結果", source: "合成ケース", expected: "資料に根拠がない情報は確認できないと伝える。", failure: "確認できない情報を断定する。", sessionId: null },
  { id: "dataset_demo_voice_v1", name: "施設案内の音声会話", version: "v1", state: "アーカイブ", category: "音声会話", cases: 16, complete: null, requirements: "会話ログ・期待結果・録音", source: "合成セッション", expected: "施設の受付時間を案内する。", failure: "受付時間が資料と異なる。", sessionId: null },
];
const states = [...new Set(datasets.map((dataset) => dataset.state))];
const categories = [...new Set(datasets.map((dataset) => dataset.category))];
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function DatasetsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const state = states.find((option) => option === params.state) ?? "";
  const category = categories.find((option) => option === params.category) ?? "";
  const rows = datasets.filter((dataset) =>
    (!state || dataset.state === state) && (!category || dataset.category === category) &&
    [dataset.id, dataset.name].some((value) => value.toLowerCase().includes(term))
  );

  return <div className="shell">
    <Sidebar section="datasets" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Database size={27} /></span><div>
          <h1>通常評価データセット</h1><p>データセットの版、ケース、評価に必要な入力の充足状況を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, state, category])} action="/datasets" className="observation-filters">
            <label>データセット名・ID<input type="search" name="q" placeholder="dataset_demo_…" defaultValue={query} /></label>
            <label>カテゴリ<select name="category" defaultValue={category}><option value="">すべて</option>{categories.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>状態<select name="state" defaultValue={state}><option value="">すべて</option>{states.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/datasets">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>データセット版</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致するデータセットがありません。</p> :
            <div className="table-wrap"><table className="dataset-table" aria-label="通常評価データセットの版">
              <thead><tr>{["データセット", "版", "カテゴリ", "状態", "ケース数", "必要入力の充足", "作成元", "評価 Run"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map(({ id, name, version, category, state, cases, complete, requirements, source, expected, failure, sessionId }) => {
                const runCount = runs.filter((run) => run.target === id).length;
                return <tr key={id}>
                  <td><details className="dataset-case">
                    <summary>{name}</summary><small>{id}</small>
                    <dl><div><dt>必要な入力</dt><dd>{requirements}</dd></div><div><dt>期待結果の例</dt><dd>{expected}</dd></div><div><dt>失敗条件の例</dt><dd>{failure}</dd></div></dl>
                    {sessionId && <Link href={`/sessions/${sessionId}`}>合成セッション例を開く</Link>}
                  </details></td>
                  <td>{version}</td><td>{category}</td><td><span className="status">{state}</span></td><td>{cases} 件</td>
                  <td>{complete === null ? "N/A" : `${complete} / ${cases} 件（${Math.round(complete / cases * 100)}%）`}</td><td>{source}</td>
                  <td>{runCount ? <Link href={`/evaluations?q=${encodeURIComponent(id)}`}>{runCount} 件</Link> : "0 件"}</td>
                </tr>;
              })}</tbody>
            </table></div>}
          <p className="dataset-caption">充足率は必要な入力がすべて揃ったケースの割合です。未確認の版は N/A と表示します。</p>
        </section>
      </div>
    </main>
  </div>;
}
