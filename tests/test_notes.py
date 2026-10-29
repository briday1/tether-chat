"""Notes retain context and safe, inspectable references in both release paths."""
from html.parser import HTMLParser
import json
from pathlib import Path
import pytest
from tether import commands, notes, store
from tether.rendering import render

FIXTURES = json.loads((Path(__file__).parent/'fixtures/note-replies.json').read_text())


class Content(HTMLParser):
    def __init__(self, html):
        super().__init__();self.tags=[];self.links=[];self.words=[];self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag=='a':self.links.append(dict(attrs).get('href'))
    def handle_data(self, data):
        self.words.append(data)


@pytest.mark.parametrize('example',FIXTURES,ids=lambda e:e['name'])
def test_note_examples_keep_rows_and_links_without_executable_html(example):
    content=Content(render(example['markdown']))
    assert content.tags.count('table')==example['tables']
    assert content.tags.count('tr')==example['rows']+example['tables']
    assert len(content.links)==example['links']
    assert 'script' not in content.tags


def test_local_rollups_keep_actions_schedules_and_literal_stored_text(tmp_path,monkeypatch):
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'notes.sqlite3'));store.init()
    task=store.create('Review [A] | *draft*','Waiting for [feedback](https://example.invalid) | keep both fields.',['Projects','Writing'])
    store.update(task['id'],{'state':'waiting','due_at':'2020-01-01','revisit_at':'2020-01-02T12:00:00Z'})
    action=store.add(task['id'],'action','Check | attachment')
    store.update_action(action['id'],{'due_at':'2020-01-03T12:00:00Z','revisit_at':'2020-01-04T12:00:00Z'})
    done=store.add(task['id'],'action','An already completed action');store.update_action(done['id'],{'done':True})
    archived=store.create('An archived task');store.archive_thread(archived['id'])
    answer=store.daily_brief();html=Content(render(answer))
    # The same task matches deadlines, reminders and waiting, but appears once.
    assert html.links==['/board#task/'+task['id']]
    words=' '.join(html.words)
    for value in ['Review [A] | *draft*','Waiting for [feedback](https://example.invalid) | keep both fields.','Check | attachment (due 2020-01-03; Bring to attention 2020-01-04)','Due 2020-01-01','Bring to attention 2020-01-02']:
        assert value in words
    assert 'An already completed action' not in answer and 'An archived task' not in answer
    recent=commands.execute('/recent')['answer']
    assert archived['id'] not in recent and task['id'] in recent


def test_action_check_in_keeps_only_its_own_notes_and_dates():
    task={'id':'task','title':'Parent','summary':'Shared context','revisit_at':'2030-05-06T12:00:00Z'}
    action={'id':'action','body':'Selected action','due_at':'2030-05-01','revisit_at':None,
            'notes':[{'body':'Keep [this](https://example.invalid) | literal.'}]}
    answer=notes.check_in(task,action,'/board#action/task/action');content=Content(render(answer))
    assert content.links==['/board#action/task/action','/board#task/task']
    assert '2030-05-01' in answer and '2030-05-06' not in answer
    assert 'Keep [this](https://example.invalid) | literal.' in ' '.join(content.words)


def test_note_limits_are_explicit_and_empty_results_stay_plain():
    tasks=[{'id':str(i),'title':'Task '+str(i)} for i in range(3)]
    assert 'Showing 2 of 3 tasks' in notes.task_note('Matches',tasks,limit=2)
    assert '| Task' not in notes.task_note('Matches',[])


def test_desktop_serves_shared_note_assets(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from tether.app import app
    monkeypatch.setenv('TETHER_DB',str(tmp_path/'assets.sqlite3'))
    with TestClient(app,base_url='http://127.0.0.1') as client:
        page=client.get('/').text
        for path in ('/notes.js','/notes.css'):
            assert path in page
            response=client.get(path)
            assert response.status_code==200 and len(response.content)>100


def test_date_only_occurrence_is_not_rendered_as_midnight():
    from tether.notes import check_in
    result=check_in({'id':'r','title':'Tomorrow','recurrence':'daily','next_occurrence':'2026-10-30'},None,'/board#task/r')
    assert '| Next occurrence | 2026-10-30 |' in result
