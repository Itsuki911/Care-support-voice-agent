const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

function load(fetch, exportName = "getDashboard") {
  const source = fs.readFileSync(require('node:path').join(__dirname, '../app/dashboard-data.ts'), 'utf8').replace('import "server-only";', '');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, require, process: { env: { LANGFUSE_BASE_URL: 'https://example.test', LANGFUSE_PUBLIC_KEY: 'pk', LANGFUSE_SECRET_KEY: 'sk' } }, Buffer, fetch, URL, AbortSignal, Date, Intl, Map, Set, Number });
  return exports[exportName];
}

test('ページをまたぐ実測値の集計と欠損値', async () => {
  const now = new Date().toISOString();
  const calls = [];
  const get = load(async url => {
    calls.push(url);
    const observation = url.pathname.endsWith('observations');
    const cursor = url.searchParams.get('cursor');
    const data = observation ? (cursor ? [{ sessionId: 's1', traceId: 't1', startTime: now, type: 'GENERATION', model: 'model', totalCost: 0.04 }] : [{ sessionId: 's1', traceId: 't1', startTime: now }, { sessionId: 's2', traceId: 't2', startTime: now }]) : [{ name: 'secretary.final_answer_accuracy', value: 0.8, dataType: 'NUMERIC', timestamp: now, subject: { kind: 'trace', id: 't1' } }, { name: 'text.conv.task_completion', value: 0.6, dataType: 'NUMERIC', timestamp: now, subject: { kind: 'trace', id: 't1' } }, { name: 'other.score', value: 1, dataType: 'NUMERIC', timestamp: now }];
    return { ok: true, json: async () => ({ data, meta: observation && !cursor ? { cursor: 'next' } : {} }) };
  });
  const result = await get();
  assert.equal(result.connected, true);
  assert.equal(result.count, 2);
  assert.equal(result.average, 0.7);
  assert.equal(result.cost, 0.04);
  assert.equal(result.sessions.find(s => s.id === 's1').score, 0.7);
  assert.equal(result.sessions.find(s => s.id === 's2').score, null);
  assert.equal(calls.filter(u => u.pathname.endsWith('observations')).length, 2);
  assert.equal(calls[0].searchParams.get('fields').includes('io'), false);
});

test('接続失敗時は実測値を捏造しない', async () => {
  const result = await load(async () => ({ ok: false }))();
  assert.equal(result.connected, false);
  assert.equal(result.average, null);
  assert.equal(result.cost, null);
  assert.equal(result.sessions.length, 0);
});

test('選択した日付の JST 境界で取得し、期間内のスコアだけ集計する', async () => {
  const calls = [];
  const get = load(async url => {
    calls.push(url);
    const scores = [
      { name: 'secretary.test', value: 0.4, dataType: 'NUMERIC', timestamp: '2026-01-01T15:00:00Z' },
      { name: 'secretary.test', value: 0.8, dataType: 'NUMERIC', timestamp: '2026-01-03T14:59:59Z' },
      { name: 'secretary.test', value: 1, dataType: 'NUMERIC', timestamp: '2026-01-03T15:00:00Z' },
    ];
    return { ok: true, json: async () => ({ data: url.pathname.endsWith('scores') ? scores : [], meta: {} }) };
  });
  const result = await get('2026-01-02', '2026-01-03');
  const observationUrl = calls.find(url => url.pathname.endsWith('observations'));
  assert.equal(observationUrl.searchParams.get('fromStartTime'), '2026-01-01T15:00:00.000Z');
  assert.equal(observationUrl.searchParams.get('toStartTime'), '2026-01-03T15:00:00.000Z');
  assert.ok(Math.abs(result.average - 0.6) < 0.00001);
  assert.equal(result.trend.length, 2);
  assert.equal(result.trend[0].quality, 0.4);
  assert.equal(result.trend[1].quality, 0.8);
});


test('観測 API の応答から接続状態を判定する', async () => {
  const check = load(async url => {
    assert.equal(url.pathname, '/api/public/v2/observations');
    assert.equal(url.searchParams.get('limit'), '1');
    assert.equal(url.searchParams.get('fields'), 'core');
    return { ok: true, status: 200, json: async () => ({ data: [] }) };
  }, 'checkLangfuseConnection');
  assert.equal((await check()).state, 'connected');
  assert.equal((await load(async () => ({ ok: false, status: 401 }), 'checkLangfuseConnection')()).state, 'unauthorized');
  assert.equal((await load(async () => { throw new Error('network'); }, 'checkLangfuseConnection')()).state, 'unavailable');
  assert.equal((await load(async () => ({ ok: true, status: 200, json: async () => ({}) }), 'checkLangfuseConnection')()).state, 'unavailable');
});
