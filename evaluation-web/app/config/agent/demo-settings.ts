export type AgentBasics = { name: string; description: string; tags: string[] };

const name = "施設案内エージェント（開発環境）";
export const versions = [
  { id: "v12", date: "2025/01/21 10:24", author: "tanaka", name, description: "受付時間と見学予約をご案内する音声Agentです。RAG・メモリ・承認付きツールを利用します。", tags: ["施設案内", "音声", "RAG"] },
  { id: "v11", date: "2025/01/18 16:42", author: "suzuki", name, description: "受付時間と見学予約をご案内する音声Agentです。", tags: ["施設案内", "音声"] },
  { id: "v10", date: "2025/01/15 09:17", author: "tanaka", name, description: "受付時間をご案内する音声Agentです。", tags: ["施設案内", "音声"] },
  { id: "v9", date: "2025/01/10 13:06", author: "suzuki", name, description: "施設の受付情報をご案内します。", tags: ["施設案内"] },
  { id: "v8", date: "2025/01/08 11:20", author: "tanaka", name: "施設案内エージェント", description: "施設案内の初期設定です。", tags: [] },
];

export const active = versions[0];

export function basics({ name, description, tags }: AgentBasics): AgentBasics {
  return { name, description, tags };
}
