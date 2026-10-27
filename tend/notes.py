"""Plain Markdown notes: portable text first, quiet rows in Conversation."""
import re
from datetime import datetime
from urllib.parse import quote


def text(value):
    """Keep stored content literal, including Markdown and table delimiters."""
    return re.sub(r'([\\`*_\[\]|])', r'\\\1', str(value or '').replace('\n', ' ').replace('\r', ' '))


def task_table(tasks, details=None):
    lines = ['| Task | Context / next action | When |', '| --- | --- | --- |']
    for task in tasks:
        full = details(task['id']) if details else task
        actions = []
        for entry in full.get('entries', []):
            if entry['kind'] != 'action' or entry.get('done'):
                continue
            schedules = []
            if entry.get('due_at'):
                schedules.append('due ' + entry['due_at'][:10])
            if entry.get('revisit_at'):
                schedules.append('Bring to attention ' + entry['revisit_at'][:10])
            actions.append(entry['body'] + (' (' + '; '.join(schedules) + ')' if schedules else ''))
        context = task.get('summary', '')
        if actions:
            context += (' ' if context else '') + 'Next: ' + '; '.join(actions)
        when = []
        if task.get('due_at'):
            when.append('Due ' + task['due_at'][:10])
        if task.get('revisit_at'):
            when.append('Bring to attention ' + task['revisit_at'][:10])
        if task.get('recurrence') and task.get('next_occurrence'):
            when.append('Next occurrence ' + task['next_occurrence'][:10])
        if task.get('state') in ('waiting', 'paused', 'settled'):
            when.append({'waiting': 'Waiting', 'paused': 'Paused', 'settled': 'Done'}[task['state']])
        lines.append(f"| [{text(task['title'])}](/board#task/{quote(task['id'], safe='')}) | {text(context)} | {text('; '.join(when))} |")
    return '\n'.join(lines)


def task_note(title, tasks, details=None, limit=25):
    lines = ['## ' + title, '']
    if not tasks:
        lines.append('Nothing here right now.')
    else:
        lines.append(task_table(tasks[:limit], details))
        if len(tasks) > limit:
            lines.extend(['', f'Showing {limit} of {len(tasks)} tasks. Open Tasks to see the rest.'])
    return '\n'.join(lines)


def brief(data, details=None):
    sections, seen = ['## Daily brief'], set()
    for key, title in [('deadlines', 'Due dates'), ('due', 'Bring to attention'),
                       ('active', 'In progress'), ('waiting', 'Waiting on')]:
        rows = [task for task in data[key] if task['id'] not in seen]
        if not rows:
            continue
        # A task appears once in this rollup, even when several sections match.
        shown = rows[:15]
        seen.update(task['id'] for task in shown)
        sections.append(task_note(title, rows, details, limit=15))
    if not seen:
        sections.append('No due, active, or waiting tasks in this brief.')
    return '\n\n'.join(sections)


def check_in(task, action, path):
    selected = action or task
    title = action['body'] if action else task['title']
    opening = f'[{text(title)}]({path})'
    if action:
        opening += f" in [{text(task['title'])}](/board#task/{quote(task['id'], safe='')})"
    parts = [opening]
    if task.get('summary'):
        parts.append(text(task['summary']))
    if action and action.get('notes'):
        parts.append('Latest note: ' + text(action['notes'][-1]['body']))
    facts = []
    if selected.get('due_at'):
        facts.append(('Due date', selected['due_at'][:10]))
    for label, value in [('Bring to attention', selected.get('revisit_at')),
                         ('Next occurrence', task.get('next_occurrence') if not action and task.get('recurrence') else None)]:
        if value:
            local = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone()
            facts.append((label, local.strftime('%a, %b %d, %Y · %H:%M %Z')))
    if facts:
        parts.append('| Detail | Value |\n| --- | --- |\n' + '\n'.join(f'| {label} | {text(value)} |' for label, value in facts))
    parts.append('What is the latest on this ' + ('action' if action else 'task') + '—is it complete, blocked, or still in progress?')
    return '\n\n'.join(parts)
