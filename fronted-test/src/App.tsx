import { useChat } from '@ai-sdk/react';
import {
  AssistantRuntimeProvider,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from '@assistant-ui/react';
import { useAISDKRuntime } from '@assistant-ui/react-ai-sdk';
import { Room, RoomEvent, Track } from 'livekit-client';
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtStep,
  type StepStatus,
} from './components/ai-elements/chain-of-thought';
import { LiveKitChatTransport } from './livekit/chatTransport';
import {
  applyStatusEvent,
  applyTranscriptEvent,
  finalizeActiveStatusEvents,
  formatStatusLabel,
  getStatusBadgeText,
  isActiveStatus,
  type AgentStatusEvent,
  type ApprovalRequestPayload,
  type TranscriptEvent,
  type VoiceMessageMetadata,
  type VoiceUIMessage,
} from './livekit/protocol';

const decoder = new TextDecoder();
const encoder = new TextEncoder();

function getVoiceMeta(message: unknown): VoiceMessageMetadata | undefined {
  const meta = (message as { metadata?: { custom?: VoiceMessageMetadata } | VoiceMessageMetadata } | undefined)
    ?.metadata;
  if (!meta) return undefined;
  return 'custom' in meta && meta.custom ? meta.custom : (meta as VoiceMessageMetadata);
}

function toStepStatus(status: string): StepStatus {
  if (status === 'running' || status === 'approved') return 'active';
  if (status === 'pending' || status === 'selected') return 'pending';
  if (
    status === 'failed' ||
    status === 'denied' ||
    status === 'expired' ||
    status === 'cancelled' ||
    status === 'result_unknown'
  ) {
    return 'error';
  }
  return 'complete';
}

interface TurnUIContextValue {
  statusEvents: AgentStatusEvent[];
  approval: ApprovalRequestPayload | null;
  onApprovalDecision: (approved: boolean) => void;
  latestUserMessageId?: string;
}

const TurnUIContext = createContext<TurnUIContextValue>({
  statusEvents: [],
  approval: null,
  onApprovalDecision: () => {},
});

function TurnProgressPanel({ events }: { events: AgentStatusEvent[] }) {
  const [open, setOpen] = useState(true);
  if (events.length === 0) return null;
  const activeSteps = events.filter((ev) => isActiveStatus(ev.status));
  const latestActive = activeSteps[activeSteps.length - 1];
  const headerLabel = latestActive
    ? formatStatusLabel(latestActive)
    : `処理ステップ（${events.length}件）`;

  return (
    <section className="status-events" aria-label="処理ステータス">
      <ChainOfThought open={open} onOpenChange={setOpen}>
        <ChainOfThoughtHeader isActive={activeSteps.length > 0}>
          {headerLabel}
        </ChainOfThoughtHeader>
        <ChainOfThoughtContent>
          {events.slice(-12).map((ev) => (
            <ChainOfThoughtStep
              key={ev.execution_id}
              kind={ev.kind}
              status={toStepStatus(ev.status)}
              label={formatStatusLabel(ev)}
              badgeText={getStatusBadgeText(ev.status)}
              detail={ev.detail}
            />
          ))}
        </ChainOfThoughtContent>
      </ChainOfThought>
    </section>
  );
}

function ApprovalPanel({
  approval,
  onDecision,
}: {
  approval: ApprovalRequestPayload;
  onDecision: (approved: boolean) => void;
}) {
  return (
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
        <button type="button" onClick={() => onDecision(true)}>
          許可する
        </button>
        <button type="button" onClick={() => onDecision(false)}>
          拒否する
        </button>
      </div>
    </section>
  );
}

function UtteranceBadge() {
  const message = useAuiState((s) => s.message);
  const voiceMeta = getVoiceMeta(message);
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
  const message = useAuiState((s) => s.message);
  const voiceMeta = getVoiceMeta(message);
  const { statusEvents, approval, onApprovalDecision, latestUserMessageId } =
    useContext(TurnUIContext);

  const isLatestUser = Boolean(latestUserMessageId && message?.id === latestUserMessageId);
  const turnEvents = statusEvents.filter((ev) =>
    voiceMeta?.turnId ? ev.turn_id === voiceMeta.turnId : isLatestUser && ev.turn_id !== 'turn-0',
  );
  const showApproval = Boolean(approval && isLatestUser);

  return (
    <div className="chat-user-group">
      <MessagePrimitive.Root className="chat-message chat-user">
        <div className="chat-meta">
          <strong>ユーザー</strong>
          <UtteranceBadge />
        </div>
        <div className="chat-body">
          <MessagePrimitive.Content />
        </div>
      </MessagePrimitive.Root>
      {(turnEvents.length > 0 || showApproval) && (
        <div className="chat-turn-attachments">
          <TurnProgressPanel events={turnEvents} />
          {showApproval && approval && (
            <ApprovalPanel approval={approval} onDecision={onApprovalDecision} />
          )}
        </div>
      )}
    </div>
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

export type SessionMode = 'voice' | 'text';

const USER_ID_STORAGE_KEY = 'care-support-user-id';
const DEFAULT_USER_ID = 'default-user';

function loadSavedUserId(): string {
  try {
    const saved = window.localStorage.getItem(USER_ID_STORAGE_KEY);
    if (saved && saved.trim()) {
      return saved.trim();
    }
  } catch {
    // Ignore storage access errors in restricted environments.
  }
  return DEFAULT_USER_ID;
}

export function App() {
  const [sessionMode, setSessionMode] = useState<SessionMode>('voice');
  const [userId, setUserId] = useState<string>(() => loadSavedUserId());
  const [textDraft, setTextDraft] = useState('');
  const [statusText, setStatusText] = useState('停止中');
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [approval, setApproval] = useState<ApprovalRequestPayload | null>(null);
  const [statusEvents, setStatusEvents] = useState<AgentStatusEvent[]>([]);

  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const activeRoomRef = useRef<Room | undefined>(undefined);
  const activeSessionIdRef = useRef<string | undefined>(undefined);
  const activeModeRef = useRef<SessionMode>('voice');
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
    setTextDraft('');
    setStatusText(message);
    setStatusEvents((prev) => finalizeActiveStatusEvents(prev));
    audioContainerRef.current?.replaceChildren();
  }

  function handleUserIdChange(nextValue: string): void {
    setUserId(nextValue);
    try {
      const trimmed = nextValue.trim();
      if (trimmed) {
        window.localStorage.setItem(USER_ID_STORAGE_KEY, trimmed);
      } else {
        window.localStorage.removeItem(USER_ID_STORAGE_KEY);
      }
    } catch {
      // Ignore storage write errors.
    }
  }

  async function handleStop(): Promise<void> {
    generationRef.current += 1;
    abortControllerRef.current?.abort();
    const room = activeRoomRef.current;
    const sessionId = activeSessionIdRef.current;
    activeRoomRef.current = undefined;
    if (room) {
      try {
        const payload = JSON.stringify({
          type: 'end_session',
          session_id: sessionId,
        });
        await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
        await new Promise((resolve) => window.setTimeout(resolve, 150));
      } catch {
        // Proceed with disconnect even if the data channel is already closed.
      }
      await room.disconnect();
    }
    resetSessionUI('会話を終了しました（記憶の保存をバックグラウンドで実行します）。');
  }

  async function handleStart(): Promise<void> {
    const attempt = ++generationRef.current;
    const mode = sessionMode;
    activeModeRef.current = mode;
    setConnecting(true);
    setStatusText(mode === 'voice' ? '音声セッションに接続中…' : 'テキスト専用セッションに接続中…');
    setStatusEvents([]);
    setMessagesRef.current([]);
    setTextDraft('');
    streamSeqRef.current = 0;

    const room = new Room();
    activeRoomRef.current = room;
    transport.setMode(mode);
    transport.setRoom(room);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (mode === 'voice') {
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio && audioContainerRef.current) {
          audioContainerRef.current.append(track.attach());
        }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((el) => el.remove());
      });
    }

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
      if (mode === 'voice') {
        await room.startAudio();
      }
      const effectiveUserId = userId.trim() || DEFAULT_USER_ID;
      const response = await fetch('/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, user_id: effectiveUserId }),
        signal: controller.signal,
      });
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

      if (mode === 'voice') {
        await room.localParticipant.setMicrophoneEnabled(true);
        if (attempt !== generationRef.current) {
          await room.disconnect();
          return;
        }
      }
      setConnected(true);
      setConnecting(false);
      setStatusText(
        mode === 'voice'
          ? '接続済み（音声専用セッション）。マイクに向かって話してください。'
          : '接続済み（テキスト専用セッション）。下の入力欄からメッセージを送信してください。',
      );
    } catch (error) {
      if (attempt !== generationRef.current) return;
      activeRoomRef.current = undefined;
      await room.disconnect();
      resetSessionUI(error instanceof Error ? error.message : '接続に失敗しました。');
    }
  }

  async function handleSendText(): Promise<void> {
    if (!connected || activeModeRef.current !== 'text') return;
    const room = activeRoomRef.current;
    const text = textDraft.trim();
    if (!room || !text) return;
    setTextDraft('');
    await chat.sendMessage({ text });
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
        <h1>会話テスト（音声 / テキスト別セッション）</h1>
        <fieldset className="mode-selector" disabled={connected || connecting}>
          <legend>セッション種別（起動中は変更不可）</legend>
          <label className={`mode-option ${sessionMode === 'voice' ? 'mode-option-active' : ''}`}>
            <input
              type="radio"
              name="session-mode"
              value="voice"
              checked={sessionMode === 'voice'}
              onChange={() => setSessionMode('voice')}
            />
            音声専用セッション（マイク・スピーカー）
          </label>
          <label className={`mode-option ${sessionMode === 'text' ? 'mode-option-active' : ''}`}>
            <input
              type="radio"
              name="session-mode"
              value="text"
              checked={sessionMode === 'text'}
              onChange={() => setSessionMode('text')}
            />
            テキスト専用セッション（チャット入力）
          </label>
        </fieldset>
        <div className="user-id-row">
          <label htmlFor="user-id-input">ユーザー ID（記憶の紐付け先）:</label>
          <input
            id="user-id-input"
            type="text"
            className="user-id-input"
            value={userId}
            disabled={connected || connecting}
            placeholder={DEFAULT_USER_ID}
            onChange={(e) => handleUserIdChange(e.target.value)}
          />
        </div>
        <p id="status" role="status" aria-live="polite">
          {statusText}
        </p>
        <div className="controls">
          <button id="start" type="button" disabled={connected || connecting} onClick={() => void handleStart()}>
            {sessionMode === 'voice' ? '音声セッションを起動' : 'テキストセッションを起動'}
          </button>
          <button id="stop" type="button" disabled={!connected && !connecting} onClick={() => void handleStop()}>
            会話終了
          </button>
        </div>
      </header>

      {(() => {
        const latestUser = [...chat.messages].reverse().find((msg) => msg.role === 'user');
        const hasUserMessage = Boolean(latestUser);
        const preUserEvents = hasUserMessage
          ? statusEvents.filter((ev) => ev.turn_id === 'turn-0')
          : statusEvents;

        return (
          <TurnUIContext.Provider
            value={{
              statusEvents,
              approval,
              onApprovalDecision: (approved) => {
                void sendApprovalDecision(approved);
              },
              latestUserMessageId: latestUser?.id,
            }}
          >
            {preUserEvents.length > 0 && <TurnProgressPanel events={preUserEvents} />}
            {!hasUserMessage && approval && (
              <ApprovalPanel
                approval={approval}
                onDecision={(approved) => {
                  void sendApprovalDecision(approved);
                }}
              />
            )}
            <AssistantRuntimeProvider runtime={runtime}>
              <ThreadPrimitive.Root className="chat-thread">
                <ThreadPrimitive.Viewport className="chat-viewport">
                  <ThreadPrimitive.Empty>
                    <p className="chat-empty">
                      {sessionMode === 'voice'
                        ? '音声セッションを開始すると、会話の文字起こしがここに表示されます。'
                        : 'テキストセッションを開始すると、ここでテキストによる会話ができます。'}
                    </p>
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
          </TurnUIContext.Provider>
        );
      })()}

      {sessionMode === 'text' && (
        <form
          className="text-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSendText();
          }}
        >
          <input
            id="text-input"
            type="text"
            className="text-composer-input"
            placeholder={
              connected
                ? 'メッセージを入力してEnterまたは送信…'
                : '「テキストセッションを起動」を押すと入力できます'
            }
            value={textDraft}
            disabled={!connected}
            onChange={(e) => setTextDraft(e.target.value)}
          />
          <button type="submit" disabled={!connected || !textDraft.trim()}>
            送信
          </button>
        </form>
      )}

      <div ref={audioContainerRef} id="audio" />
    </main>
  );
}
