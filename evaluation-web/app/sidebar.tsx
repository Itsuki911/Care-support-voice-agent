import Link from "next/link";
import { AudioLines, BarChart3, Clock3, Database, FileText, House, MessageCircle, Settings, Shield, SlidersHorizontal, Tag, TrendingUp } from "lucide-react";

const groups = [
  { label: "観測・分析", items: [[MessageCircle, "セッション"], [TrendingUp, "トレース"], [BarChart3, "評価結果"]] },
  { label: "安全性評価", items: [[Shield, "Safety Evaluation"]] },
  { label: "設定管理", items: [[SlidersHorizontal, "Agent設定"], [FileText, "評価設定（DeepEval）"], [Shield, "安全性設定"]] },
  { label: "データ管理", items: [[Database, "データセット"]] },
  { label: "その他", items: [[Tag, "アノテーション"], [Clock3, "実行履歴"]] },
] as const;

export default function Sidebar({ section }: { section: "dashboard" | "sessions" }) {
  return (
      <aside>
        <div className="brand"><AudioLines size={42} /> <span>{section === "sessions" ? "Voice Agent Lab" : <>Voice Agent<br />Evaluation Platform</>}</span></div>
        <nav aria-label="管理画面">
          <Link className={section === "dashboard" ? "current" : "nav-item"} href="/" aria-current={section === "dashboard" ? "page" : undefined}><House /> ダッシュボード</Link>
          {groups.map(({ label, items }) => (
            <div className="nav-group" key={label}>
              <div className="nav-label">{label}</div>
              {items.map(([Icon, name]) => <div className={section === "sessions" && name === "セッション" ? "current" : "nav-item"} key={name}><Icon />{name}</div>)}
            </div>
          ))}
        </nav>
        <div className="nav-footer"><Settings size={20} /> 設定</div>
      </aside>
  );
}
