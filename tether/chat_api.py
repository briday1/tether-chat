"""Tracked chat endpoints, independent of any browser's connection lifetime."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from . import chat_jobs, store
from . import attention

router = APIRouter()

class AttentionTarget(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    action_id: str | None = Field(default=None, max_length=100)

class SubmitMessage(BaseModel):
    text: str = Field(default='', max_length=50000)
    request_id: str = Field(min_length=8, max_length=100)
    attention: AttentionTarget | None = None
    task_context: list[str] | None = Field(default=None, max_length=10)

@router.get('/api/chat/state')
def state():
    return chat_jobs.state()

@router.post('/api/chat/jobs', status_code=202)
def submit(data: SubmitMessage):
    try:
        context = {'kind': 'attention', **data.attention.model_dump()} if data.attention else None
        if not data.attention and data.task_context is not None:
            ids = list(dict.fromkeys(data.task_context))
            if any(not store.get(task_id) for task_id in ids):
                raise ValueError('A selected context task no longer exists. Remove it and try again.')
            context = {'kind': 'task_context', 'task_ids': ids}
        message = attention.prompt(data.attention.task_id, data.attention.action_id) if data.attention else data.text
        return chat_jobs.submit(message, data.request_id, context)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class ActionNote(BaseModel):
    body: str = Field(min_length=1,max_length=20000)
    note_id: str | None = Field(default=None,min_length=8,max_length=100)

@router.get('/api/actions/{action_id}/notes')
def list_action_notes(action_id: str):
    notes=store.action_notes(action_id)
    if notes is None:raise HTTPException(404,'Action not found')
    return notes

@router.post('/api/actions/{action_id}/notes',status_code=201)
def create_action_note(action_id: str, data: ActionNote):
    try:note=store.add_action_note(action_id,data.body,data.note_id)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if note is None:raise HTTPException(404,'Action not found')
    return note

@router.patch('/api/actions/{action_id}/notes/{note_id}')
def edit_action_note(action_id: str, note_id: str, data: ActionNote):
    try:note=store.update_action_note(action_id,note_id,data.body)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if note is None:raise HTTPException(404,'Note not found under this action')
    return note

@router.delete('/api/actions/{action_id}/notes/{note_id}')
def remove_action_note(action_id: str,note_id: str):
    if not store.delete_action_note(action_id,note_id):raise HTTPException(404,'Note not found under this action')
    return {'deleted':True}
