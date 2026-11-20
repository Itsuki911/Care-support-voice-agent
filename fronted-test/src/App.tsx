import { useChat } from '@ai-sdk/react';
import {
  AssistantRuntimeProvider,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from '@assistant-ui/react';
import { useAISDKRuntime } from '@assistant-ui/react-ai-sdk';
import { Room, RoomEvent, Track } from 'livekit-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { LiveKitChatTransport } from './livekit/chatTransport';
import {
  applyStatusEvent,
  applyTranscriptEvent,
  type AgentStatusEvent,
  type ApprovalRequestPayload,
  type TranscriptEvent,
  type VoiceMessageMetadata,
  type VoiceUIMessage,
} from './livekit/protocol';

const decoder = new TextDecoder();
const encoder = new TextEncoder();

function UtteranceBadge() {
  const message = useAuiState((s) => s.message);
  const meta = (message as unknown as { metadata?: { custom?: VoiceMessageMetadata } | VoiceMessageMetadata })
    ?.metadata;
  const voiceMeta =
    meta && 'custom' in meta && meta.custom ? meta.custom : (meta as VoiceMessageMetadata | undefined);
  if (!voiceMeta?.status) return null;
  if (voiceMeta.status === 'interim') {
    return <span className="badge badge-interim">認識中…</span>;
  }
  if (voiceMeta.status === 'interrupted') {
    return <span className="badge badge-interrupted">中断（未発話分は除外）</span>;
  }
  return <span className="badge badge-final">確定</span>;
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="chat-message chat-user">
      <div className="chat-meta">
        <strong>ユーザー</strong>
        <UtteranceBadge />
      </div>
      <div className="chat-body">
        <MessagePrimitive.Content />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="chat-message chat-assistant">
      <div className="chat-meta">
        <strong>AI アシスタント</strong>
        <UtteranceBadge />
      </div>
      <div className="chat-body">
        <MessagePrimitive.Content />
      </div>
    </MessagePrimitive.Root>
  );
}

export function App() {
  const [statusText, setStatusText] = useState('停止中');
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [approval, setApproval] = useState<ApprovalRequestPayload | null>(null);
  const [statusEvents, setStatusEvents] = useState<AgentStatusEvent[]>([]);

  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const activeRoomRef = useRef<Room | undefined>(undefined);
  const activeSessionIdRef = useRef<string | undefined>(undefined);
  const abortControllerRef = useRef<AbortController | undefined>(undefined);
  const generationRef = useRef(0);
  const streamSeqRef = useRef(0);

  const transport = useMemo(() => new LiveKitChatTransport(), []);
  const chat = useChat<VoiceUIMessage>({
    id: 'livekit-voice-session',
    transport,
  });
  const runtime = useAISDKRuntime(chat);
  const setMessagesRef = useRef(chat.setMessages);
  setMessagesRef.current = chat.setMessages;

  function resetSessionUI(message: string): void {
    activeSessionIdRef.current = undefined;
    transport.setRoom(undefined);
    setApproval(null);
    setConnected(false);
    setConnecting(false);
    setStatusText(message);
    audioContainerRef.current?.replaceChildren();
  }

  async function handleStop(): Promise<void> {
    generationRef.current += 1;
    abortControllerRef.current?.abort();
    const room = activeRoomRef.current;
    activeRoomRef.current = undefined;
    if (room) {
      await room.disconnect();
    }
    resetSessionUI('停止中');
  }

  async function handleStart(): Promise<void> {
    const attempt = ++generationRef.current;
    setConnecting(true);
    setStatusText('接続中…');
    setStatusEvents([]);
    setMessagesRef.current([]);
    streamSeqRef.current = 0;

    const room = new Room();
    activeRoomRef.current = room;
    transport.setRoom(room);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio && audioContainerRef.current) {
        audioContainerRef.current.append(track.attach());
      }
    });

    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((el) => el.remove());
    });

    room.on(RoomEvent.Disconnected, () => {
      if (activeRoomRef.current === room) {
        activeRoomRef.current = undefined;
        generationRef.current += 1;
        resetSessionUI('切断されました。再度起動できます。');
      }
    });

    room.registerTextStreamHandler('lk.transcription', async (reader, participantInfo) => {
      const sessionId = activeSessionIdRef.current;
      if (!sessionId || room.name !== sessionId) return;

      const isAgent = participantInfo.identity !== room.localParticipant.identity;
      // User transcripts are delivered authoritatively via agent.py's TranscriptEventTracker
      // over the room data channel (which merges intra-turn clauses under a single utterance_id).
      if (!isAgent) return;

      const attrs = reader.info.attributes ?? {};
      const utteranceId = attrs['lk.segment_id'] || reader.info.id;
      let accumulated = '';

      for await (const chunk of reader) {
        if (activeSessionIdRef.current !== sessionId) return;
        accumulated += chunk;
        const isFinal = attrs['lk.transcription_final'] === 'true';
        const seq = ++streamSeqRef.current;
        const event: TranscriptEvent = {
          type: 'transcript_event',
          session_id: sessionId,
          turn_id: 'stream',
          utterance_id: `lk-${utteranceId}`,
          seq,
          speaker: 'assistant',
          timestamp: Date.now() / 1000,
          status: isFinal ? 'final' : 'interim',
          text: accumulated,
          spoken_text: accumulated,
        };
        setMessagesRef.current((prev) => applyTranscriptEvent(prev, event, sessionId));
      }
    });

    room.on(RoomEvent.DataReceived, (payload) => {
      try {
        const parsed = JSON.parse(decoder.decode(payload)) as Record<string, unknown>;
        const sessionId = activeSessionIdRef.current;
        if (parsed.type === 'transcript_event') {
          setMessagesRef.current((prev) =>
            applyTranscriptEvent(prev, parsed as unknown as TranscriptEvent, sessionId),
          );
        } else if (parsed.type === 'agent_status_event') {
          setStatusEvents((prev) =>
            applyStatusEvent(prev, parsed as unknown as AgentStatusEvent, sessionId),
          );
        } else if (parsed.type === 'approval_request' && typeof parsed.execution_id === 'string') {
          if (!parsed.session_id || parsed.session_id === sessionId) {
            setApproval(parsed as unknown as ApprovalRequestPayload);
          }
        }
      } catch {
        // Ignore non-JSON payloads.
      }
    });

    try {
      await room.startAudio();
      const response = await fetch('/api/token', { method: 'POST', signal: controller.signal });
      if (!response.ok) {
        throw new Error('接続情報を取得できません。Pythonサーバーの設定を確認してください。');
      }
      const { server_url, participant_token } = (await response.json()) as {
        server_url: string;
        participant_token: string;
      };
      if (attempt !== generationRef.current) return;

      await room.connect(server_url, participant_token);
      if (attempt !== generationRef.current) {
        await room.disconnect();
        return;
      }
      activeSessionIdRef.current = room.name;

      await room.localParticipant.setMicrophoneEnabled(true);
      if (attempt !== generationRef.current) {
        await room.disconnect();
        return;
      }
      setConnected(true);
      setConnecting(false);
      setStatusText('接続済み。マイクに向かって話してください。');
    } catch (error) {
      if (attempt !== generationRef.current) return;
      activeRoomRef.current = undefined;
      await room.disconnect();
      resetSessionUI(error instanceof Error ? error.message : '接続に失敗しました。');
    }
  }

  async function sendApprovalDecision(approved: boolean): Promise<void> {
    const room = activeRoomRef.current;
    const current = approval;
    if (!room || !current) return;
    setApproval(null);
    const payload = JSON.stringify({
      type: 'approval_response',
      execution_id: current.execution_id,
      approved,
    });
    await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
  }

  useEffect(() => {
    const onPageHide = () => {
      abortControllerRef.current?.abort();
      void activeRoomRef.current?.disconnect();
    };
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.removeEventListener('pagehide', onPageHide);
    };
  }, []);

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>音声会話テスト</h1>
        <p id="status" role="status" aria-live="polite">
          {statusText}
        </p>
        <div className="controls">
          <button id="start" type="button" disabled={connected || connecting} onClick={() => void handleStart()}>
            起動
          </button>
          <button id="stop" type="button" disabled={!connected && !connecting} onClick={() => void handleStop()}>
            停止
          </button>
        </div>
      </header>

      {approval && (
        <section id="approval-panel" className="approval-panel" aria-live="polite">
          <h2>外部操作の許可確認</h2>
          <p>操作: {approval.tool_name}</p>
          <p>対象: {approval.target}</p>
          <pre>{approval.summary}</pre>
          <p>
            {approval.reversible
              ? '読み取り・検索操作です。'
              : '送信後は取り消せません。内容をよく確認してください。'}
          </p>
          <div className="controls">
            <button type="button" onClick={() => void sendApprovalDecision(true)}>
              許可する
            </button>
            <button type="button" onClick={() => void sendApprovalDecision(false)}>
              拒否する
            </button>
          </div>
        </section>
      )}

      {statusEvents.length > 0 && (
        <section className="status-events" aria-label="処理状態">
          {statusEvents.map((ev) => (
            <span key={ev.execution_id} className="status-pill">
              {ev.label || ev.kind}: {ev.status}
            </span>
          ))}
        </section>
      )}

      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="chat-thread">
          <ThreadPrimitive.Viewport className="chat-viewport">
            <ThreadPrimitive.Empty>
              <p className="chat-empty">会話を開始すると、文字起こしがここに表示されます。</p>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages
              components={{
                UserMessage,
                AssistantMessage,
              }}
            />
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>

      <div ref={audioContainerRef} id="audio" />
    </main>
  );
}
