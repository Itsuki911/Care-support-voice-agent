import asyncio
import base64
import json
import os
import socket
import threading
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from unittest.mock import MagicMock

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from livekit.agents import ToolError

import gmail_auth
import gmail_tools as gmail
from agent import TerminalAssistant


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Tests must not contact external services')
    monkeypatch.setattr(socket, 'create_connection', blocked)


@pytest.fixture
def setup_client():
    service = MagicMock()
    messages = service.users.return_value.messages.return_value
    factory = MagicMock(return_value=service)
    return gmail.GmailClient(factory), messages, service, factory


def raw_message(body='こんにちは', html=False):
    message = EmailMessage()
    message['From'] = 'Sender <sender@example.com>'
    message['To'] = 'to@example.com'
    message['Subject'] = '日本語の件名'
    message.set_content(body, subtype='html' if html else 'plain')
    return {'id': '123abc', 'threadId': 'thread1', 'raw': base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip('=')}


def test_search_empty_and_pagination(setup_client):
    client, messages, service, _ = setup_client
    messages.list.return_value.execute.return_value = {}
    assert client.search() == {'messages': [], 'next_page_token': ''}
    messages.list.assert_called_with(userId='me', q='in:inbox', maxResults=5, pageToken=None)
    messages.list.return_value.execute.assert_called_with(num_retries=0)
    messages.list.return_value.execute.return_value = {'messages': [{'id': 'a'}], 'nextPageToken': 'next'}
    assert client.search('is:unread', 2, 'old')['next_page_token'] == 'next'
    messages.list.assert_called_with(userId='me', q='is:unread', maxResults=2, pageToken='old')
    assert service.close.call_count == 2


@pytest.mark.parametrize('count', [0, 21, -1, True, '5', 1.5])
def test_invalid_count_before_network(setup_client, count):
    with pytest.raises(gmail.GmailError):
        setup_client[0].search(max_results=count)
    setup_client[3].assert_not_called()


@pytest.mark.parametrize('kwargs', [{'query': 'x' * 1001}, {'query': None}, {'page_token': 'x' * 2001}])
def test_invalid_search(setup_client, kwargs):
    with pytest.raises(gmail.GmailError):
        setup_client[0].search(**kwargs)
    setup_client[3].assert_not_called()


def test_read_japanese_and_no_mark_as_read(setup_client):
    client, messages, _, _ = setup_client
    messages.get.return_value.execute.return_value = raw_message()
    result = client.read('123abc')
    assert result['subject'] == '日本語の件名'
    assert result['body'].strip() == 'こんにちは'
    assert result['truncated'] is False
    messages.get.assert_called_once_with(userId='me', id='123abc', format='raw')
    messages.modify.assert_not_called()


@pytest.mark.parametrize('message_id', ['', '../x', 'x\n', None, 'a' * 257])
def test_invalid_id(setup_client, message_id):
    with pytest.raises(gmail.GmailError):
        setup_client[0].read(message_id)
    setup_client[3].assert_not_called()


def test_mime_prefers_plain_over_html_and_attachment():
    message = EmailMessage()
    message.set_content('plain本文')
    message.add_alternative('<p>html本文</p>', subtype='html')
    message.add_attachment(b'private attachment', maintype='application', subtype='octet-stream', filename='file.txt')
    result = gmail.decode_message({'id': 'a', 'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})
    assert result['body'].strip() == 'plain本文'
    assert result['from'] == ''


def test_html_only_does_not_return_script():
    result = gmail.decode_message(raw_message('<p>こんにちは &amp; hello</p><script>secret()</script><style>hidden</style>', html=True))
    assert 'こんにちは & hello' in result['body']
    assert 'secret' not in result['body'] and 'hidden' not in result['body']


def test_long_body_is_explicitly_truncated():
    result = gmail.decode_message(raw_message('x' * 21000))
    assert result['truncated'] is True and len(result['body']) == 20000


@pytest.mark.parametrize('data', [{}, {'id': 'x', 'raw': '%%%'}, {'id': 'x', 'raw': None}])
def test_invalid_mime(data):
    with pytest.raises(gmail.GmailError):
        gmail.decode_message(data)


def test_send_real_mime_roundtrip_and_no_retry(setup_client):
    client, messages, service, _ = setup_client
    messages.send.return_value.execute.return_value = {'id': 'sent1', 'threadId': 't1'}
    assert client.send('to@example.com', '日本語の件名', 'こんにちは\n二行目')['status'] == 'sent'
    args = messages.send.call_args.kwargs
    assert args['userId'] == 'me'
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(args['body']['raw']))
    assert str(message['To']) == 'to@example.com'
    assert str(message['Subject']) == '日本語の件名'
    assert message.get_content().strip() == 'こんにちは\n二行目'
    assert message.get_content_type() == 'text/plain'
    messages.send.return_value.execute.assert_called_once_with(num_retries=0)
    service.close.assert_called_once()


@pytest.mark.parametrize('recipient,subject,body', [
    ('bad', 's', 'b'), ('.a@example.com', 's', 'b'), ('a..b@example.com', 's', 'b'), ('a@example.com,b@example.com', 's', 'b'),
    ('a@example.com\r\nBcc: b@example.com', 's', 'b'),
    ('a@example.com', 's\nBcc: b@example.com', 'b'),
    ('a@example.com', '', 'b'), ('a@example.com', 's', ' '),
    ('a@example.com', 'x' * 999, 'b'), ('a@example.com', 's', 'x' * 100001),
    (None, 's', 'b'), ('a@example.com', None, 'b'), ('a@example.com', 's', None),
])
def test_invalid_send_before_network(setup_client, recipient, subject, body):
    with pytest.raises(gmail.GmailError):
        setup_client[0].send(recipient, subject, body)
    setup_client[3].assert_not_called()


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
def test_http_errors_redacted_and_resources_closed(setup_client, status):
    client, messages, service, _ = setup_client
    messages.list.return_value.execute.side_effect = HttpError(httplib2.Response({'status': str(status)}), b'sensitive-response-secret')
    with pytest.raises(gmail.GmailError) as error:
        client.search()
    assert 'sensitive' not in str(error.value)
    service.close.assert_called_once()


def test_timeout_does_not_retry_send(setup_client):
    client, messages, service, _ = setup_client
    messages.send.return_value.execute.side_effect = TimeoutError('sensitive')
    with pytest.raises(gmail.GmailError, match='自動再送しない'):
        client.send('to@example.com', 's', 'b')
    assert messages.send.return_value.execute.call_count == 1
    service.close.assert_called_once()


def test_missing_token_lazy_and_agent_tools_registered(monkeypatch, tmp_path):
    monkeypatch.setenv('GMAIL_TOKEN_FILE', str(tmp_path / 'missing.json'))
    assistant = TerminalAssistant()
    assert {t.id for t in assistant.tools} == {'search_emails', 'read_email', 'send_email'}
    with pytest.raises(gmail.GmailError, match='認証'):
        gmail.build_service()


def test_malformed_token_redacted(monkeypatch, tmp_path):
    path = tmp_path / 'token.json'
    path.write_text('not-json-sensitive')
    monkeypatch.setenv('GMAIL_TOKEN_FILE', str(path))
    with pytest.raises(gmail.GmailError) as error:
        gmail.build_service()
    assert 'sensitive' not in str(error.value)


def test_scope_and_refresh_failures(monkeypatch):
    credentials = MagicMock()
    monkeypatch.setattr(gmail.Credentials, 'from_authorized_user_file', lambda _: credentials)
    credentials.has_scopes.return_value = False
    with pytest.raises(gmail.GmailError, match='権限'):
        gmail.build_service()
    credentials.has_scopes.return_value = True
    credentials.valid = False
    credentials.refresh_token = None
    with pytest.raises(gmail.GmailError, match='再認証'):
        gmail.build_service()
    credentials.refresh_token = 'fake'
    credentials.refresh.side_effect = RefreshError('sensitive')
    with pytest.raises(gmail.GmailError) as error:
        gmail.build_service()
    assert 'sensitive' not in str(error.value)


def test_valid_credentials_build_real_transport_without_network(monkeypatch):
    credentials = MagicMock(valid=True)
    credentials.has_scopes.return_value = True
    monkeypatch.setattr(gmail.Credentials, 'from_authorized_user_file', lambda _: credentials)
    builder = MagicMock()
    monkeypatch.setattr(gmail, 'build', builder)
    gmail.build_service()
    assert builder.call_args.args == ('gmail', 'v1')
    assert builder.call_args.kwargs['cache_discovery'] is False
    credentials.refresh.assert_not_called()


def test_tool_executes_off_event_loop_and_converts_errors():
    main_thread = threading.get_ident()
    client = MagicMock()
    client.search.side_effect = lambda *args: {'other_thread': threading.get_ident() != main_thread}
    tools = gmail.GmailTools(client)
    assert asyncio.run(tools.search_emails())['other_thread']
    client.send.side_effect = gmail.GmailError('safe error')
    with pytest.raises(ToolError, match='safe error'):
        asyncio.run(tools.send_email('to@example.com', 'subject', 'body'))
    client.read.return_value = {'id': 'x'}
    assert asyncio.run(tools.read_email('x')) == {'id': 'x'}


def test_auth_save_atomic_permissions_and_overwrite(tmp_path):
    path = tmp_path / '.secrets' / 'token.json'
    gmail_auth.save_token(path, '{"test":1}')
    gmail_auth.save_token(path, '{"test":2}')
    assert json.loads(path.read_text()) == {'test': 2}
    # Windows の ACL は POSIX の 0600 モード値へ対応付けられない。
    # Unix 系では秘密トークンの所有者専用パーミッションを検証する。
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    assert list(path.parent.iterdir()) == [path]


def test_auth_missing_client_reports_safe_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('GMAIL_CLIENT_SECRET_FILE', str(tmp_path / 'missing'))
    assert gmail_auth.main() == 1
    assert '失敗' in capsys.readouterr().out


def test_auth_flow_saved_without_printing_token(monkeypatch, tmp_path, capsys):
    flow = MagicMock()
    flow.run_local_server.return_value.to_json.return_value = '{"token":"sensitive"}'
    monkeypatch.setattr(gmail_auth.InstalledAppFlow, 'from_client_secrets_file', lambda *args: flow)
    target = tmp_path / 'token.json'
    monkeypatch.setenv('GMAIL_TOKEN_FILE', str(target))
    assert gmail_auth.main() == 0
    assert json.loads(target.read_text())['token'] == 'sensitive'
    assert 'sensitive' not in capsys.readouterr().out
    assert flow.run_local_server.call_args.kwargs['timeout_seconds'] == 180


def test_relative_config_path(monkeypatch):
    monkeypatch.setenv('GMAIL_TOKEN_FILE', 'private/token.json')
    assert gmail.configured_path('GMAIL_TOKEN_FILE', 'unused') == gmail.BASE_DIR / 'private/token.json'


def test_transport_error_and_cleanup_do_not_expose_sensitive_details(setup_client):
    client, messages, service, _ = setup_client
    messages.list.return_value.execute.side_effect = httplib2.ServerNotFoundError('sensitive')
    service.close.side_effect = OSError('cleanup sensitive')
    with pytest.raises(gmail.GmailError) as error:
        client.search()
    assert 'sensitive' not in str(error.value)


def test_refresh_success_builds_service(monkeypatch):
    credentials = MagicMock(valid=False, refresh_token='fake')
    credentials.has_scopes.return_value = True
    monkeypatch.setattr(gmail.Credentials, 'from_authorized_user_file', lambda _: credentials)
    builder = MagicMock()
    monkeypatch.setattr(gmail, 'build', builder)
    gmail.build_service()
    credentials.refresh.assert_called_once()
    builder.assert_called_once()
