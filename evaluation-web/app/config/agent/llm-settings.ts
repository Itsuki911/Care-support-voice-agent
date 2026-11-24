export const modelOptions = {
  OpenAI: ["gpt-4o", "gpt-4o-mini"],
  OpenRouter: ["openai/gpt-4o", "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
} as const;

export type LlmSettings = {
  provider: keyof typeof modelOptions;
  model: string;
  temperature: string;
  maxTokens: string;
  topP: string;
  frequencyPenalty: string;
  presencePenalty: string;
  timeout: string;
  retries: string;
  streaming: boolean;
  responseFormat: "text" | "json";
};

export const defaultLlm: LlmSettings = {
  provider: "OpenAI", model: "gpt-4o", temperature: "0.3", maxTokens: "4096",
  topP: "1.0", frequencyPenalty: "0.0", presencePenalty: "0.0",
  timeout: "30", retries: "3", streaming: true, responseFormat: "text",
};

export const numericFields = {
  temperature: { label: "温度 (Temperature)", min: 0, max: 2, step: 0.1 },
  maxTokens: { label: "最大出力トークン", min: 1, max: 4096, step: 1 },
  topP: { label: "トップP (Top-p)", min: 0, max: 1, step: 0.1 },
  frequencyPenalty: { label: "頻度ペナルティ", min: -2, max: 2, step: 0.1 },
  presencePenalty: { label: "存在ペナルティ", min: -2, max: 2, step: 0.1 },
  timeout: { label: "リクエストタイムアウト（秒）", min: 1, max: 120, step: 1 },
  retries: { label: "リトライ回数", min: 0, max: 5, step: 1 },
} as const;

export type NumericKey = keyof typeof numericFields;

export function validateLlm(value: LlmSettings) {
  for (const key of Object.keys(numericFields) as NumericKey[]) {
    if (value.provider !== "OpenAI" && (key === "frequencyPenalty" || key === "presencePenalty")) continue;
    const { label, min, max, step } = numericFields[key];
    const raw = value[key].trim();
    const number = Number(raw);
    const steps = (number - min) / step;
    if (!raw || !Number.isFinite(number) || number < min || number > max || Math.abs(steps - Math.round(steps)) > 1e-8) {
      return `${label}は ${min}〜${max} の範囲で ${step} 刻みで入力してください。`;
    }
  }
}
