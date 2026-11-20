import type { UIMessage } from 'ai';

export type UtteranceStatus = 'interim' | 'final' | 'interrupted';
export type SpeakerRole = 'user' | 'assistant';

export interface TranscriptEvent {
  type: 'transcript_event';
  session_id: string;
  turn_id: string;
  utterance_id: string;
  seq: number;
  speaker: SpeakerRole;
  timestamp: number;
  status: UtteranceStatus;
  text: string;
  generated_text?: string;
  spoken_text?: string;
}

export interface AgentStatusEvent {
  type: 'agent_status_event';
  session_id: string;
  turn_id: string;
  execution_id: string;
  kind: string;
  status: string;
  seq: number;
  timestamp: number;
  label: string;
}

export interface ApprovalRequestPayload {
  type: 'approval_request';
  execution_id: string;
  session_id?: string;
  tool_name: string;
  target: string;
  summary: string;
  reversible: boolean;
}

export interface VoiceMessageMetadata {
  sessionId: string;
  turnId: string;
  utteranceId: string;
  seq: number;
  timestamp: number;
  status: UtteranceStatus;
  spokenText?: string;
  generatedText?: string;
}

export type VoiceUIMessage = UIMessage<VoiceMessageMetadata>;

export function applyTranscriptEvent(
  messages: VoiceUIMessage[],
  event: TranscriptEvent,
  activeSessionId: string | undefined,
): VoiceUIMessage[] {
  if (!activeSessionId || event.session_id !== activeSessionId) {
    return messages;
  }

  const displayText =
    event.speaker === 'assistant' && event.spoken_text !== undefined
      ? event.spoken_text
      : event.text;

  let existingIndex = messages.findIndex(
    (msg) => msg.id === event.utterance_id || msg.metadata?.utteranceId === event.utterance_id,
  );
  if (existingIndex === -1 && event.speaker === 'assistant' && event.status !== 'interim') {
    // Reconcile final/interrupted assistant event from conversation_item_added
    // with an in-progress lk.transcription streaming bubble in the same session.
    existingIndex = messages.findIndex(
      (msg) =>
        msg.role === 'assistant' &&
        msg.metadata?.sessionId === event.session_id &&
        msg.metadata?.status === 'interim',
    );
  }
  if (existingIndex === -1) {
    const created: VoiceUIMessage = {
      id: event.utterance_id,
      role: event.speaker,
      parts: [{ type: 'text', text: displayText }],
      metadata: {
        sessionId: event.session_id,
        turnId: event.turn_id,
        utteranceId: event.utterance_id,
        seq: event.seq,
        timestamp: event.timestamp,
        status: event.status,
        spokenText: event.spoken_text,
        generatedText: event.generated_text,
      },
    };
    return [...messages, created];
  }

  const existing = messages[existingIndex];
  const prevMeta = existing.metadata;
  if (prevMeta) {
    const sameSourceId =
      existing.id === event.utterance_id && prevMeta.utteranceId === event.utterance_id;
    // Ignore replayed, out-of-order, or stale interim events after completion/interruption.
    if (sameSourceId && event.seq <= prevMeta.seq) {
      return messages;
    }
    if (prevMeta.status === 'interrupted' && event.status === 'interim') {
      return messages;
    }
    if (
      prevMeta.status === 'final' &&
      event.status === 'interim' &&
      (event.speaker === 'assistant' || !sameSourceId)
    ) {
      return messages;
    }
  }

  const updated: VoiceUIMessage = {
    ...existing,
    parts: [{ type: 'text', text: displayText }],
    metadata: {
      sessionId: event.session_id,
      turnId: event.turn_id,
      utteranceId: event.utterance_id,
      seq: event.seq,
      timestamp: event.timestamp,
      status: event.status,
      spokenText: event.spoken_text ?? prevMeta?.spokenText,
      generatedText: event.generated_text ?? prevMeta?.generatedText,
    },
  };

  const next = [...messages];
  next[existingIndex] = updated;
  return next;
}

export function applyStatusEvent(
  events: AgentStatusEvent[],
  incoming: AgentStatusEvent,
  activeSessionId: string | undefined,
): AgentStatusEvent[] {
  if (!activeSessionId || incoming.session_id !== activeSessionId) {
    return events;
  }
  const index = events.findIndex((item) => item.execution_id === incoming.execution_id);
  if (index === -1) {
    return [...events, incoming];
  }
  if (incoming.seq <= events[index].seq) {
    return events;
  }
  const next = [...events];
  next[index] = incoming;
  return next;
}
