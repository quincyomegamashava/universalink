from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)


# --- Users ---


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    role: str = "user"


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


# --- API Keys ---


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10000)


class ApiKeyOut(ORMModel):
    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    expires_at: datetime | None
    rate_limit_per_minute: int | None
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    raw_key: str


# --- Chats ---


class ChatCreate(BaseModel):
    title: str = "New chat"
    model: str
    system_prompt: str | None = None


class ChatOut(ORMModel):
    id: UUID
    title: str
    model: str
    system_prompt: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    role: str = "user"


class MessageOut(ORMModel):
    id: UUID
    role: str
    content: str
    model: str | None
    token_count: int | None
    created_at: datetime


class ChatDetail(ChatOut):
    messages: list[MessageOut] = []


# --- OpenAI compatible ---


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = 0.7
    max_tokens: int | None = None
    user: str | None = None
    # Platform extension: inject RAG context
    collection_id: UUID | None = None


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = False
    temperature: float | None = 0.7
    max_tokens: int | None = None


class EmbeddingRequest(BaseModel):
    model: str | None = None
    input: str | list[str]


# --- Settings / Admin ---


class SettingUpsert(BaseModel):
    key: str
    value: dict[str, Any]
    description: str | None = None


class SettingOut(ORMModel):
    key: str
    value: dict[str, Any]
    description: str | None
    updated_at: datetime


class UsageSummary(BaseModel):
    total_requests: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class CollectionOut(ORMModel):
    id: UUID
    name: str
    description: str | None
    qdrant_collection: str
    is_active: bool
    created_at: datetime


class DocumentOut(ORMModel):
    id: UUID
    filename: str
    source_type: str
    chunk_count: int
    status: str
    error_message: str | None
    created_at: datetime


class ToolPermissionOut(ORMModel):
    tool_name: str
    role: str
    enabled: bool
    config: dict[str, Any]


class ToolPermissionUpdate(BaseModel):
    enabled: bool
    config: dict[str, Any] | None = None


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    components: list[HealthComponent]
