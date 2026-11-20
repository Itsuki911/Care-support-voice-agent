import { Room, RoomEvent, Track } from 'livekit-client';
import './style.css';
import { attachApprovals } from './approvals';

const start = document.querySelector<HTMLButtonElement>('#start')!;
const stop = document.querySelector<HTMLButtonElement>('#stop')!;
const status = document.querySelector<HTMLParagraphElement>('#status')!;
const audio = document.querySelector<HTMLDivElement>('#audio')!;
const approvalPanel = document.querySelector<HTMLElement>('#approval-panel')!;
const approvalTool = document.querySelector<HTMLParagraphElement>('#approval-tool')!;
const approvalTarget = document.querySelector<HTMLParagraphElement>('#approval-target')!;
const approvalSummary = document.querySelector<HTMLPreElement>('#approval-summary')!;
const approvalNote = document.querySelector<HTMLParagraphElement>('#approval-note')!;
const approveBtn = document.querySelector<HTMLButtonElement>('#approve-btn')!;
const rejectBtn = document.querySelector<HTMLButtonElement>('#reject-btn')!;

interface ApprovalRequestPayload {
  type: 'approval_request';
  execution_id: string;
  tool_name: string;
  target: string;
  summary: string;
  reversible: boolean;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();
let activeRoom: Room | undefined;
let request: AbortController | undefined;
let generation = 0;
let detachApprovals: (() => void) | undefined;
let pendingApprovalId: string | undefined;

function clearApproval(): void {
  pendingApprovalId = undefined;
  if (!approvalPanel) return;
  approvalPanel.hidden = true;
  approvalTool.textContent = '';
  approvalTarget.textContent = '';
  approvalSummary.textContent = '';
  approvalNote.textContent = '';
}

async function sendApprovalDecision(approved: boolean): Promise<void> {
  const executionId = pendingApprovalId;
  const room = activeRoom;
  if (!executionId || !room) return;
  clearApproval();
  const payload = JSON.stringify({
    type: 'approval_response',
    execution_id: executionId,
    approved,
  });
  await room.localParticipant.publishData(encoder.encode(payload), { reliable: true });
}

if (approveBtn) approveBtn.onclick = () => { void sendApprovalDecision(true); };
if (rejectBtn) rejectBtn.onclick = () => { void sendApprovalDecision(false); };

function reset(message: string): void {
  detachApprovals?.();
  detachApprovals = undefined;
  clearApproval();
  audio.replaceChildren();
  start.disabled = false;
  stop.disabled = true;
  status.textContent = message;
}

stop.onclick = async () => {
  generation++;
  detachApprovals?.();
  detachApprovals = undefined;
  request?.abort();
  const room = activeRoom;
  activeRoom = undefined;
  stop.disabled = true;
  if (room) await room.disconnect(); // Also stops local microphone tracks.
  reset('停止中');
};

start.onclick = async () => {
  const attempt = ++generation;
  start.disabled = true;
  stop.disabled = false;
  status.textContent = '接続中…';
  const room = new Room();
  activeRoom = room;
  request = new AbortController();
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === Track.Kind.Audio) audio.append(track.attach());
  });
  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    track.detach().forEach((element) => element.remove());
  });
  room.on(RoomEvent.DataReceived, (payload) => {
    try {
      const data = JSON.parse(decoder.decode(payload)) as Partial<ApprovalRequestPayload>;
      if (data.type !== 'approval_request' || !data.execution_id) return;
      pendingApprovalId = data.execution_id;
      approvalTool.textContent = `操作: ${data.tool_name ?? ''}`;
      approvalTarget.textContent = `対象: ${data.target ?? ''}`;
      approvalSummary.textContent = data.summary ?? '';
      approvalNote.textContent = data.reversible
        ? '読み取り・検索操作です。'
        : '送信後は取り消せません。内容をよく確認してください。';
      approvalPanel.hidden = false;
    } catch {
      // Ignore non-JSON or unrelated data messages.
    }
  });
  room.on(RoomEvent.Disconnected, () => {
    if (activeRoom === room) {
      activeRoom = undefined;
      generation++;
      reset('切断されました。再度起動できます。');
    }
  });
  try {
    // Unlock playback during the user's button gesture, before network awaits.
    await room.startAudio();
    const response = await fetch('/api/token', { method: 'POST', signal: request.signal });
    if (!response.ok) throw new Error('接続情報を取得できません。Pythonサーバーの設定を確認してください。');
    const { server_url, participant_token } = await response.json();
    if (attempt !== generation) return;
    await room.connect(server_url, participant_token);
    if (attempt !== generation) { await room.disconnect(); return; }
    await room.localParticipant.setMicrophoneEnabled(true);
    if (attempt !== generation) { await room.disconnect(); return; }
    detachApprovals = attachApprovals(room, document.querySelector<HTMLElement>('#approvals')!);
    status.textContent = '接続済み。マイクに向かって話してください。';
  } catch (error) {
    if (attempt !== generation) return;
    activeRoom = undefined;
    await room.disconnect();
    reset(error instanceof Error ? error.message : '接続に失敗しました。');
  }
};

window.addEventListener('pagehide', () => { request?.abort(); void activeRoom?.disconnect(); });
