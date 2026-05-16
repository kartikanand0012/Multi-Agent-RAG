"""Notebook CRUD endpoints (ownership-enforced)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import Notebook, User
from app.db.session import get_db
from app.retrieval.vector_store import vector_store
from app.cache.redis_cache import query_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notebooks", tags=["notebooks"])


class NotebookCreate(BaseModel):
    id:   str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)


class NotebookUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class NotebookOut(BaseModel):
    id:         str
    name:       str
    doc_count:  int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


async def _get_owned(notebook_id: str, user: User, db: AsyncSession) -> Notebook:
    result = await db.execute(
        select(Notebook).where(Notebook.id == notebook_id, Notebook.user_id == user.id)
    )
    nb = result.scalar_one_or_none()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return nb


@router.post("", response_model=NotebookOut, status_code=201)
async def create_notebook(
    body: NotebookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Notebook).where(Notebook.id == body.id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Notebook ID already exists")

    nb = Notebook(id=body.id, name=body.name, user_id=current_user.id)
    db.add(nb)
    return nb


@router.get("", response_model=list[NotebookOut])
async def list_notebooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notebook).where(Notebook.user_id == current_user.id)
        .order_by(Notebook.updated_at.desc())
    )
    return result.scalars().all()


@router.patch("/{notebook_id}", response_model=NotebookOut)
async def rename_notebook(
    notebook_id: str,
    body: NotebookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = await _get_owned(notebook_id, current_user, db)
    nb.name = body.name
    nb.updated_at = datetime.now(timezone.utc)
    return nb


@router.delete("/{notebook_id}", status_code=204)
async def delete_notebook(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb = await _get_owned(notebook_id, current_user, db)
    try:
        vector_store.delete_notebook(notebook_id)
    except Exception as e:
        logger.warning(f"ChromaDB delete failed for {notebook_id}: {e}")
    query_cache.invalidate(notebook_id)
    await db.delete(nb)
