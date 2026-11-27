import Sidebar from "../../sidebar";
import AgentSettings from "./settings-view";
import { getMemoryOverview, getModelComparisons, getRuntimeSettings } from "./runtime-data";
import "./settings.css";

export const dynamic = "force-dynamic";
export const metadata = { title: "Agent設定 | Voice Agent Lab" };
export default async function AgentSettingsPage() {
  const settings = getRuntimeSettings();
  const [comparisons, memory] = await Promise.all([getModelComparisons(), getMemoryOverview()]);
  return <div className="shell"><Sidebar section="agent-config" /><AgentSettings settings={settings} comparisons={comparisons} memory={memory} /></div>;
}
