import Link from "next/link";
import { GitBranch, Search } from "lucide-react";
import { formatUsd } from "../format-usd";
import Sidebar from "../sidebar";
import { session } from "../sessions/demo-session";
import { demoTraceId, relatedSessionId, root, spans, traceCostSubtotal, unmeasuredLeafCount } from "./demo-trace";
import "../observation-list.css";

export const metadata = { title: "トレース一覧 | Voice Agent Lab" };

const rows = [
  { id: demoTraceId, sessionId: relatedSessionId, model: session.model, kind: "音声", status: "完了", date: "2025-01-21", time: root.start, seconds: root.duration, spanNames: spans.map(({ span }) => span.name), cost: traceCostSubtotal, missing: unmeasuredLeafCount },
  { id: "trace_demo_text", sessionId: "sess_demo_text", model: "gpt-4o-mini", kind: "テキスト", status: "完了", date: "2025-01-20", time: "16:35:02", seconds: 2.74, spanNames: ["llm.call", "response.stream"], cost: 0.0012, missing: 0 },
  { id: "trace_demo_voice", sessionId: "sess_demo_voice", model: "gpt-4o", kind: "音声", status: "エラー", date: "2025-01-20", time: "09:20:06", seconds: 5.12, spanNames: ["stt.transcribe", "llm.call"], cost: null, missing: 2 },
];
const models = [...new Set(rows.map(({ model }) => model))];
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function TracesPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const term = query.toLowerCase();
  const model = models.find((value) => value === params.model) ?? "";
  const status = params.status === "完了" || params.status === "エラー" ? params.status : "";
  const kind = params.kind === "音声" || params.kind === "テキスト" ? params.kind : "";
  const date = typeof params.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(params.date) ? params.date : "";
  const sort = params.sort === "duration" || params.sort === "cost" ? params.sort : "latest";

  const matching = rows.filter((row) =>
    (!term || [row.id, row.sessionId, ...row.spanNames].some((value) => value.toLowerCase().includes(term))) &&
    (!model || row.model === model) && (!status || row.status === status) &&
    (!kind || row.kind === kind) && (!date || row.date === date)
  );
  if (sort === "duration") matching.sort((a, b) => b.seconds - a.seconds);
  if (sort === "cost") matching.sort((a, b) => (b.cost ?? -1) - (a.cost ?? -1));

  return <div className="shell">
    <Sidebar section="traces" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><GitBranch size={27} /></span><div>
          <h1>トレース一覧</h1><p>セッションを横断して処理の所要時間、コスト、エラーを確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form action="/traces" className="observation-filters">
            <label>ID・スパン名<input name="q" type="search" placeholder="Trace ID、Session ID、スパン名" defaultValue={query} /></label>
            <label>モデル<select name="model" defaultValue={model}><option value="">すべて</option>{models.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>種別<select name="kind" defaultValue={kind}><option value="">すべて</option><option>音声</option><option>テキスト</option></select></label>
            <label>状態<select name="status" defaultValue={status}><option value="">すべて</option><option>完了</option><option>エラー</option></select></label>
            <label>開始日（JST）<input name="date" type="date" defaultValue={date} /></label>
            <label>並び順<select name="sort" defaultValue={sort}><option value="latest">新しい順</option><option value="duration">所要時間が長い順</option><option value="cost">コストが高い順</option></select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/traces">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>検索結果</h2><span>{matching.length} 件</span></div>
          {matching.length === 0 ? <p className="observation-list-empty">一致するトレースがありません。</p> :
            <div className="table-wrap"><table aria-label="トレース検索結果">
              <thead><tr>{["トレースID", "セッションID", "開始日時（JST）", "種別", "モデル", "所要時間", "計測コスト小計（USD）", "状態"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{matching.map((row) => <tr key={row.id}>
                <td>{row.id === demoTraceId ? <Link href={`/traces/${row.id}`}>{row.id}</Link> : row.id}</td>
                <td>{row.sessionId === relatedSessionId ? <Link href={`/sessions/${row.sessionId}`}>{row.sessionId}</Link> : row.sessionId}</td>
                <td>{row.date.replaceAll("-", "/")} {row.time}</td><td>{row.kind}</td><td>{row.model}</td>
                <td>{row.seconds.toFixed(2)} s</td>
                <td>{formatUsd(row.cost)}{row.missing > 0 && <small> · 未計測 {row.missing} 件</small>}</td>
                <td><span className="status" data-evaluation={row.status === "エラー" ? "評価失敗" : "評価完了"}>{row.status}</span></td>
              </tr>)}</tbody>
            </table></div>}
        </section>
      </div>
    </main>
  </div>;
}
