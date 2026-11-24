import { sessions } from "../demo-data";

export const demoSessionId = sessions[0].id;

export const session = {
  id: demoSessionId,
  startedAt: "2025/01/21 14:32 JST",
  duration: "6分28秒",
  model: sessions[0].model,
  agentConfig: "v12",
  evaluatorConfig: "v5",
  application: "voice-agent-dev",
  score: sessions[0].score,
  labels: ["施設案内", "営業時間"],
  turns: [
    { time: "00:00", elapsed: "00:07", tokens: 182, costUsd: 0.0008, status: "完了", speaker: "ユーザー", text: "初めて利用します。受付時間と、予約が必要か教えてください。" },
    { time: "00:08", elapsed: "00:14", tokens: 1642, costUsd: 0.0076, status: "完了", speaker: "エージェント", text: "受付は平日の9時から17時までです。見学をご希望の場合は、事前の予約をお願いします。予約方法もご案内しましょうか？" },
    { time: "00:24", elapsed: "00:05", tokens: 317, costUsd: 0.0017, status: "完了", speaker: "ユーザー", text: "はい、電話で予約する方法を教えてください。" },
    { time: "00:30", elapsed: "00:18", tokens: 2391, costUsd: 0.0109, status: "完了", speaker: "エージェント", text: "受付時間内に窓口にお電話いただき、ご希望の日時と人数をお伝えください。担当者が空き状況を確認します。" },
  ],
  metrics: [
    { name: "回答の関連性", score: 0.92 },
    { name: "タスク達成度", score: 0.9 },
    { name: "事実性（Faithfulness）", score: 0.87 },
    { name: "文脈の関連性", score: 0.88 },
    { name: "応答の自然さ（音声）", score: null },
    { name: "発話の聞き取りやすさ", score: null },
  ],
  tools: [
    { name: "search_knowledge", time: "00:11", description: "案内資料から受付時間を取得" },
    { name: "search_memories", time: "00:27", description: "案内方法の希望を検索" },
  ],
} as const;
