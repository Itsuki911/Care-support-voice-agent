import Link from "next/link";
import { ClipboardCheck, Shield } from "lucide-react";
import Sidebar from "../../sidebar";
import { safetyRuns } from "../demo-safety";
import "../../observation-list.css";
import "../safety.css";

export const metadata = { title: "安全性評価の新規 Run | Voice Agent Lab" };

const targets = ["LLM 単体", "Agent 全体（テキスト）"];
const configVersions = ["v12", "v11"];
const frameworks = [...new Set(safetyRuns.map((run) => run.framework))];
const datasets = [...new Set(safetyRuns.map((run) => run.dataset))];
const profiles = ["Quick", "Standard", "Comprehensive"];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function selectOption(options: readonly string[], value: string | string[] | undefined) {
  return options.find((option) => option === value) ?? options[0];
}

export default async function NewSafetyRunPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const review = params.review === "1";
  const target = selectOption(targets, params.target);
  const version = selectOption(configVersions, params.version);
  const requested = typeof params.framework === "string" ? [params.framework] : params.framework ?? [];
  const selected = review ? frameworks.filter((option) => requested.includes(option)) : frameworks.slice(0, 1);
  const dataset = selectOption(datasets, params.dataset);
  const profile = selectOption(profiles, params.profile);
  const error = review && selected.length === 0;
  const summary = [
    ["対象", target],
    ["Agent 設定", version],
    ["フレームワーク", selected.join(" / ")],
    ["データセット版", dataset],
    ["プロファイル", profile],
  ];

  return <div className="shell">
    <Sidebar section="safety" />
    <main className="observation-list safety-page">
      <header>
        <div className="heading"><span className="home"><Shield size={27} /></span><div>
          <h1>安全性評価の新規 Run</h1><p>サンプルの設定を選び、確認画面に表示します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <nav aria-label="安全性評価"><Link href="/safety">← 安全性評価の概要</Link></nav>
        <div className="safety-new-grid">
          <section className="card panel">
            <h2>Run 設定</h2>
            <form action="/safety/new" className="observation-filters safety-new-form">
              <input type="hidden" name="review" value="1" />
              <label>評価対象<select name="target" defaultValue={target}>{targets.map((option) => <option key={option}>{option}</option>)}<option disabled>Agent 全体（音声・準備中）</option></select></label>
              <label>Agent 設定<select name="version" defaultValue={version}>{configVersions.map((option) => <option key={option}>{option}</option>)}</select></label>
              <fieldset aria-describedby={error ? "framework-error" : undefined}><legend>フレームワーク（複数選択）</legend>
                {frameworks.map((option) => <label key={option}><input type="checkbox" name="framework" value={option} defaultChecked={selected.includes(option)} />{option}</label>)}
                {error && <p id="framework-error" role="alert">フレームワークを1つ以上選んでください。</p>}
              </fieldset>
              <label>データセット版<select name="dataset" defaultValue={dataset}>{datasets.map((option) => <option key={option}>{option}</option>)}</select></label>
              <label>評価プロファイル<select name="profile" defaultValue={profile}>{profiles.map((option) => <option key={option}>{option}</option>)}</select></label>
              <div className="observation-filter-actions"><button type="submit"><ClipboardCheck size={16} /> 設定を確認</button></div>
            </form>
          </section>
          <section className="card panel">
            <h2>設定プレビュー</h2>
            {review && !error ? <dl className="safety-review">
              {summary.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
            </dl> : <p className="safety-caption">「設定を確認」を押すと、選んだ内容がここに表示されます。</p>}
            <dl className="safety-review">
              <div><dt>隔離環境</dt><dd>未接続</dd></div>
              <div><dt>概算予算（USD）</dt><dd>N/A</dd></div>
            </dl>
            <p className="safety-caption">この画面は設定プレビュー用です。Run の実行や保存は行いません。</p>
          </section>
        </div>
      </div>
    </main>
  </div>;
}
