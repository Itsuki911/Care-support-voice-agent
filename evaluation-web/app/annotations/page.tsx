import Link from "next/link";
import { Search, Tag } from "lucide-react";
import Sidebar from "../sidebar";
import { demoSessionAnnotation, session } from "../sessions/demo-session";
import { demoTraceId } from "../traces/demo-trace";
import "../observation-list.css";
import "./annotations.css";

export const metadata = { title: "アノテーション一覧 | Voice Agent Lab" };

const annotations = [
  { id: "annot_demo_003", kind: "セッション", target: session.id, href: `/sessions/${session.id}#annotations`, labels: ["回答品質", "施設案内"], status: "対応済み", assignee: "評価者A", ...demoSessionAnnotation },
  { id: "annot_demo_002", kind: "トレース", target: demoTraceId, href: `/traces/${demoTraceId}`, labels: ["検索", "根拠"], status: "確認中", assignee: "評価者B", author: "評価者A", date: "2025/01/21 14:58 JST", comment: "検索結果に参照資料の版を表示できるか確認してください。" },
  { id: "annot_demo_001", kind: "Finding", target: "finding_demo_004", href: "/safety/findings?q=finding_demo_004", labels: ["承認フロー"], status: "未確認", assignee: null, author: "評価者B", date: "2025/01/21 14:42 JST", comment: "承認待ちの状態が画面に反映されるか確認が必要です。" },
];
const kinds = [...new Set(annotations.map((annotation) => annotation.kind))];
const states = ["未確認", "確認中", "対応済み", "再検証"];

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function AnnotationsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const kind = kinds.find((option) => option === params.kind) ?? "";
  const status = states.find((option) => option === params.status) ?? "";
  const rows = annotations.filter((annotation) =>
    (!kind || annotation.kind === kind) && (!status || annotation.status === status) &&
    [annotation.id, annotation.target, annotation.comment, ...annotation.labels].some((value) => value.toLowerCase().includes(term))
  );

  return <div className="shell">
    <Sidebar section="annotations" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Tag size={27} /></span><div>
          <h1>アノテーション一覧</h1><p>レビューコメント、ラベル、担当者と対応状況を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, kind, status])} action="/annotations" className="observation-filters">
            <label>ID・コメント・ラベル<input type="search" name="q" placeholder="annot_demo_…" defaultValue={query} /></label>
            <label>対象種別<select name="kind" defaultValue={kind}><option value="">すべて</option>{kinds.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>レビュー状態<select name="status" defaultValue={status}><option value="">すべて</option>{states.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/annotations">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>レビューコメント</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致するアノテーションがありません。</p> :
            <div className="table-wrap"><table className="annotations-table" aria-label="レビューコメント一覧">
              <thead><tr>{["コメント", "対象", "ラベル", "レビュー状態", "担当者"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map((annotation) => <tr key={annotation.id}>
                <td><p>{annotation.comment}</p><small>{annotation.id} · {annotation.author} · {annotation.date}</small></td>
                <td><small>{annotation.kind}</small><Link href={annotation.href}>{annotation.target}</Link></td>
                <td><div className="annotation-labels">{annotation.labels.map((label) => <span key={label}>{label}</span>)}</div></td>
                <td><span className="status" data-review={annotation.status}>{annotation.status}</span></td>
                <td>{annotation.assignee ?? "未割当"}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
