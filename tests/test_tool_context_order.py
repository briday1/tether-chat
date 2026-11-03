"""Retrieval keeps selected action identity and serialized conversation order."""
import json
import pytest
from tether import ai, chat_jobs, store
from tether.task_context import search_history


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path/'context-order.sqlite3'))
    store.init()


def test_explicit_action_context_overrides_the_original_action_selection(database, monkeypatch):
    task = store.create('Forms')
    original = store.add(task['id'], 'action', 'Find the form')
    requested = store.add(task['id'], 'action', 'Get the signature')
    calls = []

    def provider(transcript, **kwargs):
        calls.append(json.loads(json.dumps(transcript)))
        if len(calls) == 1:
            return {'choices': [{'message': {'tool_calls': [{
                'id': 'read-other-action', 'function': {'name': 'get_context',
                'arguments': json.dumps({'action_id': requested['id']})}}]}}]}
        result = json.loads(transcript[-1]['content'])
        assert result['focused_action']['id'] == requested['id']
        return {'choices': [{'message': {'content': 'The requested action was checked.'}}]}

    monkeypatch.setattr(ai, 'request', provider)
    answer = ai.chat('Read the other action', history=[], task_context=[task['id']],
                     action_context=original['id'])
    assert answer['actions'] == ['get_context']
    assert len(calls) == 2


def test_history_search_works_before_chat_queue_initialization(database):
    assert not store.query("SELECT name FROM sqlite_master WHERE name='chat_jobs'")
    message_id = store.remember('user', 'Contract note recorded through a direct client')
    result = search_history('contract', 1)
    assert [message['id'] for message in result['messages']] == [message_id]
    assert result['has_more'] is False


def test_history_search_excludes_pending_requests_before_limiting_results(database):
    chat_jobs.initialize()
    for status in ('done', 'running', 'queued'):
        message_id = store.remember('user', f'Contract instruction for the {status} request')
        with store.conn() as connection:
            connection.execute('''INSERT INTO chat_jobs
                (id,message,context,status,progress,created_at,updated_at,user_message_id)
                VALUES(?,?,?,?,?,?,?,?)''',
                ('job-'+status, 'Contract instruction', '{}', status, '[]',
                 store.now(), store.now(), message_id))
        if status == 'done':completed_message = message_id
    result = search_history('contract', 1)
    assert [message['id'] for message in result['messages']] == [completed_message]
    assert result['has_more'] is False
