import { demoSessionId } from "../sessions/demo-session";

export const demoTraceId = "trace_8f3a2c9e";
export const relatedSessionId = demoSessionId;

export type Span = {
  id: string;
  name: string;
  description: string;
  start: string;
  duration: number;
  tokens: number | null;
  cost: number | null;
  children?: Span[];
};

export const root: Span = {
  id: "run", name: "voice_agent_run", description: "音声Agentの実行（全体）",
  start: "14:32:08.000", duration: 12.84, tokens: 3408, cost: null,
  children: [
    { id: "stt", name: "stt.transcribe", description: "音声をテキストに変換", start: "14:32:08.012", duration: 1.26, tokens: null, cost: 0.002 },
    {
      id: "step1", name: "agent.step.1", description: "ユーザー発話の理解と応答生成",
      start: "14:32:09.289", duration: 4.72, tokens: 1536, cost: null,
      children: [
        { id: "llm1", name: "llm.call (gpt-4o)", description: "応答の生成", start: "14:32:09.311", duration: 2.81, tokens: 1536, cost: 0.0076 },
        {
          id: "tool", name: "tool.search_knowledge", description: "案内資料から受付時間を取得",
          start: "14:32:12.142", duration: 1.17, tokens: null, cost: null,
          children: [
            { id: "retriever", name: "retriever.query", description: "ベクトル検索（pgvector）", start: "14:32:12.158", duration: 0.63, tokens: null, cost: null },
            { id: "rerank", name: "rerank", description: "検索結果の並べ替え", start: "14:32:12.805", duration: 0.49, tokens: null, cost: null },
          ],
        },
      ],
    },
    {
      id: "step2", name: "agent.step.2", description: "検索結果をもとに最終応答を生成",
      start: "14:32:14.009", duration: 2.91, tokens: 1872, cost: null,
      children: [
        { id: "llm2", name: "llm.call (gpt-4o)", description: "最終応答の生成", start: "14:32:14.030", duration: 2.69, tokens: 1872, cost: 0.0092 },
      ],
    },
    { id: "tts", name: "tts.synthesize", description: "テキストを音声に変換", start: "14:32:16.925", duration: 1.87, tokens: null, cost: 0.0052 },
    { id: "stream", name: "response.stream", description: "音声ストリーミング出力", start: "14:32:18.800", duration: 0.21, tokens: null, cost: 0 },
  ],
};

export function flatten(span: Span, depth = 0): { span: Span; depth: number }[] {
  return [{ span, depth }, ...(span.children ?? []).flatMap((child) => flatten(child, depth + 1))];
}

export const spans = flatten(root);

const leaves = spans.filter(({ span }) => !span.children);
export const traceCostSubtotal = leaves.reduce((total, { span }) => total + (span.cost ?? 0), 0);
export const unmeasuredLeafCount = leaves.filter(({ span }) => span.cost === null).length;
