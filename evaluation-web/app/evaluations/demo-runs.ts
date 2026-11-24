import { session } from "../sessions/demo-session";
import { demoTraceId } from "../traces/demo-trace";

export const runs = [
  { id: "eval_demo_004", target: session.id, kind: "セッション", trigger: "自動", version: session.evaluatorConfig, time: "2025/01/21 14:40", status: "完了", score: session.score, judge: "gpt-4o-mini", seconds: 8.42, cost: 0.0048, tokens: 1450, retries: 0, outputValid: true },
  { id: "eval_demo_003", target: demoTraceId, kind: "トレース", trigger: "手動", version: session.evaluatorConfig, time: "2025/01/21 14:35", status: "実行中", score: null, judge: "gpt-4o-mini", seconds: null, cost: null, tokens: null, retries: 0, outputValid: null },
  { id: "eval_demo_002", target: "dataset_demo_voice_v2", kind: "データセット", trigger: "手動", version: "v4", time: "2025/01/21 10:15", status: "待機中", score: null, judge: "gpt-4o", seconds: null, cost: null, tokens: null, retries: 0, outputValid: null },
  { id: "eval_demo_001", target: "sess_demo_voice", kind: "セッション", trigger: "自動", version: "v4", time: "2025/01/20 09:22", status: "実行失敗", score: null, judge: "gpt-4o", seconds: 12.6, cost: 0.0062, tokens: 1800, retries: 1, outputValid: false },
];
