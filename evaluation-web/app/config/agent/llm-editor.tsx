import { Bot, Check, Cpu, Info, Lightbulb, Plus, Save, Sparkles } from "lucide-react";
import { modelOptions, numericFields, validateLlm, type LlmSettings, type NumericKey } from "./llm-settings";

type Props = {
  value: LlmSettings;
  version: string;
  editing: boolean;
  message: string;
  onEdit: () => void;
  onSave: () => void;
  onChange: (value: LlmSettings) => void;
  onBasic: () => void;
};

const mainFields: NumericKey[] = ["temperature", "maxTokens", "topP", "frequencyPenalty", "presencePenalty"];

export default function LlmEditor({ value, version, editing, message, onEdit, onSave, onChange, onBasic }: Props) {
  const models = modelOptions[value.provider];
  const supportsAdvanced = value.provider === "OpenAI";
  const invalid = editing ? validateLlm(value) : undefined;

  function numberField(key: NumericKey, slider = false) {
    const { label, min, max, step } = numericFields[key];
    return <div className="llm-row" key={key}>
      <label htmlFor={`llm-${key}`} title={`モックの範囲 ${min}〜${max}`}>{label}</label>
      <div className={slider ? "llm-range" : undefined}>
        {slider && <input type="range" aria-label={`${label} スライダー`} min={min} max={max} step={step} value={value[key] || min} disabled={!editing} onChange={(event) => onChange({ ...value, [key]: event.target.value })} />}
        <input id={`llm-${key}`} type="number" min={min} max={max} step={step} required value={value[key]} readOnly={!editing} onChange={(event) => onChange({ ...value, [key]: event.target.value })} />
      </div>
    </div>;
  }

  return <main className="agent-main">
    <header className="agent-header llm-header">
      <div className="heading"><div className="home"><Bot size={29} /></div><div><h1>Agent設定</h1><p>応答生成に使用する LLM を設定します。</p></div></div>
      <div className="llm-header-actions">
        <span>設定バージョン <strong>{version}</strong></span>
        {!editing && <button className="agent-button" type="button" onClick={onEdit}><Plus size={16} /> ドラフトを編集</button>}
        <button className="agent-button agent-primary" type="submit" form="llm-form" disabled={!editing}><Save size={16} /> ドラフトとして保存</button>
      </div>
    </header>
    <nav className="agent-tabs" aria-label="設定カテゴリ">
      <button type="button" onClick={onBasic}>基本設定</button>
      <button type="button" aria-current="page" aria-pressed="true" disabled>LLM</button>
    </nav>
    <div className="llm-grid">
      <section className="card agent-card llm-editor">
        <div className="heading"><span className="icon purple"><Sparkles size={23} /></span><div><h2>LLM設定</h2><p>モデルと生成パラメーター（モックデータ）</p></div></div>
        <form id="llm-form" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
          <div className="llm-row"><label htmlFor="llm-provider">プロバイダー</label><div>
            <select id="llm-provider" value={value.provider} disabled={!editing} onChange={(event) => {
              const provider = event.target.value as LlmSettings["provider"];
              onChange({ ...value, provider, model: modelOptions[provider][0], responseFormat: "text" });
            }}>{Object.keys(modelOptions).map((provider) => <option key={provider}>{provider}</option>)}</select>
            <p>APIキーの状態は未確認です。</p>
          </div></div>
          <div className="llm-row"><label htmlFor="llm-model">モデル</label>
            <select id="llm-model" value={value.model} disabled={!editing} onChange={(event) => onChange({ ...value, model: event.target.value })}>
              {models.map((model) => <option key={model}>{model}</option>)}
            </select>
          </div>
          {mainFields.filter((key) => supportsAdvanced || (key !== "frequencyPenalty" && key !== "presencePenalty")).map((key) => numberField(key, key !== "maxTokens"))}
          <details className="llm-advanced" open>
            <summary>詳細設定</summary>
            <div className="llm-advanced-grid">
              {numberField("timeout")}
              {numberField("retries")}
              <label className="llm-check"><input type="checkbox" checked={value.streaming} disabled={!editing} onChange={(event) => onChange({ ...value, streaming: event.target.checked })} /> ストリーミング</label>
              {supportsAdvanced && <div className="llm-row"><label htmlFor="llm-format">レスポンス形式</label><select id="llm-format" disabled={!editing} value={value.responseFormat} onChange={(event) => onChange({ ...value, responseFormat: event.target.value === "json" ? "json" : "text" })}><option value="text">テキスト</option><option value="json">JSON</option></select></div>}
            </div>
          </details>
          <p className="llm-feedback" role="status">{invalid || message || (editing ? "ドラフトを編集中です。" : "変更はドラフトで行います。")}</p>
        </form>
      </section>
      <div className="agent-stack">
        <section className="card agent-card"><h2>設定の概要</h2>
          <div className="llm-summary"><strong><Cpu size={20} /> {value.model}</strong>
            <dl>{[["温度", value.temperature], ["最大出力トークン", value.maxTokens ? Number(value.maxTokens).toLocaleString("ja-JP") : ""], ["トップP", value.topP]].map(([label, text]) => <div key={label}><dt>{label}</dt><dd>{text || "N/A"}</dd></div>)}</dl>
          </div>
          <div className="llm-note"><Info size={17} /><div><strong>推定コスト（USD / 1K トークン）</strong><p>入力 N/A ・ 出力 N/A</p></div></div>
        </section>
        <section className="card agent-card"><h2>モデルの比較</h2>
          <div className="table-wrap"><table className="llm-models"><thead><tr>{["モデル", "品質", "レイテンシ", "出力コスト"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{models.map((model) => <tr key={model}><td><label><input type="radio" name="llm-model-choice" checked={model === value.model} disabled={!editing} onChange={() => onChange({ ...value, model })} />{model}</label></td><td>N/A</td><td>N/A</td><td>N/A</td></tr>)}</tbody>
          </table></div><p>比較可能な実測値と価格データは未取得です。</p>
        </section>
        <section className="card agent-card llm-impact"><Lightbulb size={20} /><div><h2>変更の影響</h2><p>モデルや生成パラメーターは応答品質、コスト、レイテンシに影響します。</p><p><Check size={14} /> ドラフトはこの画面内で保持します。</p></div></section>
      </div>
    </div>
  </main>;
}
