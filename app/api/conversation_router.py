"""Conversation CRUD endpoints — list, get, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import Conversation, Message, User
from app.db.session import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    convs = result.scalars().all()
    return {
        "conversations": [
            {
                "id":              c.id,
                "notebook_id":     c.notebook_id,
                "title":           c.title,
                "message_count":   c.message_count,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
                "created_at":      c.created_at.isoformat(),
            }
            for c in convs
        ]
    }


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = (await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )).scalars().all()

    return {
        "conversation": {
            "id": conv.id, "notebook_id": conv.notebook_id, "title": conv.title,
        },
        "messages": [
            {
                "id":           m.id,
                "role":         m.role.value,
                "content":      m.content,
                "agent_run_id": m.agent_run_id,
                "created_at":   m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
