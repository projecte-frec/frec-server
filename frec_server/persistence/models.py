import datetime
from enum import StrEnum
from typing import Optional
import uuid
import hashlib

from sqlmodel import JSON, Column, Field, SQLModel, LargeBinary


# ========================
#     User Management
# ========================


class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    username: str = Field(index=True)
    email_address: str = Field(index=True)
    password_hash: str
    is_admin: bool

    @staticmethod
    def hash_password(password: str) -> str:
        gen = hashlib.sha512()
        gen.update(password.encode("utf-8"))
        password_sha512 = gen.hexdigest()
        return password_sha512


class UserToken(SQLModel, table=True):
    token_sha512: str = Field(primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    last_chars: str

    @staticmethod
    def token_prefix() -> str:
        return "ftk"

    @staticmethod
    def hash_token_str(token_str: str) -> str:
        gen = hashlib.sha512()
        gen.update(token_str.encode("utf-8"))
        token_sha512 = gen.hexdigest()
        return token_sha512

    @staticmethod
    def generate(user_id: uuid.UUID) -> tuple[str, "UserToken"]:
        token_str = f"{UserToken.token_prefix()}{uuid.uuid4()}"
        token_hash = UserToken.hash_token_str(token_str)
        return token_str, UserToken(
            token_sha512=token_hash, user_id=user_id, last_chars=token_str[-6:]
        )


class UserSession(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    issued_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    last_access: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)

    @staticmethod
    def expiry_time_seconds() -> int:
        return 60 * 30


# ========================
#      Conversations
# ========================


class MessageRole(StrEnum):
    User = "user"
    Assistant = "assistant"
    System = "system"
    Tool = "tool"

    def visible_in_frontend(self) -> bool:
        match self:
            case MessageRole.User:
                return True
            case MessageRole.Assistant:
                return True
            case MessageRole.System:
                return False
            case MessageRole.Tool:
                return False


class ChatMessage(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    conversation_id: uuid.UUID = Field(foreign_key="conversation.id", index=True)
    role: MessageRole
    raw_content: str
    visible_content: str


class ToolCallStatus(StrEnum):
    PendingConfirm = "PendingConfirm"
    Rejected = "Rejected"
    PendingExecution = "PendingExecution"
    PendingExternalResult = "PendingExternalResult"
    Completed = "Completed"


class ToolCall(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    # The message in which this tool call was invoked
    message_id: uuid.UUID = Field(foreign_key="chatmessage.id", index=True)
    # The role=MessageRoles.Tool message that contains the output for this tool
    reply_message_id: uuid.UUID | None = Field(
        foreign_key="chatmessage.id", index=True, default=None
    )
    status: ToolCallStatus
    toolset_key: str
    tool_key: str
    tool_args: dict = Field(sa_column=Column(JSON))
    tool_answer: dict | None = Field(default=None, sa_column=Column(JSON))

    def display_name(self) -> str:
        return f"{self.toolset_key}.{self.tool_key}"


class DocumentCitation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    # The message id containing the assistant reply where this citation is displayed
    message_id: uuid.UUID = Field(foreign_key="chatmessage.id", index=True)
    # The rag tool used to produce this citation
    rag_toolset_key: str
    # Reference to the chunk in the rag server's database
    rag_chunk_id: uuid.UUID
    # The literal text used by the citation, e.g. "[r32]"
    citation_literal: str
    text_contents: str
    document_filename: str | None
    page_start: int | None
    page_end: int | None
    encoded_heading_path: str | None = None

    def get_heading_path(self) -> list[str] | None:
        return (
            DocumentCitation.decode_heading_path(p)
            if (p := self.encoded_heading_path) is not None
            else None
        )

    @staticmethod
    def decode_heading_path(encoded: str) -> list[str]:
        return encoded.split("||||")

    @staticmethod
    def encode_heading_path(heading_path: list[str]) -> str:
        return "||||".join(heading_path)


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    name: str | None = Field(default=None)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    visible_on_web: bool


class ConversationFile(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    conversation_id: uuid.UUID = Field(foreign_key="conversation.id", index=True)
    data: bytes = Field(sa_column=Column(LargeBinary))
    mime_type: str
    filename: Optional[str]


# ========================
#     Tool Connections
# ========================


class ToolPermissionKind(StrEnum):
    Disable = "Disable"
    AskEveryTime = "AskEveryTime"
    AutoExecute = "AutoExecute"

    def display(self) -> str:
        match self:
            case ToolPermissionKind.Disable:
                return "Off"
            case ToolPermissionKind.AskEveryTime:
                return "Ask"
            case ToolPermissionKind.AutoExecute:
                return "Auto"


class ToolsetConfig(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    toolset_key: str
    enabled: bool


class ToolPermission(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    toolset_key: str
    tool_key: str
    kind: ToolPermissionKind
