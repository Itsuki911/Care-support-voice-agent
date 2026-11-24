import Link from "next/link";
import { Activity, ClipboardCheck, LockKeyhole } from "lucide-react";
import Sidebar from "../../sidebar";
import "../../observation-list.css";
import "../evaluator/evaluator.css";

export const metadata = { title: "観測設定 | Voice Agent Lab" };

const settings = [
  { key: "sampling", label: "通常トレースのサンプリング率", options: ["100%", "50%", "25%"], baseline: "100%" },
  { key: "level", label: "ログレベル", options: ["INFO", "WARN", "ERROR"], baseline: "INFO" },
  { key: "retention", label: "マスキング済みログの保持期間", options: ["7 日", "14 日", "30 日"], baseline: "14 日" },
];

const fixed = [
  ["重大な安全性イベント", "全件記録"],
  ["秘密情報・個人情報", "外部送信禁止"],
  ["テレメトリのマスキング", "必須"],
  ["録音の保存", "無効（モック）"],
] as const;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function ObservabilityPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const preview = params.preview === "1";
  const fields = settings.map((setting) => ({
    ...setting,
    selected: setting.options.find((option) => option === params[setting.key]),
  }));
  const invalid = preview && fields.some(({ selected }) => selected === undefined);
  const changes = fields.filter(({ baseline, selected }) => selected !== undefined && baseline !== selected);

  return <div className="shell">
    <Sidebar section="observability-config" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Activity size={27} /></span><div>
          <h1>観測設定</h1><p>トレースの取得率、ログレベル、保持期間を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <div className="evaluator-grid">
          <div className="evaluator-stack">
            <section className="card panel">
              <div className="panel-heading"><h2>トレースとログ</h2><Link href="/traces">トレース一覧 →</Link></div>
              <form key={JSON.stringify([preview, fields.map(({ selected }) => selected)])} action="/config/observability" className="evaluator-stack">
                <input type="hidden" name="preview" value="1" />
                <div className="observation-filters">
                  {fields.map(({ key, label, options, baseline, selected }) => <label key={key}>{label}
                    <select name={key} defaultValue={selected ?? baseline}>{options.map((option) => <option key={option}>{option}</option>)}</select>
                  </label>)}
                </div>
                <div className="observation-filter-actions"><button type="submit"><ClipboardCheck size={16} /> 変更を確認</button><Link href="/config/observability">初期設定に戻す</Link></div>
              </form>
            </section>
            <section className="card panel">
              <h2>記録と保護のポリシー</h2>
              <dl className="evaluator-summary">{fixed.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
              <p className="evaluator-caption"><LockKeyhole size={16} /> 重大な安全性イベントはサンプリング率にかかわらず記録する設定です。</p>
            </section>
          </div>
          <div className="evaluator-stack">
            <section className="card panel">
              <h2>変更プレビュー</h2>
              {invalid ? <p role="alert">選択内容を確認して、もう一度送信してください。</p> : !preview ? <p>「変更を確認」を押すと初期設定との差分を表示します。</p> : changes.length === 0 ? <p>差分はありません。</p> :
                <dl className="evaluator-summary">{changes.map(({ key, label, baseline, selected }) => <div key={key}><dt>{label}</dt><dd>{baseline} → {selected}</dd></div>)}</dl>}
              <p className="evaluator-caption">観測設定の保存と適用は未接続です。</p>
            </section>
            <section className="card panel">
              <h2>接続状況</h2>
              <dl className="evaluator-summary"><div><dt>Langfuse</dt><dd>未接続（モック）</dd></div><div><dt>最終同期</dt><dd>N/A</dd></div></dl>
            </section>
          </div>
        </div>
      </div>
    </main>
  </div>;
}
