import Link from "next/link";
import { MessageCircle, Search } from "lucide-react";
import { sessions } from "../demo-data";
import { formatUsd } from "../format-usd";
import Sidebar from "../sidebar";
import { demoSessionId, session } from "./demo-session";
import "../observation-list.css";

export const metadata = { title: "セッション一覧 | Voice Agent Lab" };

const rows = [
  ...sessions.map((row) => ({ ...row, date: "2025-01-21", status: "評価完了" })),
  { id: "sess_demo_text", date: "2025-01-20", time: "16:35", model: "gpt-4o-mini", score: null, status: "未評価" },
  { id: "sess_demo_voice", date: "2025-01-20", time: "09:20", model: "gpt-4o", score: null, status: "評価失敗" },
];
const models = [...new Set(rows.map(({ model }) => model))].sort();
const statuses = ["評価完了", "未評価", "評価失敗"];
const totalTurnCost = session.turns.reduce((total, turn) => total + turn.costUsd, 0);

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function SessionsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q.trim() : "";
  const model = models.find((option) => option === params.model) ?? "";
  const status = statuses.find((option) => option === params.status) ?? "";
  const ascending = params.sort === "oldest";
  const matching = rows.filter((row) => row.id.toLowerCase().includes(q.toLowerCase()) &&
    (!model || row.model === model) && (!status || row.status === status));
  if (ascending) matching.reverse();

  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(matching.length / pageSize));
  const requestedPage = typeof params.page === "string" ? Number(params.page) : 1;
  const page = Number.isSafeInteger(requestedPage) ? Math.min(pageCount, Math.max(1, requestedPage)) : 1;

  function pageHref(nextPage: number) {
    const query = new URLSearchParams();
    if (q) query.set("q", q);
    if (model) query.set("model", model);
    if (status) query.set("status", status);
    if (ascending) query.set("sort", "oldest");
    if (nextPage > 1) query.set("page", String(nextPage));
    return query.size ? `/sessions?${query}` : "/sessions";
  }

  return <div className="shell">
    <Sidebar section="sessions" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><MessageCircle size={27} /></span><div>
          <h1>セッション一覧</h1><p>会話セッションの実行情報と評価状況</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>

      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form action="/sessions" className="observation-filters">
            <label>セッションID<input name="q" type="search" placeholder="sess_…" defaultValue={q} /></label>
            <label>モデル<select name="model" defaultValue={model}><option value="">すべて</option>{models.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>評価状態<select name="status" defaultValue={status}><option value="">すべて</option>{statuses.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>開始日時<select name="sort" defaultValue={ascending ? "oldest" : "latest"}><option value="latest">新しい順</option><option value="oldest">古い順</option></select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/sessions">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>検索結果</h2><span>{matching.length} 件</span></div>
          {matching.length === 0 ? <p className="observation-list-empty">一致するセッションがありません。</p> :
            <div className="table-wrap"><table aria-label="セッション検索結果">
              <thead><tr>{["セッションID", "開始日時（JST）", "LLM", "Agent設定", "評価状態", "評価スコア", "発話コスト小計（USD）"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{matching.slice((page - 1) * pageSize, page * pageSize).map((row) => {
                const hasDetail = row.id === demoSessionId;
                return <tr key={row.id}>
                  <td>{hasDetail ? <Link href={`/sessions/${row.id}`}>{row.id}</Link> : row.id}</td>
                  <td>{row.date.replaceAll("-", "/")} {row.time}</td><td>{row.model}</td>
                  <td>{hasDetail ? session.agentConfig : "N/A"}</td>
                  <td><span className="status" data-evaluation={row.status}>{row.status}</span></td>
                  <td>{row.score?.toFixed(2) ?? "N/A"}</td><td>{formatUsd(hasDetail ? totalTurnCost : null)}</td>
                </tr>;
              })}</tbody>
            </table></div>}
          {pageCount > 1 && <nav className="observation-list-pages" aria-label="検索結果のページ">
            {page > 1 && <Link href={pageHref(page - 1)}>前へ</Link>}
            <span>{page} / {pageCount} ページ</span>
            {page < pageCount && <Link href={pageHref(page + 1)}>次へ</Link>}
          </nav>}
        </section>
      </div>
    </main>
  </div>;
}
