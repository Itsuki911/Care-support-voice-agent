import { notFound } from "next/navigation";
import Sidebar from "../../sidebar";
import { demoTraceId } from "../demo-trace";
import TraceView from "./trace-view";
import "./trace.css";

export const metadata = { title: "トレース詳細 | Voice Agent Lab" };

export default async function TracePage({ params }: { params: Promise<{ id: string }> }) {
  if ((await params).id !== demoTraceId) notFound();

  return <div className="shell">
    <Sidebar section="traces" />
    <TraceView />
  </div>;
}
