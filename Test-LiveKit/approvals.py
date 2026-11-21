"""Session-scoped approval authority. Only authenticated room RPC can decide.

Tool arguments never carry approval authority. All operations and their arguments
are captured before asking, and a consumed execution cannot be replayed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

from livekit.agents import ToolError


@dataclass
class PendingOperation:
    execution_id: str
    tool: str
    arguments: dict
    expires_at: float
    deadline: float
    fingerprint: str
    state: str = 'pending'
    decision: asyncio.Event = field(default_factory=asyncio.Event)


class ApprovalManager:
    def __init__(self, session_id: str, *, ttl: float = 120, observer=None):
        self.session_id = session_id
        self.ttl = ttl
        self.observer = observer or (lambda *args: None)
        self.operations: dict[str, PendingOperation] = {}
        self.closed = False
        self.owner: str | None = None

    def _state(self, op: PendingOperation, state: str):
        op.state = state
        self.observer(op.execution_id, op.tool, state)

    def _expire(self, op: PendingOperation):
        if op.state in ('pending', 'approved') and time.monotonic() >= op.deadline:
            self._state(op, 'expired')
            op.decision.set()

    def snapshot(self) -> dict:
        for op in self.operations.values():
            self._expire(op)
        # Only one full proposal per response: keep RPC under its 15 KiB limit.
        active = [op for op in self.operations.values() if op.state == 'pending']
        recent = list(self.operations.values())[-10:]
        return {'session_id': self.session_id, 'closed': self.closed,
                'pending_count': len(active),
                'proposal': self._view(active[0]) if active else None,
                'operations': [{'execution_id': op.execution_id, 'tool': op.tool,
                                'state': op.state} for op in recent]}

    def _view(self, op):
        return {'execution_id': op.execution_id, 'tool': op.tool,
                'arguments': json.loads(json.dumps(op.arguments)),
                'expires_at': op.expires_at, 'state': op.state}

    def decide(self, session_id: str, execution_id: str, allow: bool) -> str:
        if self.closed or session_id != self.session_id or type(allow) is not bool:
            raise ValueError('Invalid approval session or decision')
        op = self.operations.get(execution_id)
        if op is None:
            raise ValueError('Unknown execution')
        self._expire(op)
        if op.state == 'pending':
            self._state(op, 'approved' if allow else 'denied')
            op.decision.set()
            # Refresh TTL for the next queued item so it doesn't expire while waiting in queue.
            next_op = next((item for item in self.operations.values() if item.state == 'pending'), None)
            if next_op is not None:
                next_op.expires_at = time.time() + self.ttl
                next_op.deadline = time.monotonic() + self.ttl
        return op.state

    def close(self):
        self.closed = True
        for op in self.operations.values():
            if op.state in ('pending', 'approved'):
                self._state(op, 'cancelled')
                op.decision.set()
            elif op.state == 'running':
                self._state(op, 'result_unknown')

    async def run(self, tool: str, arguments: dict,
                  execute: Callable[[dict], Awaitable[Any]]) -> Any:
        if self.closed:
            raise ToolError('セッションが終了したため実行できません。')
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode()) > 9000 or len(self.operations) >= 100:
            raise ToolError('承認画面の上限を超えています。内容を短くするか新しいセッションを開始してください。')
        fingerprint = hashlib.sha256((tool + encoded).encode()).hexdigest()
        # Denial/expiry and unknown sends cannot silently create a fresh retry.
        if any(op.fingerprint == fingerprint for op in self.operations.values()):
            raise ToolError('同じ操作は既に依頼済みです。承認状態と実行結果を確認してください。自動再実行はしません。')
        op = PendingOperation(uuid4().hex, tool, json.loads(encoded),
                              time.time() + self.ttl, time.monotonic() + self.ttl, fingerprint)
        self.operations[op.execution_id] = op
        self._state(op, 'selected')
        self._state(op, 'pending')
        try:
            while not op.decision.is_set():
                remaining = op.deadline - time.monotonic()
                if remaining <= 0:
                    self._state(op, 'expired')
                    break
                try:
                    await asyncio.wait_for(op.decision.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    if time.monotonic() >= op.deadline:
                        self._state(op, 'expired')
                        break
            self._expire(op)
            if self.closed or op.state != 'approved':
                raise ToolError(f'外部操作は実行していません（{op.state}）。')
            self._state(op, 'running')
            try:
                result = await execute(json.loads(encoded))
            except Exception:
                self._state(op, 'result_unknown' if tool == 'send_email' else 'failed')
                raise
            if op.state == 'running':
                self._state(op, 'succeeded')
            return result
        except asyncio.CancelledError:
            self._state(op, 'result_unknown' if op.state == 'running' else 'cancelled')
            raise


def register_approval_rpc(room, manager: ApprovalManager):
    """Authenticate via LiveKit caller identity, not a client-supplied identity."""
    from livekit import rtc

    def authorize(data):
        participant = room.remote_participants.get(data.caller_identity)
        if (participant is None or not data.caller_identity.startswith('browser-')
                or manager.closed):
            raise rtc.RpcError(1500, 'Approval unavailable')
        if manager.owner is None:
            manager.owner = data.caller_identity
        if manager.owner != data.caller_identity:
            raise rtc.RpcError(1500, 'Different approval owner')

    @room.local_participant.register_rpc_method('approval.list')
    async def list_operations(data):
        authorize(data)
        return json.dumps(manager.snapshot(), ensure_ascii=False)

    @room.local_participant.register_rpc_method('approval.decide')
    async def decide(data):
        authorize(data)
        try:
            payload = json.loads(data.payload)
            state = manager.decide(payload['session_id'], payload['execution_id'], payload['allow'])
        except (ValueError, TypeError, KeyError):
            raise rtc.RpcError(1500, 'Invalid approval') from None
        return json.dumps({'state': state})

    @room.on('participant_disconnected')
    def disconnected(participant):
        if participant.identity == manager.owner or participant.identity.startswith('browser-'):
            manager.close()

    @room.on('disconnected')
    def room_disconnected(*_):
        manager.close()
