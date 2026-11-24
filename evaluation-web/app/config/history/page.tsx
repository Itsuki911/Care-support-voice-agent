import Link from "next/link";
import { Clock3, Search } from "lucide-react";
import Sidebar from "../../sidebar";
import { active, versions } from "../agent/demo-settings";
import "../../observation-list.css";
import "../evaluator/evaluator.css";

export const metadata = { title: "設定バージョン履歴 | Voice Agent Lab" };

const entries = [
  ...versions.map((version) => ({
    id: version.id, type: "Agent", href: "/config/agent", date: version.date,
    author: version.author, state: version.id === active.id ? "適用中" : "旧版",
    summary: version.description,
  })),
  { id: "v5", type: "評価", href: "/config/evaluator", date: "2025/01/21 10:10", author: "suzuki", state: "適用中", summary: "通常評価の Judge モデルと指標セットを更新しました。" },
  { id: "v3", type: "安全性", href: "/config/safety", date: "2025/01/20 11:00", author: "tanaka", state: "適用中", summary: "既定のレビュー担当とマスキング済みレポートの保持期間を設定しました。" },
  { id: "v2", type: "観測", href: "/config/observability", date: "2025/01/20 09:45", author: "suzuki", state: "適用中", summary: "通常トレースの取得率とログの保持期間を設定しました。" },
].sort((a, b) => b.date.localeCompare(a.date));

const types = [...new Set(entries.map((entry) => entry.type))];
const states = ["適用中", "旧版"];
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function ConfigHistoryPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const type = types.find((option) => option === params.type) ?? "";
  const state = states.find((option) => option === params.state) ?? "";
  const term = query.toLowerCase();
  const rows = entries.filter((entry) =>
    (!type || entry.type === type) && (!state || entry.state === state) &&
    [entry.id, entry.author, entry.summary].some((value) => value.toLowerCase().includes(term))
  );

  return <div className="shell">
    <Sidebar section="config-history" />
    <main className="observation-list">
      <header>
        <div className="heading"><span className="home"><Clock3 size={27} /></span><div>
          <h1>設定バージョン履歴</h1><p>設定ごとの変更内容と適用状態を確認します。</p>
        </div></div>
        <div className="environment">環境 <strong>Development</strong><span>モックデータ</span></div>
      </header>
      <div className="content">
        <section className="card panel">
          <h2>検索条件</h2>
          <form key={JSON.stringify([query, type, state])} action="/config/history" className="observation-filters">
            <label>バージョン・更新者・変更概要<input type="search" name="q" placeholder="v12、tanaka など" defaultValue={query} /></label>
            <label>設定種別<select name="type" defaultValue={type}><option value="">すべて</option>{types.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>状態<select name="state" defaultValue={state}><option value="">すべて</option>{states.map((option) => <option key={option}>{option}</option>)}</select></label>
            <div className="observation-filter-actions"><button type="submit"><Search size={16} /> 検索</button><Link href="/config/history">条件を解除</Link></div>
          </form>
        </section>
        <section className="card panel">
          <div className="panel-heading"><h2>バージョン</h2><span>{rows.length} 件</span></div>
          {rows.length === 0 ? <p className="observation-list-empty">一致する設定バージョンがありません。</p> :
            <div className="table-wrap"><table aria-label="設定バージョン履歴">
              <thead><tr>{["設定種別", "バージョン", "状態", "更新日時（JST）", "更新者", "変更概要", "関連設定"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{rows.map(({ id, type, href, date, author, state, summary }) => <tr key={`${type}-${id}`}>
                <td>{type}</td><td><strong>{id}</strong></td><td><span className="status" data-evaluation={state === "適用中" ? "評価完了" : undefined}>{state}</span></td>
                <td>{date}</td><td>{author}</td><td style={{ whiteSpace: "normal", minWidth: 190 }}>{summary}</td><td><Link href={href}>{type}設定を開く</Link></td>
              </tr>)}</tbody>
            </table></div>}
          <p className="evaluator-caption">関連設定のリンクから現在の設定を開きます。版の適用・ロールバックは未接続です。</p>
        </section>
      </div>
    </main>
  </div>;
}
