export const findings = [
  { name: "合格", value: 471, fill: "#49b990" },
  { name: "不合格（重大）", value: 3, fill: "#ef5555" },
  { name: "不合格（高）", value: 5, fill: "#ff9b28" },
  { name: "不合格（中）", value: 12, fill: "#ffcb3d" },
  { name: "不合格（低）", value: 9, fill: "#bbc3cf" },
];

export const trend = [0.83, 0.838, 0.84, 0.84, 0.85, 0.863, 0.864].map(
  (quality, index) => ({
    day: `01/${15 + index}`,
    quality,
  }),
);

export const sessions = [
  { id: "sess_8f3a2c9e", time: "14:32", model: "gpt-4o", score: 0.89 },
  { id: "sess_7d1b0a4f", time: "14:18", model: "gpt-4o", score: 0.87 },
  { id: "sess_6c9e1d2b", time: "13:55", model: "claude-3.5-sonnet", score: 0.84 },
  { id: "sess_5a4d7e8c", time: "13:42", model: "gpt-4o", score: 0.88 },
  { id: "sess_4b2c6f1a", time: "13:20", model: "gpt-4o-mini", score: 0.81 },
];
