import { describe, expect, it } from 'vitest';

import {
  applyStatusEvent,
  applyTranscriptEvent,
  finalizeActiveStatusEvents,
  formatStatusLabel,
  getStatusBadgeText,
  isActiveStatus,
  type AgentStatusEvent,
  type TranscriptEvent,
  type VoiceUIMessage,
} from './protocol';

describe('applyTranscriptEvent', () => {
  it('updates interim transcript in place without adding duplicate rows', () => {
    let messages: VoiceUIMessage[] = [];
    const e1: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      utterance_id: 'utt-1',
      seq: 1,
      speaker: 'user',
      timestamp: 100,
      status: 'interim',
      text: '明日の',
    };
    const e2: TranscriptEvent = {
      ...e1,
      seq: 2,
      status: 'final',
      text: '明日の予定を教えて',
    };

    messages = applyTranscriptEvent(messages, e1, 'room-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].metadata?.status).toBe('interim');

    messages = applyTranscriptEvent(messages, e2, 'room-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].parts[0]).toEqual({ type: 'text', text: '明日の予定を教えて' });
    expect(messages[0].metadata?.status).toBe('final');
  });

  it('uses spoken_text on interruption and ignores stale or cross-session events', () => {
    let messages: VoiceUIMessage[] = [];
    const interrupted: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      utterance_id: 'utt-asst-1',
      seq: 5,
      speaker: 'assistant',
      timestamp: 101,
      status: 'interrupted',
      text: '明日の予定は',
      spoken_text: '明日の予定は',
      generated_text: '明日の予定は午前10時に会議があります。',
    };

    messages = applyTranscriptEvent(messages, interrupted, 'room-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].parts[0]).toEqual({ type: 'text', text: '明日の予定は' });
    expect(messages[0].metadata?.status).toBe('interrupted');
    expect(messages[0].metadata?.generatedText).toBe('明日の予定は午前10時に会議があります。');

    // Duplicate/older seq or stale interim must be ignored.
    messages = applyTranscriptEvent(
      messages,
      { ...interrupted, seq: 4, status: 'interim', spoken_text: '古い' },
      'room-1',
    );
    expect(messages[0].parts[0]).toEqual({ type: 'text', text: '明日の予定は' });

    // Different session_id must never mix into the active session.
    messages = applyTranscriptEvent(
      messages,
      { ...interrupted, session_id: 'room-other', utterance_id: 'utt-other', seq: 1 },
      'room-1',
    );
    expect(messages).toHaveLength(1);
  });

  it('merges multi-clause user turn updates and reconciles streaming assistant message with final commit', () => {
    let messages: VoiceUIMessage[] = [];
    // Clause 1 final, followed by Clause 2 interim and final, then conversation_item_added commit
    const u1: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      utterance_id: 'utt-user-1',
      seq: 1,
      speaker: 'user',
      timestamp: 100,
      status: 'final',
      text: 'えーと、Gメールツールを使って。',
    };
    const u2Interim: TranscriptEvent = {
      ...u1,
      seq: 2,
      status: 'interim',
      text: 'えーと、Gメールツールを使って。 今日の',
    };
    const u2Final: TranscriptEvent = {
      ...u1,
      seq: 3,
      status: 'final',
      text: 'えーと、Gメールツールを使って。 今日の。',
    };

    messages = applyTranscriptEvent(messages, u1, 'room-1');
    messages = applyTranscriptEvent(messages, u2Interim, 'room-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].metadata?.status).toBe('interim');
    messages = applyTranscriptEvent(messages, u2Final, 'room-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].parts[0]).toEqual({
      type: 'text',
      text: 'えーと、Gメールツールを使って。 今日の。',
    });
    expect(messages[0].metadata?.status).toBe('final');

    // Assistant streams via lk.transcription, then commits via conversation_item_added
    const aStream: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'room-1',
      turn_id: 'stream',
      utterance_id: 'lk-SG_1',
      seq: 1,
      speaker: 'assistant',
      timestamp: 101,
      status: 'interim',
      text: '最新のメールを',
      spoken_text: '最新のメールを',
    };
    const aCommit: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      utterance_id: 'item_asst_1',
      seq: 4,
      speaker: 'assistant',
      timestamp: 102,
      status: 'final',
      text: '最新のメールを確認します。',
      spoken_text: '最新のメールを確認します。',
      generated_text: '最新のメールを確認します。',
    };

    messages = applyTranscriptEvent(messages, aStream, 'room-1');
    expect(messages).toHaveLength(2);
    messages = applyTranscriptEvent(messages, aCommit, 'room-1');
    expect(messages).toHaveLength(2);
    expect(messages[1].parts[0]).toEqual({ type: 'text', text: '最新のメールを確認します。' });
    expect(messages[1].metadata?.status).toBe('final');

    // Late interim chunk from lk.transcription must not revert final status
    messages = applyTranscriptEvent(
      messages,
      { ...aStream, seq: 99, status: 'interim', text: '最新のメールを' },
      'room-1',
    );
    expect(messages).toHaveLength(2);
    expect(messages[1].metadata?.status).toBe('final');
  });

  it('reconciles optimistic client text message with authoritative server transcript_event without duplication', () => {
    let messages: VoiceUIMessage[] = [
      {
        id: 'client-msg-1',
        role: 'user',
        parts: [{ type: 'text', text: 'テキストセッションの質問です' }],
      },
    ];
    const serverCommit: TranscriptEvent = {
      type: 'transcript_event',
      session_id: 'frontend-test-text-1',
      turn_id: 'turn-1',
      utterance_id: 'item_user_1',
      seq: 1,
      speaker: 'user',
      timestamp: 200,
      status: 'final',
      text: 'テキストセッションの質問です',
    };

    messages = applyTranscriptEvent(messages, serverCommit, 'frontend-test-text-1');
    expect(messages).toHaveLength(1);
    expect(messages[0].metadata?.status).toBe('final');
    expect(messages[0].metadata?.utteranceId).toBe('item_user_1');
    expect(messages[0].metadata?.turnId).toBe('turn-1');
  });
});

describe('applyStatusEvent', () => {
  it('tracks status by execution_id and ignores stale sequence or other sessions', () => {
    let events: AgentStatusEvent[] = [];
    const ev1: AgentStatusEvent = {
      type: 'agent_status_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      execution_id: 'exec-1',
      kind: 'tool',
      status: 'pending',
      seq: 1,
      timestamp: 100,
      label: 'search_emails',
    };
    events = applyStatusEvent(events, ev1, 'room-1');
    events = applyStatusEvent(events, { ...ev1, seq: 2, status: 'executed' }, 'room-1');
    events = applyStatusEvent(events, { ...ev1, seq: 1, status: 'pending' }, 'room-1');
    events = applyStatusEvent(events, { ...ev1, session_id: 'room-2', execution_id: 'exec-2' }, 'room-1');

    expect(events).toHaveLength(1);
    expect(events[0].status).toBe('executed');
  });

  it('finalizes active statuses on disconnect and formats custom progress labels', () => {
    const running: AgentStatusEvent = {
      type: 'agent_status_event',
      session_id: 'room-1',
      turn_id: 'turn-1',
      execution_id: 'web-1',
      kind: 'web_search',
      status: 'running',
      seq: 1,
      timestamp: 100,
      label: '',
    };
    const done: AgentStatusEvent = {
      ...running,
      execution_id: 'mem-1',
      kind: 'memory',
      status: 'completed',
      seq: 2,
      label: '記憶の検索完了',
    };
    expect(isActiveStatus(running.status)).toBe(true);
    expect(formatStatusLabel(running)).toBe('Web を検索中…');
    expect(getStatusBadgeText(running.status)).toBe('実行中');

    const finalized = finalizeActiveStatusEvents([running, done]);
    expect(finalized[0].status).toBe('cancelled');
    expect(finalized[1].status).toBe('completed');
    expect(getStatusBadgeText(finalized[0].status)).toBe('キャンセル');
  });
});
