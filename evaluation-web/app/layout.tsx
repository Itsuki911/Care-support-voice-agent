import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./style.css";

export const metadata: Metadata = {
  title: "ダッシュボード | Voice Agent Lab",
  description: "音声Agentの評価・観測ダッシュボード",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="ja"><body>{children}</body></html>;
}
