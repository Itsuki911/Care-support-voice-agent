import { ParticipantKind, Room, RoomEvent } from 'livekit-client';

type Proposal = { execution_id: string; tool: string; arguments: Record<string, unknown>; expires_at: number; state: string };
type Snapshot = { session_id: string; closed: boolean; proposal: Proposal | null; operations: {execution_id: string; tool: string; state: string}[] };
const labels: Record<string, string> = {
  search_emails: 'Gmailを検索', read_email: 'メール本文を取得', send_email: 'メールを送信',
  selected: '選択', pending: '承認待ち', approved: '承認済み', denied: '拒否', expired: '期限切れ',
  cancelled: 'キャンセル', running: '実行中', succeeded: '完了', failed: '失敗', result_unknown: '結果不明（自動再送しません）',
};

export function attachApprovals(room: Room, container: HTMLElement): () => void {
  let disposed = false;
  let deciding = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let displayed = '';
  const status = document.createElement('p');
  const proposal = document.createElement('div');
  const history = document.createElement('p');
  container.replaceChildren(status, proposal, history);
  status.textContent = '外部操作は、この画面で内容を確認してから許可してください。';

  function clearPending(message: string) {
    displayed = '';
    proposal.replaceChildren();
    status.textContent = message;
  }
  const onReconnecting = () => clearPending('再接続中。承認操作は一時停止しています。');
  room.on(RoomEvent.Reconnecting, onReconnecting);

  async function poll() {
    if (disposed) return;
    const agent = [...room.remoteParticipants.values()].find(p => p.kind === ParticipantKind.AGENT);
    try {
      if (!agent) { clearPending('エージェントへの接続を待っています。'); return; }
      const response = await room.localParticipant.performRpc({destinationIdentity: agent.identity, method: 'approval.list', payload: '{}', responseTimeout: 3});
      if (disposed) return;
      const data: Snapshot = JSON.parse(response);
      history.textContent = data.operations.map(op => `${labels[op.tool] || op.tool}: ${labels[op.state] || op.state}`).join(' / ');
      if (data.closed) { clearPending('承認セッションは終了しました。停止してから再度起動してください。'); return; }
      if (!data.proposal) { clearPending('承認待ちの外部操作はありません。'); return; }
      const item = data.proposal;
      const remaining = Math.max(0, Math.ceil(item.expires_at - Date.now() / 1000));
      status.textContent = `承認待ち（残り約${remaining}秒）。拒否しても会話は続けられます。`;
      if (displayed === item.execution_id) return;
      displayed = item.execution_id;
      const heading = document.createElement('h2');
      heading.textContent = labels[item.tool] || item.tool;
      const details = document.createElement('pre');
      // External/LLM-controlled strings are text, never HTML.
      details.textContent = JSON.stringify(item.arguments, null, 2);
      const notice = document.createElement('p');
      notice.textContent = item.tool === 'send_email' ? '送信後は取り消せません。宛先・件名・本文を確認してください。' : '表示された条件で外部のGmailへアクセスします。取得済みデータの取得を取り消すことはできません。';
      const allow = document.createElement('button');
      const deny = document.createElement('button');
      allow.type = deny.type = 'button';
      allow.textContent = 'この内容で許可'; deny.textContent = '拒否';
      const decide = async (approved: boolean) => {
        if (disposed || deciding) return;
        deciding = true; allow.disabled = deny.disabled = true;
        try {
          await room.localParticipant.performRpc({destinationIdentity: agent.identity, method: 'approval.decide',
            payload: JSON.stringify({session_id: data.session_id, execution_id: item.execution_id, allow: approved}), responseTimeout: 5});
          if (!disposed) clearPending('決定を送信しました。実行状態を確認しています。');
        } catch {
          if (!disposed) clearPending('決定の応答を確認できません。状態を再取得します。自動再送はしません。');
        } finally { deciding = false; }
      };
      allow.onclick = () => { void decide(true); }; deny.onclick = () => { void decide(false); };
      proposal.replaceChildren(heading, details, notice, allow, deny);
    } catch {
      if (!disposed) clearPending('承認状態を取得できません。未承認の操作は実行されません。');
    } finally {
      if (!disposed) timer = setTimeout(() => { void poll(); }, 1000);
    }
  }
  void poll();
  return () => {
    disposed = true;
    if (timer) clearTimeout(timer);
    room.off(RoomEvent.Reconnecting, onReconnecting);
    container.replaceChildren();
  };
}
