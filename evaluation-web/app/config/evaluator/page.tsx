import Link from "next/link";
import { ClipboardCheck, Settings, ShieldCheck } from "lucide-react";
import Sidebar from "../../sidebar";
import { session } from "../../sessions/demo-session";
import "../../observation-list.css";
import "./evaluator.css";

export const metadata = { title: "評価設定（DeepEval） | Voice Agent Lab" };

const judges = ["gpt-4o-mini", "gpt-4o"];
const metrics = [
  { id: "relevancy", label: "回答の関連性", input: "質問・回答", threshold: "0.75" },
  { id: "completion", label: "タスク達成度", input: "会話ログ・期待結果", threshold: "0.80" },
  { id: "faithfulness", label: "事実性", input: "回答・検索コンテキスト", threshold: "0.80" },
  { id: "context", label: "文脈の関連性", input: "質問・検索コンテキスト", threshold: "0.70" },
];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function EvaluatorPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const review = params.review === "1";
  const judge = judges.find((option) => option === params.judge) ?? judges[0];
  const automatic = !review || params.automatic === "1";
  const requested = typeof params.metric === "string" ? [params.metric] : params.metric ?? [];
  const selections = metrics.map((metric) => {
    const raw = params[metric.id];
    const enabled = !review || requested.includes(metric.id);
    const value = review && typeof raw === "string" ? raw : metric.threshold;
    const valid = /^(?:0(?:\.\d{1,2})?|1(?:\.0{1,2})?)$/.test(value);
    return { ...metric, value, enabled, valid };
  });
  const errors = selections.filter((metric) => metric.enabled && !metric.valid);
  const changes = selections.filter((metric) => !metric.enabled || Number(metric.value) !== Number(metric.threshold));

  return <div className="shell">
    <Sidebar section="evaluator-config" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Settings size={27} /></span><div>
          <h1>評価設定（DeepEval）</h1><p>通常評価用の Judge と評価指標を設定します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <div className="evaluator-grid">
          <form key={JSON.stringify([review, judge, automatic, selections])} action="/config/evaluator" className="evaluator-stack">
            <input type="hidden" name="review" value="1" />
            <section className="card panel">
              <div className="panel-heading"><h2>Judge 設定</h2><Link href="/evaluators/monitoring">評価モニタリング →</Link></div>
              <div className="observation-filters">
                <label>Judge モデル<select name="judge" defaultValue={judge}>{judges.map((option) => <option key={option}>{option}</option>)}</select></label>
              </div>
              <label className="evaluator-toggle"><input type="checkbox" name="automatic" value="1" defaultChecked={automatic} /> 会話終了後の自動評価</label>
            </section>
            <section className="card panel">
              <h2>評価指標</h2>
              <div className="table-wrap"><table aria-label="評価指標の設定">
                <thead><tr><th scope="col">指標</th><th scope="col">必要な入力</th><th scope="col">有効</th><th scope="col">合格閾値</th></tr></thead>
                <tbody>{selections.map(({ id, label, input, value, enabled, valid }) => <tr key={id}>
                  <td>{label}</td><td>{input}</td>
                  <td><input aria-label={`${label}を有効にする`} type="checkbox" name="metric" value={id} defaultChecked={enabled} /></td>
                  <td><input aria-label={`${label}の合格閾値`} aria-invalid={enabled && !valid} type="number" name={id} min="0" max="1" step="0.01" defaultValue={value} /></td>
                </tr>)}</tbody>
              </table></div>
              <p className="evaluator-caption"><ShieldCheck size={16} /> 承認違反の必須チェックは固定です。</p>
              <div className="observation-filter-actions evaluator-actions"><button type="submit"><ClipboardCheck size={16} /> 変更を確認</button><Link href="/config/evaluator">初期設定に戻す</Link></div>
            </section>
          </form>
          <section className="card panel">
            <h2>ドラフトの確認</h2>
            <p className="evaluator-caption">比較元は適用済み設定 {session.evaluatorConfig} のサンプルです。</p>
            {errors.length > 0 ? <p role="alert">合格閾値は 0〜1 の範囲で小数第2位まで入力してください。</p> : review ? <>
              <dl className="evaluator-summary">
                <div><dt>Judge モデル</dt><dd>{judge === judges[0] ? judge : `${judges[0]} → ${judge}`}</dd></div>
                <div><dt>自動評価</dt><dd>{automatic ? "有効" : "有効 → 無効"}</dd></div>
                {changes.map(({ id, label, threshold, value, enabled }) => <div key={id}><dt>{label}</dt><dd>{enabled ? `${threshold} → ${value}` : "有効 → 無効"}</dd></div>)}
              </dl>
              {changes.length === 0 && judge === judges[0] && automatic && <p>差分はありません。</p>}
            </> : <p>「変更を確認」を押すと、選んだ設定が表示されます。</p>}
            <p className="evaluator-caption">この画面ではプレビューまでを確認できます。評価ジョブと設定の適用は未接続です。</p>
          </section>
        </div>
      </div>
    </main>
  </div>;
}
