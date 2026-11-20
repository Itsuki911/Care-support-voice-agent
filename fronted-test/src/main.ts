import { Room, RoomEvent, Track } from 'livekit-client';
import './style.css';
import { attachApprovals } from './approvals';

const start = document.querySelector<HTMLButtonElement>('#start')!;
const stop = document.querySelector<HTMLButtonElement>('#stop')!;
const status = document.querySelector<HTMLParagraphElement>('#status')!;
const audio = document.querySelector<HTMLDivElement>('#audio')!;
let activeRoom: Room | undefined;
let request: AbortController | undefined;
let generation = 0;
let detachApprovals: (() => void) | undefined;

function reset(message: string): void {
  detachApprovals?.();
  detachApprovals = undefined;
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
