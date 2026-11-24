import Sidebar from "../../sidebar";
import AgentSettings from "./settings-view";
import "./settings.css";

export const metadata = { title: "Agent設定 | Voice Agent Lab" };

export default function AgentSettingsPage() {
  return <div className="shell">
    <Sidebar section="agent-config" />
    <AgentSettings />
  </div>;
}
