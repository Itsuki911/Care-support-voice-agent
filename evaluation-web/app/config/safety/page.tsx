import Link from "next/link";
import { ClipboardCheck, LockKeyhole, Shield } from "lucide-react";
import Sidebar from "../../sidebar";
import "../../observation-list.css";
import "../evaluator/evaluator.css";

export const metadata = { title: "安全性設定 | Voice Agent Lab" };

const policies = [
  ["評価データ", "合成データのみ"],
  ["環境", "隔離されたテスト環境のみ"],
  ["外部操作", "無効"],
  ["保存前のマスキング", "必須"],
  ["安全性の必須チェック", "有効"],
] as const;

const reviewers = [
  { value: "safety", label: "安全性レビュー担当" },
  { value: "quality", label: "品質レビュー担当" },
];
const retentionOptions = ["7", "14", "30"];
const baseline = { reviewer: reviewers[0], retention: "14" };
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SafetyConfigPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const reviewing = params.review === "1";
  const reviewer = reviewers.find((option) => option.value === params.reviewer);
  const retention = retentionOptions.find((option) => option === params.retention);
  const invalid = reviewing && (!reviewer || !retention);
  const selectedReviewer = reviewer ?? baseline.reviewer;
  const selectedRetention = retention ?? baseline.retention;
  const changes = [
    { label: "既定のレビュー担当", before: baseline.reviewer.label, after: selectedReviewer.label },
    { label: "マスキング済みレポートの保持期間", before: `${baseline.retention} 日`, after: `${selectedRetention} 日` },
  ].filter(({ before, after }) => before !== after);

  return <div className="shell">
    <Sidebar section="safety-config" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Shield size={27} /></span><div>
          <h1>安全性設定</h1><p>安全性評価の固定ポリシーとレビュー設定を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <div className="evaluator-grid">
          <div className="evaluator-stack">
            <section className="card panel">
              <div className="panel-heading"><h2>固定ポリシー</h2><Link href="/safety">安全性評価の概要 →</Link></div>
              <dl className="evaluator-summary">
                {policies.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
              </dl>
              <p className="evaluator-caption"><LockKeyhole size={16} /> 固定ポリシーは変更できません。</p>
            </section>
            <section className="card panel">
              <h2>レビューとレポートの設定</h2>
              <form key={JSON.stringify([reviewing, selectedReviewer.value, selectedRetention])} action="/config/safety" className="observation-filters">
                <input type="hidden" name="review" value="1" />
                <label>既定のレビュー担当<select name="reviewer" defaultValue={selectedReviewer.value}>
                  {reviewers.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
                </select></label>
                <label>マスキング済みレポートの保持期間<select name="retention" defaultValue={selectedRetention}>
                  {retentionOptions.map((value) => <option key={value} value={value}>{value} 日</option>)}
                </select></label>
                <div className="observation-filter-actions"><button type="submit"><ClipboardCheck size={16} /> 変更を確認</button><Link href="/config/safety">初期設定に戻す</Link></div>
              </form>
            </section>
          </div>
          <section className="card panel">
            <h2>変更プレビュー</h2>
            {invalid ? <p role="alert">レビュー担当と保持期間を選び直してください。</p> : !reviewing ? <p>「変更を確認」を押すと差分が表示されます。</p> : changes.length === 0 ? <p>差分はありません。</p> :
              <dl className="evaluator-summary">{changes.map(({ label, before, after }) => <div key={label}><dt>{label}</dt><dd>{before} → {after}</dd></div>)}</dl>}
            <p className="evaluator-caption">表示はサンプルです。設定の保存と適用は未接続です。</p>
          </section>
        </div>
      </div>
    </main>
  </div>;
}
