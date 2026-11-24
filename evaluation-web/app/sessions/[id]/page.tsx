import { notFound } from "next/navigation";
import Sidebar from "../../sidebar";
import { demoSessionId } from "../demo-session";
import SessionView from "./session-view";
import "./session.css";

export const metadata = { title: "セッション詳細 | Voice Agent Lab" };

export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (id !== demoSessionId) notFound();

  return (
    <div className="shell">
      <Sidebar section="sessions" />
      <SessionView />
    </div>
  );
}
