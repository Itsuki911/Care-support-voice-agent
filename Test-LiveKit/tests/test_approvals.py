import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from livekit import rtc
from livekit.agents import ToolError
from approvals import ApprovalManager, register_approval_rpc
from gmail_tools import GmailTools, GmailError


def test_no_approval_no_external_operation():
    client = MagicMock()
    async def scenario():
        tools = GmailTools(client)
        for coroutine in (tools.search_emails(), tools.read_email('id'), tools.send_email('a@example.com', 's', 'b')):
            with pytest.raises(ToolError):
                await coroutine
    asyncio.run(scenario())
    assert not client.mock_calls


@pytest.mark.parametrize('decision', ['denied', 'expired', 'closed', 'cancelled'])
def test_denial_expiry_close_and_interrupt_never_execute(decision):
    async def scenario():
        manager = ApprovalManager('s', ttl=0.01 if decision == 'expired' else 120)
        client = MagicMock()
        task = asyncio.create_task(GmailTools(client, manager).search_emails())
        await asyncio.sleep(0)
        op = manager.snapshot()['proposal']
        assert not client.mock_calls
        if decision == 'denied': manager.decide('s', op['execution_id'], False)
        if decision == 'closed': manager.close()
        if decision == 'cancelled': task.cancel()
        with pytest.raises((ToolError, asyncio.CancelledError)):
            await task
        assert not client.mock_calls
        assert manager.operations[op['execution_id']].state in ('denied', 'expired', 'cancelled')
    asyncio.run(scenario())


def test_duplicate_decision_and_model_retry_do_not_resend():
    async def scenario():
        manager = ApprovalManager('s')
        client = MagicMock()
        client.send.return_value = {'status': 'sent'}
        tools = GmailTools(client, manager)
        task = asyncio.create_task(tools.send_email('a@example.com', 'subject', 'body'))
        await asyncio.sleep(0)
        op = manager.snapshot()['proposal']
        with pytest.raises(ValueError): manager.decide('different-session', op['execution_id'], True)
        with pytest.raises(ValueError): manager.decide('s', op['execution_id'], 'true')
        assert not client.mock_calls
        for _ in range(2): manager.decide('s', op['execution_id'], True)
        assert await task == {'status': 'sent'}
        manager.decide('s', op['execution_id'], True)
        with pytest.raises(ToolError): await tools.send_email('a@example.com', 'subject', 'body')
        client.send.assert_called_once_with(recipient='a@example.com', subject='subject', body='body')
    asyncio.run(scenario())


def test_changed_arguments_require_new_approval_and_snapshot_cannot_mutate():
    async def scenario():
        manager = ApprovalManager('s')
        client = MagicMock()
        tools = GmailTools(client, manager)
        task = asyncio.create_task(tools.send_email('a@example.com', 'subject', 'original'))
        await asyncio.sleep(0)
        op = manager.snapshot()['proposal']
        op['arguments']['body'] = 'tampered'
        manager.decide('s', op['execution_id'], True)
        await task
        client.send.assert_called_once_with(recipient='a@example.com', subject='subject', body='original')
        task = asyncio.create_task(tools.send_email('b@example.com', 'subject', 'changed'))
        await asyncio.sleep(0)
        assert client.send.call_count == 1
        assert manager.snapshot()['proposal']['execution_id'] != op['execution_id']
        manager.close()
        with pytest.raises(ToolError): await task
    asyncio.run(scenario())


def test_unknown_send_cannot_retry():
    async def scenario():
        manager = ApprovalManager('s')
        client = MagicMock()
        client.send.side_effect = GmailError('result unknown')
        tools = GmailTools(client, manager)
        task = asyncio.create_task(tools.send_email('a@example.com', 's', 'b'))
        await asyncio.sleep(0)
        op = manager.snapshot()['proposal']
        manager.decide('s', op['execution_id'], True)
        with pytest.raises(ToolError): await task
        assert manager.operations[op['execution_id']].state == 'result_unknown'
        with pytest.raises(ToolError): await tools.send_email('a@example.com', 's', 'b')
        assert client.send.call_count == 1
    asyncio.run(scenario())


def test_expired_approval_and_separate_session_cannot_reuse():
    async def scenario():
        manager = ApprovalManager('s')
        task = asyncio.create_task(GmailTools(MagicMock(), manager).read_email('id'))
        await asyncio.sleep(0)
        op = next(iter(manager.operations.values()))
        op.deadline = 0
        assert manager.decide('s', op.execution_id, True) == 'expired'
        with pytest.raises(ToolError): await task
        other = ApprovalManager('new')
        with pytest.raises(ValueError): other.decide('s', op.execution_id, True)
    asyncio.run(scenario())


def test_rpc_authentication_and_disconnect():
    class Room:
        def __init__(self):
            self.handlers = {}; self.events = {}
            self.remote_participants = {'browser-a': object(), 'browser-b': object(), 'agent': object()}
            self.local_participant = self
        def register_rpc_method(self, name):
            def register(f): self.handlers[name] = f; return f
            return register
        def on(self, name):
            def register(f): self.events[name] = f; return f
            return register
    async def scenario():
        room = Room(); manager = ApprovalManager('s')
        register_approval_rpc(room, manager)
        def data(identity, payload='{}'):
            return SimpleNamespace(caller_identity=identity, payload=payload)
        for identity in ('stranger', 'agent'):
            with pytest.raises(rtc.RpcError): await room.handlers['approval.list'](data(identity))
        result = json.loads(await room.handlers['approval.list'](data('browser-a')))
        assert result['session_id'] == 's'
        with pytest.raises(rtc.RpcError): await room.handlers['approval.list'](data('browser-b'))
        with pytest.raises(rtc.RpcError): await room.handlers['approval.decide'](data('browser-a', 'null'))
        room.events['participant_disconnected'](SimpleNamespace(identity='browser-a'))
        assert manager.closed
        with pytest.raises(rtc.RpcError): await room.handlers['approval.list'](data('browser-a'))
    asyncio.run(scenario())


@pytest.mark.parametrize('action', ['close', 'cancel'])
def test_stop_during_execution_marks_unknown_and_does_not_retry(action):
    async def scenario():
        manager = ApprovalManager('s')
        entered = asyncio.Event(); release = asyncio.Event(); calls = []
        async def execute(args):
            calls.append(args)
            entered.set()
            await release.wait()
            return {'status': 'sent'}
        task = asyncio.create_task(manager.run('send_email', {'body': 'b'}, execute))
        await asyncio.sleep(0)
        op = manager.snapshot()['proposal']
        manager.decide('s', op['execution_id'], True)
        await entered.wait()
        if action == 'close':
            manager.close(); release.set()
            await task
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        assert manager.operations[op['execution_id']].state == 'result_unknown'
        with pytest.raises(ToolError): await manager.run('send_email', {'body': 'b'}, execute)
        assert len(calls) == 1
    asyncio.run(scenario())


def test_approval_that_expires_before_execution_does_not_run():
    async def scenario():
        manager = ApprovalManager('s')
        client = MagicMock()
        task = asyncio.create_task(GmailTools(client, manager).search_emails())
        await asyncio.sleep(0)
        op = next(iter(manager.operations.values()))
        manager.decide('s', op.execution_id, True)
        op.deadline = 0
        with pytest.raises(ToolError): await task
        assert not client.mock_calls
    asyncio.run(scenario())
