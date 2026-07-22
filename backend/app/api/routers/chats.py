from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import Chat, Message
from app.schemas import ChatCreate, ChatDetail, ChatOut, MessageCreate, MessageOut

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("", response_model=list[ChatOut])
async def list_chats(user: CurrentUser, db: DbSession) -> list[Chat]:
    result = await db.execute(
        select(Chat).where(Chat.user_id == user.id, Chat.is_archived.is_(False)).order_by(Chat.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, user: CurrentUser, db: DbSession) -> Chat:
    chat = Chat(
        user_id=user.id,
        title=body.title,
        model=body.model,
        system_prompt=body.system_prompt,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat(chat_id: UUID, user: CurrentUser, db: DbSession) -> Chat:
    result = await db.execute(
        select(Chat).options(selectinload(Chat.messages)).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.post("/{chat_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def add_message(chat_id: UUID, body: MessageCreate, user: CurrentUser, db: DbSession) -> Message:
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    message = Message(chat_id=chat.id, role=body.role, content=body.content, model=chat.model)
    db.add(message)
    if chat.title == "New chat" and body.role == "user":
        chat.title = body.content[:80]
    await db.commit()
    await db.refresh(message)
    return message


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def archive_chat(chat_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    chat.is_archived = True
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
