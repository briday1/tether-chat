import json
from datetime import datetime, timezone

import pytest

from tether import ai, attention, store
from tether.task_context import build_context, defer_intent, search_history


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('TETHER_DB', str(tmp_path / 'context.sqlite3'))
    store.init()
    monkeypatch.setattr(ai, 'public_config', lambda: {'has_key': False})


def make_actions():
    task = store.create('Prepare the report', categories=['Work'])
    selected = store.add(task['id'], 'action', 'Review the figures')
    sibling = store.add(task['id'], 'action', 'Send the appendix')
    store.update(task['id'], {'due_at': '2020-01-01'})
    for action in (selected, sibling):
        store.update_action(action['id'], {'due_at': '2020-01-01', 'revisit_at': '2020-01-01T09:00:00Z'})
    return task, selected, sibling


def test_short_attention_reply_defers_exact_action_without_provider(database, monkeypatch):
    task, selected, sibling = make_actions()
    monkeypatch.setattr(ai, 'request', lambda *a, **kw: pytest.fail('A scoped deferral must not need the model'))
    before = store.get(task['id'])
    result = ai.chat("Let's do that tomorrow", history=[], task_context=[task['id']], action_context=selected['id'])
    after = store.get(task['id'])
    action = next(e for e in after['entries'] if e['id'] == selected['id'])
    assert result['actions'] == ['defer_action'] and 'out of Attention' in result['answer']
    assert action['due_at'] == '2020-01-01' and store.is_snoozed(action)
    assert after['due_at'] == before['due_at'] and after['revisit_at'] == before['revisit_at']
    assert next(e for e in after['entries'] if e['id'] == sibling['id']) == next(e for e in before['entries'] if e['id'] == sibling['id'])
    ids = {item['id'] for item in attention.items()['items']}
    assert selected['id'] not in ids and sibling['id'] in ids


def test_scoped_task_deferral_hides_deadline_and_child_attention(database, monkeypatch):
    task, selected, sibling = make_actions()
    monkeypatch.setattr(ai, 'request', lambda *a, **kw: pytest.fail('Unexpected model request'))
    result = ai.chat('Please postpone it until tomorrow morning.', history=[], task_context=[task['id']])
    assert result['actions'] == ['defer_task']
    assert not attention.items()['items']
    assert store.get(task['id'])['due_at'] == '2020-01-01'
    assert store.list_threads()[0]['deadline_due']


@pytest.mark.parametrize('text', [
    'If I say "let\'s do that tomorrow", what happens?',
    'Should we do that tomorrow?', 'Move its deadline to tomorrow',
    "Let's do that tomorrow or next week", "Let's do that tomorrow and send it now",
    'Do something tomorrow',
])
def test_only_complete_unambiguous_deferral_commands_are_local(text):
    assert defer_intent(text) is None


def test_multiple_or_cleared_task_selection_never_guesses_a_local_target(database, monkeypatch):
    first = store.create('One')
    second = store.create('Two')
    calls = []
    monkeypatch.setattr(ai, 'request', lambda *a, **kw: calls.append(1) or {'choices': [{'message': {'content': 'Which task do you mean?'}}]})
    for selected in ([first['id'], second['id']], []):
        result = ai.chat("Let's do that tomorrow", history=[], task_context=selected)
        assert result['actions'] == []
    assert len(calls) == 2
    assert not store.get(first['id'])['revisit_at'] and not store.get(second['id'])['revisit_at']


def test_initial_context_keeps_old_open_actions_action_notes_and_current_dates(database):
    task, selected, sibling = make_actions()
    store.add_action_note(selected['id'], 'Use the revised figures approved on Friday.')
    for n in range(30):
        store.add(task['id'], 'thought', f'Later note {n}')
    store.record_activity(task['id'], 'Received the revised figures')
    context = build_context([task['id']], selected['id'])
    assert context['focused_action']['notes'][0]['body'].startswith('Use the revised')
    assert context['focused_action']['due_at'] == '2020-01-01'
    assert selected['id'] in {a['id'] for a in context['focused_task']['actions']}
    assert context['focused_task']['recent_activity'][0]['body'] == 'Received the revised figures'
    other = store.create('Another task')
    with pytest.raises(ValueError, match='belong'):
        build_context([other['id']], selected['id'])


def test_model_can_read_fresh_scoped_context_after_mutation(database, monkeypatch):
    task, selected, _ = make_actions()
    calls = []
    def request(messages, **kwargs):
        calls.append(messages[-1])
        index = len(calls)
        if index == 4:
            context = json.loads(messages[-1]['content'])
            assert context['focused_action']['id'] == selected['id']
            assert context['focused_action']['snoozed_until']
            return {'choices': [{'message': {'content': 'Deferred.'}}]}
        name, args = ('defer_action', {'action_id': selected['id'], 'when': 'tomorrow'}) if index == 2 else ('get_context', {})
        return {'choices': [{'message': {'tool_calls': [{'id': str(index), 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]}
    monkeypatch.setattr(ai, 'request', request)
    result = ai.chat('Please put the selected action off until tomorrow.', history=[], task_context=[task['id']], action_context=selected['id'])
    assert result['actions'] == ['get_context', 'defer_action', 'get_context']


def test_history_search_is_bounded_and_treats_wildcards_as_literal_data(database):
    with store.conn() as db:
        for i, body in enumerate(['100% complete', '100 percent complete', '100% reviewed']):
            db.execute('INSERT INTO conversation(id,role,body,created_at) VALUES(?,?,?,?)', (str(i), 'user', body, store.now()))
    result = search_history('100%', 1)
    assert result['has_more'] and result['messages'][0]['body'] == '100% reviewed'
    assert len(search_history('percent')['messages']) == 1
    with pytest.raises(ValueError):search_history('a')


def test_mcp_deferral_completion_reopen_and_explicit_clearing(database):
    from tether import mcp_server as mcp
    task, selected, sibling = make_actions()
    assert mcp.defer_action_item(selected['id'], 'tomorrow')['snoozed_until']
    assert mcp.get_action_item(selected['id'])['task_id'] == task['id']
    assert mcp.revise_thread(task['id'], due_at='', summary='')['due_at'] is None
    completed = mcp.complete_task(task['id'])
    assert completed['archived_at'] and all(e['done'] for e in completed['entries'])
    restored = mcp.complete_task(task['id'], False)
    assert not restored['archived_at'] and all(not e['done'] for e in restored['entries'])
