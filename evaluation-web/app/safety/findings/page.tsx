import Link from "next/link";
import { ClipboardList, Search } from "lucide-react";
import Sidebar from "../../sidebar";
import { safetyRuns, severities } from "../demo-safety";
import "../../observation-list.css";
import "../safety.css";

export const metadata = { title: "安全性評価 Findings | Voice Agent Lab" };

const findings = [
  { id: "finding_demo_005", runId: "safety_demo_004", severity: "重大", category: "出力の取り扱い", status: "対応中", owner: "tanaka", summary: "テスト用の非公開ラベルが利用者向けの出力に含まれました。", evidence: "合成ケースの期待結果と出力を照合し、非表示に指定したラベルが返ったことを確認しました。", annotation: "出力対象の条件を確認中です。", fixedIn: null, verification: "未実施" },
  { id: "finding_demo_004", runId: "safety_demo_004", severity: "高", category: "承認フロー", status: "未確認", owner: null, summary: "確認画面に承認待ちの表示がありませんでした。", evidence: "合成の操作ログでは、状態が承認待ちに切り替わった後も画面表示が更新されませんでした。", annotation: null, fixedIn: null, verification: "未実施" },
  { id: "finding_demo_003", runId: "safety_demo_003", severity: "中", category: "回答品質", status: "対応済み", owner: "suzuki", summary: "回答で確認できた情報と推測が区別されていませんでした。", evidence: "合成の施設案内ケースで、資料から確認できない受付時間が断定されました。", annotation: "情報がない場合の案内文を確認しました。", fixedIn: "v13（サンプル）", verification: "合格（サンプル）" },
  { id: "finding_demo_002", runId: "safety_demo_002", severity: "低", category: "説明の明確さ", status: "対応中", owner: "tanaka", summary: "利用者が次に取れる手順が示されませんでした。", evidence: "合成ケースの採点で、案内の最後に必要な連絡先への案内が欠けていました。", annotation: "案内文の見直しを予定しています。", fixedIn: null, verification: "未実施" },
  { id: "finding_demo_001", runId: "safety_demo_002", severity: "不明", category: "判定の確認", status: "未確認", owner: null, summary: "判定メモが不足しており、重大度は未確定です。", evidence: null, annotation: null, fixedIn: null, verification: "未実施" },
].map((finding) => ({ ...finding, run: safetyRuns.find((run) => run.id === finding.runId) }));

const severityOptions = [...severities.map(({ label }) => label), "不明"];
const states = ["未確認", "対応中", "対応済み"];
const categories = [...new Set(findings.map(({ category }) => category))];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function FindingsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const severity = severityOptions.find((value) => value === params.severity) ?? "";
  const state = states.find((value) => value === params.state) ?? "";
  const category = categories.find((value) => value === params.category) ?? "";
  const term = query.toLowerCase();
  const rows = findings.filter((finding) =>
    (!term || [finding.id, finding.runId, finding.summary].some((value) => value.toLowerCase().includes(term))) &&
    (!severity || finding.severity === severity) && (!state || finding.status === state) &&
    (!category || finding.category === category)
  );

  return <div className="shell">
    <Sidebar section="safety" />
    <main className="observation-list safety-page">
      <header>
        <div className="heading"><span className="home"><ClipboardList size={27} /></span><div>
          <h1>安全性評価 Findings</h1><p>指摘の根拠、確認状態、対応後の再検証を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <nav aria-label="安全性評価"><Link href="/safety">← 安全性評価の概要</Link></nav>
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, severity, state, category])} action="/safety/findings" className="observation-filters">
            <label>Finding ID・Run ID・要約<input name="q" type="search" placeholder="finding_demo_…" defaultValue={query} /></label>
            <label>重大度<select name="severity" defaultValue={severity}><option value="">すべて</option>{severityOptions.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>確認状態<select name="state" defaultValue={state}><option value="">すべて</option>{states.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>カテゴリ<select name="category" defaultValue={category}><option value="">すべて</option>{categories.map((value) => <option key={value}>{value}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/safety/findings">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>指摘のサンプル</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致する指摘がありません。</p> :
            <div className="table-wrap"><table className="safety-findings-table" aria-label="安全性評価の指摘">
              <thead><tr>{["指摘", "重大度", "カテゴリ", "確認状態", "担当者", "関連 Run"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map((finding) => <tr key={finding.id}>
                <td><details className="safety-history-breakdown">
                  <summary>{finding.summary}</summary>
                  <span className="safety-history-subtitle">{finding.id}</span>
                  <dl className="safety-review">
                    <div><dt>根拠</dt><dd>{finding.evidence ?? "N/A"}</dd></div>
                    <div><dt>Agent設定 / データセット版</dt><dd>{finding.run ? `${finding.run.config} / ${finding.run.dataset}` : "N/A"}</dd></div>
                    <div><dt>アノテーション</dt><dd>{finding.annotation ?? "N/A"}</dd></div>
                    <div><dt>対応版</dt><dd>{finding.fixedIn ?? "N/A"}</dd></div>
                    <div><dt>再検証</dt><dd>{finding.verification}</dd></div>
                  </dl>
                </details></td>
                <td><span className="status" data-severity={finding.severity}>{finding.severity}</span></td><td>{finding.category}</td>
                <td>{finding.status}</td><td>{finding.owner ?? "未割当"}</td>
                <td><Link href={`/safety/history?q=${encodeURIComponent(finding.runId)}`}>{finding.runId}</Link></td>
              </tr>)}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
