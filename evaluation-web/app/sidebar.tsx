import Link from "next/link";
import { Activity, AudioLines, BarChart3, Clock3, Database, FileText, House, MessageCircle, Settings, Shield, SlidersHorizontal, Tag, TrendingUp } from "lucide-react";

const groups = [
  { label: "観測・分析", items: [[MessageCircle, "セッション"], [TrendingUp, "トレース"], [BarChart3, "評価結果"], [BarChart3, "評価モニタリング"]] },
  { label: "安全性評価", items: [[Shield, "Safety Evaluation"]] },
  { label: "設定管理", items: [[SlidersHorizontal, "Agent設定"], [FileText, "評価設定（DeepEval）"], [Shield, "安全性設定"], [Activity, "観測設定"], [Clock3, "設定バージョン履歴"]] },
  { label: "データ管理", items: [[Database, "データセット"]] },
  { label: "その他", items: [[Tag, "アノテーション"], [Clock3, "実行履歴"]] },
] as const;

const destinations: Record<string, { section: string; href: string } | undefined> = {
  "セッション": { section: "sessions", href: "/sessions" },
  "トレース": { section: "traces", href: "/traces" },
  "評価モニタリング": { section: "evaluator-monitoring", href: "/evaluators/monitoring" },
  "評価結果": { section: "evaluations", href: "/evaluations" },
  "Safety Evaluation": { section: "safety", href: "/safety" },
  "Agent設定": { section: "agent-config", href: "/config/agent" },
  "評価設定（DeepEval）": { section: "evaluator-config", href: "/config/evaluator" },
  "安全性設定": { section: "safety-config", href: "/config/safety" },
  "観測設定": { section: "observability-config", href: "/config/observability" },
  "設定バージョン履歴": { section: "config-history", href: "/config/history" },
  "データセット": { section: "datasets", href: "/datasets" },
  "アノテーション": { section: "annotations", href: "/annotations" },
};

export default function Sidebar({ section }: { section: "dashboard" | "sessions" | "traces" | "evaluations" | "evaluator-monitoring" | "safety" | "agent-config" | "evaluator-config" | "safety-config" | "observability-config" | "config-history" | "datasets" | "annotations" }) {
  return (
      <aside>
        <div className="brand"><AudioLines size={42} /> <span>{section !== "dashboard" ? "Voice Agent Lab" : <>Voice Agent<br />Evaluation Platform</>}</span></div>
        <nav aria-label="管理画面">
          <Link className={section === "dashboard" ? "current" : "nav-item"} href="/" aria-current={section === "dashboard" ? "page" : undefined}><House /> ダッシュボード</Link>
          {groups.map(({ label, items }) => (
            <div className="nav-group" key={label}>
              <div className="nav-label">{label}</div>
              {items.map(([Icon, name]) => {
                const destination = destinations[name];
                if (!destination) return <div className="nav-item" key={name}><Icon />{name}</div>;
                const active = section === destination.section;
                return <Link key={name} className={active ? "current" : "nav-item"} href={destination.href} aria-current={active ? "page" : undefined}><Icon />{name}</Link>;
              })}
            </div>
          ))}
        </nav>
        <div className="nav-footer"><Settings size={20} /> 設定</div>
      </aside>
  );
}
