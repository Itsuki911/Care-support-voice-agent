import { notFound } from "next/navigation";
import Sidebar from "../../sidebar";
import { demoSessionId } from "../demo-session";
import SessionView from "./session-view";
import "./session.css";

export const metadata = { title: "セッション詳細 | Voice Agent Lab" };

export default async function SessionPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string | string[] }> }) {
  const { id } = await params;
  if (id !== demoSessionId) notFound();

  const initialView = (await searchParams).tab === "evaluation" ? "評価結果" : "会話";

  return (
    <div className="shell">
      <Sidebar section="sessions" />
      <SessionView key={initialView} initialView={initialView} />
    </div>
  );
}
