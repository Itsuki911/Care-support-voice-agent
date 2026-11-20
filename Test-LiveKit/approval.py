"""Backend approval state machine for human-in-the-loop external tool execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import uuid4


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    UNKNOWN_RESULT = "unknown_result"


class ApprovalError(Exception):
    """Raised when an approval check or state transition fails."""


def compute_args_digest(args: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 digest of normalized tool arguments."""
    normalized = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class ApprovalRequest:
    execution_id: str
    session_id: str
    tool_name: str
    target: str
    summary: str
    args_snapshot: dict[str, Any]
    args_digest: str
    reversible: bool
    created_at: float
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    detail: str = ""
    _decision_future: asyncio.Future[bool] | None = field(default=None, repr=False, compare=False)

    def to_payload(self) -> dict[str, Any]:
        """Serialize public fields for the approval UI (no internal Future objects)."""
        return {
            "type": "approval_request",
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "target": self.target,
            "summary": self.summary,
            "reversible": self.reversible,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status.value,
        }


class ApprovalManager:
    """Manages pending approvals, expiration, argument binding, and single-execution guarantees."""

    def __init__(
        self,
        session_id: str,
        *,
        default_ttl_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.session_id = session_id
        self.default_ttl_seconds = default_ttl_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._requests: dict[str, ApprovalRequest] = {}
        self._closed = False

    def create_request(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        target: str,
        summary: str,
        reversible: bool,
        ttl_seconds: float | None = None,
    ) -> ApprovalRequest:
        """Create a new pending approval bound to the exact normalized arguments."""
        now = self._clock()
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")

        snapshot = json.loads(json.dumps(args, ensure_ascii=False))
        digest = compute_args_digest(snapshot)
        execution_id = uuid4().hex

        with self._lock:
            if self._closed:
                raise ApprovalError("セッションが終了しているため、外部操作の承認を作成できません。")
            req = ApprovalRequest(
                execution_id=execution_id,
                session_id=self.session_id,
                tool_name=tool_name,
                target=target,
                summary=summary,
                args_snapshot=snapshot,
                args_digest=digest,
                reversible=reversible,
                created_at=now,
                expires_at=now + ttl,
            )
            self._requests[execution_id] = req
            return req

    def get(self, execution_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(execution_id)

    def resolve(
        self,
        execution_id: str,
        approved: bool,
        *,
        args_digest: str | None = None,
    ) -> ApprovalRequest:
        """Record a human decision for a pending request. Duplicate or expired responses are ignored."""
        now = self._clock()
        future_to_set: asyncio.Future[bool] | None = None
        decision = False

        with self._lock:
            req = self._requests.get(execution_id)
            if req is None:
                raise ApprovalError("承認対象のリクエストが見つかりません。")

            if self._closed:
                if req.status == ApprovalStatus.PENDING:
                    req.status = ApprovalStatus.REJECTED
                    req.detail = "session_closed"
                return req

            if req.status != ApprovalStatus.PENDING:
                # Duplicate approval/rejection event: never re-open or re-trigger execution.
                return req

            if now > req.expires_at:
                req.status = ApprovalStatus.EXPIRED
                req.detail = "approval_expired"
                future_to_set = req._decision_future
                decision = False
            elif args_digest is not None and args_digest != req.args_digest:
                req.status = ApprovalStatus.REJECTED
                req.detail = "args_mismatch"
                future_to_set = req._decision_future
                decision = False
            elif approved:
                req.status = ApprovalStatus.APPROVED
                future_to_set = req._decision_future
                decision = True
            else:
                req.status = ApprovalStatus.REJECTED
                req.detail = "rejected_by_user"
                future_to_set = req._decision_future
                decision = False

        if future_to_set is not None and not future_to_set.done():
            loop = future_to_set.get_loop()
            loop.call_soon_threadsafe(lambda: not future_to_set.done() and future_to_set.set_result(decision))
        return req

    async def wait_for_decision(
        self,
        execution_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> bool:
        """Wait asynchronously until the request is approved, rejected, expired, or session-closed."""
        loop = asyncio.get_running_loop()
        with self._lock:
            req = self._requests.get(execution_id)
            if req is None:
                raise ApprovalError("承認対象のリクエストが見つかりません。")
            if self._closed:
                return False
            if req.status == ApprovalStatus.APPROVED:
                return True
            if req.status != ApprovalStatus.PENDING:
                return False
            if req._decision_future is None:
                req._decision_future = loop.create_future()
            future = req._decision_future
            remaining = max(0.0, req.expires_at - self._clock())

        wait_time = remaining if timeout_seconds is None else min(remaining, timeout_seconds)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=wait_time)
        except asyncio.TimeoutError:
            self._expire_if_pending(execution_id)
            return False

    def _expire_if_pending(self, execution_id: str) -> None:
        with self._lock:
            req = self._requests.get(execution_id)
            if req is not None and req.status == ApprovalStatus.PENDING:
                req.status = ApprovalStatus.EXPIRED
                req.detail = "approval_timeout"

    def begin_execution(self, execution_id: str, current_args: dict[str, Any]) -> ApprovalRequest:
        """Atomically verify approval, expiration, and exact argument match before execution."""
        now = self._clock()
        current_digest = compute_args_digest(current_args)
        with self._lock:
            req = self._requests.get(execution_id)
            if req is None:
                raise ApprovalError("承認情報が存在しないため実行できません。")
            if self._closed:
                raise ApprovalError("セッションが終了しているため実行できません。")
            if req.status == ApprovalStatus.PENDING:
                if now > req.expires_at:
                    req.status = ApprovalStatus.EXPIRED
                    raise ApprovalError("承認の有効期限が切れています。")
                raise ApprovalError("この操作はまだ人の許可を得ていません。")
            if req.status == ApprovalStatus.REJECTED:
                raise ApprovalError("この操作は人によって拒否されました。")
            if req.status == ApprovalStatus.EXPIRED:
                raise ApprovalError("承認の有効期限が切れています。")
            if req.status in {
                ApprovalStatus.EXECUTING,
                ApprovalStatus.EXECUTED,
                ApprovalStatus.FAILED,
                ApprovalStatus.UNKNOWN_RESULT,
            }:
                raise ApprovalError("この承認はすでに使用済みのため二重実行できません。")
            if now > req.expires_at:
                req.status = ApprovalStatus.EXPIRED
                raise ApprovalError("承認の有効期限が切れています。")
            if current_digest != req.args_digest:
                raise ApprovalError("操作内容が承認時と変更されたため、再度承認が必要です。")

            req.status = ApprovalStatus.EXECUTING
            return req

    def complete_execution(
        self,
        execution_id: str,
        outcome: ApprovalStatus,
        *,
        detail: str = "",
    ) -> ApprovalRequest:
        """Record final execution outcome (EXECUTED, FAILED, or UNKNOWN_RESULT)."""
        if outcome not in {
            ApprovalStatus.EXECUTED,
            ApprovalStatus.FAILED,
            ApprovalStatus.UNKNOWN_RESULT,
        }:
            raise ValueError(f"Invalid completion outcome: {outcome}")

        with self._lock:
            req = self._requests.get(execution_id)
            if req is None:
                raise ApprovalError("承認情報が存在しません。")
            req.status = outcome
            req.detail = detail
            return req

    def close_session(self) -> None:
        """Cancel all pending approvals when the session ends."""
        pending_futures: list[asyncio.Future[bool]] = []
        with self._lock:
            self._closed = True
            for req in self._requests.values():
                if req.status == ApprovalStatus.PENDING:
                    req.status = ApprovalStatus.EXPIRED
                    req.detail = "session_closed"
                    if req._decision_future is not None and not req._decision_future.done():
                        pending_futures.append(req._decision_future)

        for future in pending_futures:
            loop = future.get_loop()
            loop.call_soon_threadsafe(lambda f=future: not f.done() and f.set_result(False))
