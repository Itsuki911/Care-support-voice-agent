export const severities = [
  { label: "重大", color: "#b42338" },
  { label: "高", color: "#a9500d" },
  { label: "中", color: "#a77506" },
  { label: "低", color: "#526680" },
] as const;

export type SafetyRun = {
  id: string;
  framework: "Inspect AI" | "garak" | "PyRIT";
  started: string;
  target: "LLM 単体" | "Agent 全体（テキスト）";
  config: string;
  seconds: number | null;
  cost: number | null;
  dataset: string;
  result: { passed: number; failed: readonly [number, number, number, number] } | null;
};

export const safetyRuns: SafetyRun[] = [
  { id: "safety_demo_004", target: "Agent 全体（テキスト）", config: "v12", seconds: 182, cost: 0.0621, framework: "Inspect AI", started: "2025/01/21 16:10", dataset: "safety_demo_v3", result: { passed: 191, failed: [1, 2, 4, 2] } },
  { id: "safety_demo_003", target: "LLM 単体", config: "v12", seconds: 96, cost: 0.0334, framework: "garak", started: "2025/01/21 15:30", dataset: "safety_demo_v3", result: { passed: 143, failed: [1, 1, 3, 2] } },
  { id: "safety_demo_002", target: "Agent 全体（テキスト）", config: "v11", seconds: 145, cost: 0.0482, framework: "PyRIT", started: "2025/01/20 14:05", dataset: "safety_demo_v2", result: { passed: 137, failed: [1, 2, 5, 5] } },
  { id: "safety_demo_001", target: "LLM 単体", config: "v11", seconds: null, cost: null, framework: "Inspect AI", started: "2025/01/20 10:20", dataset: "safety_demo_v2", result: null },
];
