from datetime import datetime
import time
from typing import Callable, Sequence
from uuid import UUID, uuid4
import uuid
import sqlalchemy
from sqlmodel import Session, select, col
import hashlib

from frec_server import configuration
from frec_server.tool_calling import agent_client, mcp_manager, tool_prompting
import frec_server.persistence.models as m
import frec_server.persistence.db as db
import frec_server.llm.inference as inference


def is_conversation_id_valid(database: db.Database, cid: uuid.UUID):
    with Session(database.engine) as session:
        return session.get(m.Conversation, cid) is not None


def get_conversations(
    database: db.Database, user_id: UUID, visible_on_web_only: bool = True
) -> Sequence[m.Conversation]:
    with Session(database.engine) as session:
        q = select(m.Conversation).where(m.Conversation.user_id == user_id)
        if visible_on_web_only:
            q = q.where(m.Conversation.visible_on_web)
        return session.exec(q).all()


def start_conversation(
    database: db.Database, user_id: UUID, name: str | None, visible_on_web: bool
) -> m.Conversation:
    with Session(database.engine) as session:
        conv_id = uuid4()
        conversation = m.Conversation(
            id=conv_id,
            name=name,
            user_id=user_id,
            visible_on_web=visible_on_web,
        )
        session.add(conversation)

        starting_prompt = tool_prompting.start_tool_call_chat()
        for msg in starting_prompt:
            if msg.role == "assistant":
                role = m.MessageRole.Assistant
            elif msg.role == "user":
                role = m.MessageRole.User
            elif msg.role == "system":
                role = m.MessageRole.System
            message = m.ChatMessage(
                role=role,
                raw_content=msg.content,
                visible_content=msg.content,
                conversation_id=conversation.id,
            )
            session.add(message)

        session.commit()
        session.refresh(conversation)

    return conversation


def get_conversation(database: db.Database, conversation_id: UUID) -> m.Conversation:
    with Session(database.engine) as session:
        return session.get_one(m.Conversation, conversation_id)


def store_conversation_file(
    database: db.Database,
    conversation_id: UUID,
    data: bytes,
    mime_type: str,
    filename: str | None = None,
) -> UUID:

    with Session(database.engine) as session:
        # user_id = get_conversation(database, conversation_id).user_id
        file_id = uuid4()
        conversation_file = m.ConversationFile(
            id=file_id,
            conversation_id=conversation_id,
            filename=filename,
            data=data,
            mime_type=mime_type,
        )
        session.add(conversation_file)
        session.commit()
        print(f"Stored conversation file {file_id}", flush=True)
        return conversation_file.id


def get_conversation_file(
    database: db.Database, conversation_id: UUID, file_id
) -> m.ConversationFile | None:
    with Session(database.engine) as session:
        file = session.get_one(m.ConversationFile, file_id)
        if file and file.conversation_id == conversation_id:
            return file
        return None


def get_message(database: db.Database, message_id: UUID) -> m.ChatMessage:
    with Session(database.engine) as session:
        return session.get_one(m.ChatMessage, message_id)


def delete_conversation(database: db.Database, conversation_id: UUID):
    with Session(database.engine) as session:
        conv = session.get_one(m.Conversation, conversation_id)
        session.delete(conv)
        session.commit()

def rename_conversation(database: db.Database, conversation_id: UUID, new_name: str):
    with Session(database.engine) as session:
        conv = session.get_one(m.Conversation, conversation_id)
        conv.name = new_name
        session.add(conv)
        session.commit()


def get_conversation_messages(
    database: db.Database, conversation_id: UUID
) -> Sequence[m.ChatMessage]:
    with Session(database.engine) as session:
        return session.exec(
            select(m.ChatMessage)
            .where(m.ChatMessage.conversation_id == conversation_id)
            .order_by(col(m.ChatMessage.created_at).asc())
        ).all()


def get_message_tool_calls(
    database: db.Database, message_id: UUID
) -> Sequence[m.ToolCall]:
    with Session(database.engine) as session:
        return session.exec(
            select(m.ToolCall)
            .where(m.ToolCall.message_id == message_id)
            .order_by(col(m.ToolCall.created_at).asc())
        ).all()


def get_tool_reply_message_tool_calls(
    database: db.Database, message_id: UUID
) -> Sequence[m.ToolCall]:
    with Session(database.engine) as session:
        return session.exec(
            select(m.ToolCall)
            .where(m.ToolCall.reply_message_id == message_id)
            .order_by(col(m.ToolCall.created_at).asc())
        ).all()


def _create_message(
    database: db.Database,
    conversation_id: UUID,
    role: m.MessageRole,
    content: str,
) -> UUID:
    with Session(database.engine) as session:
        msg = m.ChatMessage(
            conversation_id=conversation_id,
            role=role,
            raw_content=content,
            visible_content=content,
        )
        session.add(msg)
        msg_id = msg.id

        session.commit()
    return msg_id


def create_user_message(
    database: db.Database, conversation_id: UUID, content: str
) -> UUID:
    return _create_message(database, conversation_id, m.MessageRole.User, content)


def create_empty_assistant_message(
    database: db.Database, conversation_id: UUID
) -> UUID:
    return _create_message(database, conversation_id, m.MessageRole.Assistant, "")


def update_message_content(
    database: db.Database,
    message_id: uuid.UUID,
    new_raw_content: str,
    new_visible_content: str,
):
    with Session(database.engine) as session:
        msg = session.get_one(m.ChatMessage, message_id)
        msg.raw_content = new_raw_content
        msg.visible_content = new_visible_content
        session.add(msg)
        session.commit()


def validate_user_of_citation(
    database: db.Database, citation_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    with Session(database.engine) as session:
        db_user_id = session.exec(
            select(m.User.id)
            .join(m.Conversation, onclause=col(m.User.id) == m.Conversation.user_id)
            .join(
                m.ChatMessage,
                onclause=col(m.Conversation.id) == m.ChatMessage.conversation_id,
            )
            .join(
                m.DocumentCitation,
                onclause=col(m.ChatMessage.id) == m.DocumentCitation.message_id,
            )
            .where(m.DocumentCitation.id == citation_id)
        ).one()
        return user_id == db_user_id


def get_document_citation(
    database: db.Database, citation_id: uuid.UUID
) -> m.DocumentCitation:
    with Session(database.engine) as session:
        return session.get_one(m.DocumentCitation, citation_id)


def add_citation_to_message(
    database: db.Database,
    message_id: uuid.UUID,
    rag_toolset_key: str,
    rag_chunk_id: uuid.UUID,
    citation_literal: str,
    text_contents: str,
    document_filename: str | None,
    page_start: int | None,
    page_end: int | None,
    heading_path: list[str] | None,
) -> uuid.UUID:
    with Session(database.engine) as session:
        citation = m.DocumentCitation(
            message_id=message_id,
            rag_toolset_key=rag_toolset_key,
            rag_chunk_id=rag_chunk_id,
            citation_literal=citation_literal,
            text_contents=text_contents,
            document_filename=document_filename,
            page_start=page_start,
            page_end=page_end,
            encoded_heading_path=(
                m.DocumentCitation.encode_heading_path(heading_path)
                if heading_path is not None
                else None
            ),
        )
        session.add(citation)
        session.commit()
        session.refresh(citation)

    return citation.id


def get_message_citations(
    database: db.Database, message_id: uuid.UUID
) -> Sequence[m.DocumentCitation]:
    with Session(database.engine) as session:
        return session.exec(
            select(m.DocumentCitation).where(
                m.DocumentCitation.message_id == message_id
            )
        ).all()


def create_tool_reply_message(
    database: db.Database,
    conversation_id: UUID,
    content: str,
    tool_calls_being_replied_to: list[UUID],
) -> UUID:
    msg_id = _create_message(
        database,
        conversation_id,
        m.MessageRole.Tool,
        content,
    )
    with Session(database.engine) as session:
        for tool_id in tool_calls_being_replied_to:
            tool_call = session.get_one(m.ToolCall, tool_id)
            tool_call.reply_message_id = msg_id
            session.add(tool_call)
        session.commit()
    return msg_id


def _get_or_init_toolset_config(
    session: Session, user_id: uuid.UUID, toolset_key: str
) -> m.ToolsetConfig:
    toolset_config = session.exec(
        select(m.ToolsetConfig)
        .where(m.ToolsetConfig.user_id == user_id)
        .where(m.ToolsetConfig.toolset_key == toolset_key)
    ).one_or_none()

    if toolset_config is None:
        toolset_config = m.ToolsetConfig(
            user_id=user_id, toolset_key=toolset_key, enabled=False
        )
        session.add(toolset_config)

    return toolset_config


def _get_or_init_tool_permission(
    session: Session, user_id: uuid.UUID, toolset_key: str, tool_key: str
) -> m.ToolPermission:
    tool_perm = session.exec(
        select(m.ToolPermission)
        .where(m.ToolPermission.user_id == user_id)
        .where(m.ToolPermission.toolset_key == toolset_key)
        .where(m.ToolPermission.tool_key == tool_key)
    ).one_or_none()

    if tool_perm is None:
        tool_perm = m.ToolPermission(
            user_id=user_id,
            toolset_key=toolset_key,
            tool_key=tool_key,
            kind=m.ToolPermissionKind.AskEveryTime,
        )
        session.add(tool_perm)

    return tool_perm


def record_reply_message_and_parse_tool_calls(
    database: db.Database, msg_id: UUID, content: str, ignore_tool_calls: bool = False
) -> list[UUID]:
    with Session(database.engine) as session:
        user_id = get_conversation(
            database, get_message(database, msg_id).conversation_id
        ).user_id

        reply_msg = session.get_one(m.ChatMessage, msg_id)
        assert reply_msg.role == m.MessageRole.Assistant
        reply_msg.raw_content = content

        ret_tool_call_ids = []
        visible, tool_calls = tool_prompting.parse_and_strip_tool_calls(content)
        reply_msg.visible_content = visible

        if not ignore_tool_calls:
            cfg_file = configuration.get_config_file()
            for tool_call in tool_calls:
                print(f"PROCESSING TOOL CALL IN PROMPT '{tool_call}'", flush=True)
                toolset_key = tool_call.toolset
                tool_key = tool_call.tool

                if toolset_key not in cfg_file.toolsets:
                    print("ERROR: LLM referenced non-existing toolset", flush=True)
                    continue

                toolset = cfg_file.toolsets[toolset_key]
                toolset_cfg = _get_or_init_toolset_config(session, user_id, toolset_key)
                tool_permission = _get_or_init_tool_permission(
                    session, user_id, toolset_key, tool_key
                )

                if not toolset_cfg.enabled:
                    print("ERROR: LLM referenced disabled toolset", flush=True)
                    continue

                # Fetch the tool permission, and in case it's auto, directly enable execution
                tool_call_status = m.ToolCallStatus.PendingConfirm
                match tool_permission.kind:
                    case m.ToolPermissionKind.Disable:
                        print("ERROR: LLM referenced disabled tool", flush=True)
                        continue
                    case m.ToolPermissionKind.AskEveryTime:
                        pass
                    case m.ToolPermissionKind.AutoExecute:
                        tool_call_status = m.ToolCallStatus.PendingExecution

                db_tool_call = m.ToolCall(
                    message_id=reply_msg.id,
                    status=tool_call_status,
                    toolset_key=toolset_key,
                    tool_key=tool_call.tool,
                    tool_args=tool_call.args,
                )
                session.add(db_tool_call)
                ret_tool_call_ids.append(db_tool_call.id)

        session.add(reply_msg)
        session.commit()

    return ret_tool_call_ids


async def get_tools_prompt(database: db.Database, user_id: UUID) -> str:
    tools_prompt = ""
    with Session(database.engine) as session:
        cfg_file = configuration.get_config_file()
        for toolset_key, toolset in cfg_file.toolsets.items():
            toolset_config = _get_or_init_toolset_config(session, user_id, toolset_key)
            if not toolset_config.enabled:
                continue

            if toolset.kind == "mcp":
                tool_status = await mcp_manager.check_status(
                    toolset_key, toolset.endpoint
                )
                if type(tool_status) is mcp_manager.ChatToolSet:
                    tools_prompt += tool_status.to_prompt(
                        toolset.custom_instructions,
                    )
            elif toolset.kind == "external":
                tools_prompt += tool_prompting.toolset_prompt(
                    toolset_key=toolset_key,
                    custom_instructions=toolset.custom_instructions,
                    contents=str.join(
                        "\n",
                        (
                            tool_prompting.tool_definition_prompt(
                                tool_key, tool.description, tool.input_schema
                            )
                            for tool_key, tool in toolset.tools.items()
                        ),
                    ),
                )
            elif toolset.kind == "rag":
                tools_prompt += tool_prompting.toolset_prompt(
                    toolset_key=toolset_key,
                    custom_instructions=toolset.custom_instructions,
                    contents=tool_prompting.tool_definition_prompt(
                        tool_key="answer_question",
                        tool_description="Use this tool to answer questions about the topic in this toolset.",
                        json_schema={
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "type": "object",
                        },
                    ),
                )
            elif toolset.kind == "agent":
                agent_description = await agent_client.get_agent_description(
                    toolset.url, toolset.agent_key
                )
                tools_prompt += tool_prompting.toolset_prompt(
                    toolset_key=toolset_key,
                    custom_instructions=toolset.custom_instructions,
                    contents=tool_prompting.tool_definition_prompt(
                        tool_key="answer_question",
                        tool_description=agent_description,
                        json_schema={
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                            "type": "object",
                        },
                    ),
                )

            else:
                raise Exception(f"Unhandled toolset kind: '{toolset.kind}'")

    if tools_prompt == "":
        tools_prompt = "This user has no tools configured. You can direct them at the settings page in case tools are needed."

    return tools_prompt


async def get_chat_prompt_for_inference(
    database: db.Database,
    conversation_id: UUID,
) -> list[inference.ChatMessage]:
    user_id = get_conversation(database, conversation_id).user_id
    messages = get_conversation_messages(database, conversation_id)

    tools_prompt = await get_tools_prompt(database, user_id)

    # print("====================================")
    # print(tools_prompt)
    # print("====================================")

    result = []
    for message in messages:
        role = str(message.role)
        assert role in ["assistant", "user", "system", "tool"]

        # The 'tool' role is seen by the LLM as a regular user message.
        if role == "tool":
            role = "user"

        content = message.raw_content
        content = content.replace("$__TOOLS_PROMPT__", tools_prompt)
        content = content.replace(
            "$__CURRENT_DATETIME__", time.strftime("%Y-%m-%d %H:%M:%S")
        )

        result.append(
            inference.ChatMessage(
                role=role,  # type:ignore -- we just checked with an assert
                # NOTE: The tools prompt is dynamically generated on every message based
                # on the currently enabled tools.
                content=content,
            )
        )
    return result


def set_tool_call_consent(database: db.Database, tool_call_id: UUID, consented: bool):
    with Session(database.engine) as session:
        tool = session.get_one(m.ToolCall, tool_call_id)
        tool.status = (
            m.ToolCallStatus.PendingExecution
            if consented
            else m.ToolCallStatus.Rejected
        )
        session.add(tool)
        session.commit()


def set_tool_call_awaiting_for_external_tool(database: db.Database, tool_call_id: UUID):
    with Session(database.engine) as session:
        tool = session.get_one(m.ToolCall, tool_call_id)
        tool.status = m.ToolCallStatus.PendingExternalResult
        session.add(tool)
        session.commit()


def get_tool_call(database: db.Database, tool_call_id: uuid.UUID) -> m.ToolCall:
    with Session(database.engine) as session:
        return session.get_one(m.ToolCall, tool_call_id)


def store_tool_call_result(database: db.Database, toolcall_id: UUID, result: dict):
    with Session(database.engine) as session:
        # Mark this tool as completed
        tool = session.get_one(m.ToolCall, toolcall_id)
        tool.tool_answer = result
        tool.status = m.ToolCallStatus.Completed
        session.add(tool)
        session.commit()


def get_all_toolsets_and_config(
    database: db.Database,
    user_id: UUID,
) -> Sequence[tuple[str, configuration.Toolset, m.ToolsetConfig]]:
    with Session(database.engine) as session:
        cfg_file = configuration.get_config_file()
        result = []
        for toolset_key, toolset in cfg_file.toolsets.items():
            toolset_cfg = _get_or_init_toolset_config(
                session, user_id, toolset_key=toolset_key
            )
            result.append((toolset_key, toolset, toolset_cfg))

        session.commit()
        for _, _, cfg in result:
            session.refresh(cfg)

        return result


def update_toolset_connection_enabled(
    database: db.Database,
    user_id: UUID,
    toolset_key: str,
    update_enabled: Callable[[bool], bool],
) -> bool:
    with Session(database.engine) as session:
        toolset_cfg = _get_or_init_toolset_config(session, user_id, toolset_key)
        new_status = update_enabled(toolset_cfg.enabled)
        toolset_cfg.enabled = new_status
        session.add(toolset_cfg)
        session.commit()
        return new_status


async def get_toolset_permissions(
    database: db.Database, user_id: UUID, toolset_key: str
) -> list[m.ToolPermission]:
    with Session(database.engine) as session:
        cfg_file = configuration.get_config_file()
        toolset = cfg_file.toolsets[toolset_key]

        tool_permissions = []

        if toolset.kind == "mcp":
            status = await mcp_manager.check_status(toolset_key, toolset.endpoint)
            if type(status) is mcp_manager.ChatToolSet:
                for tool_key in status.available_functions:
                    tool_permissions.append(
                        _get_or_init_tool_permission(
                            session,
                            user_id=user_id,
                            toolset_key=toolset_key,
                            tool_key=tool_key,
                        )
                    )
        elif toolset.kind == "external":
            for tool_key, _tool in toolset.tools.items():
                tool_permissions.append(
                    _get_or_init_tool_permission(
                        session,
                        user_id=user_id,
                        toolset_key=toolset_key,
                        tool_key=tool_key,
                    )
                )
        elif toolset.kind == "rag":
            tool_permissions.append(
                _get_or_init_tool_permission(
                    session,
                    user_id=user_id,
                    toolset_key=toolset_key,
                    tool_key="answer_question",
                )
            )
        elif toolset.kind == "agent":
            tool_permissions.append(
                _get_or_init_tool_permission(
                    session,
                    user_id=user_id,
                    toolset_key=toolset_key,
                    tool_key="answer_question",
                )
            )

        else:
            raise Exception(f"Unhandled tool type: {toolset.kind}")

        session.commit()
        for t in tool_permissions:
            session.refresh(t)

        return [t for t in tool_permissions]


def get_tool_permission(
    database: db.Database, tool_permission_id: uuid.UUID
) -> m.ToolPermission:
    with Session(database.engine) as session:
        return session.get_one(m.ToolPermission, tool_permission_id)


def set_tool_permission(
    database: db.Database, tool_permission_id: uuid.UUID, new_kind: m.ToolPermissionKind
):
    with Session(database.engine) as session:
        print(f"THE ID IS '{tool_permission_id}'")
        perm = session.get_one(m.ToolPermission, tool_permission_id)
        perm.kind = new_kind
        session.add(perm)
        session.commit()


def create_user_token(database: db.Database, user_id: uuid.UUID) -> str:
    with Session(database.engine) as session:
        token_str, user_token = m.UserToken.generate(user_id)
        session.add(user_token)
        session.commit()
        return token_str


def delete_user_token(database: db.Database, token_sha512: str):
    with Session(database.engine) as session:
        utk = session.get(m.UserToken, token_sha512)
        session.delete(utk)
        session.commit()


def get_user_id_of_token(database: db.Database, token_str: str) -> uuid.UUID | None:
    with Session(database.engine) as session:
        utk = session.get(m.UserToken, m.UserToken.hash_token_str(token_str))
        if utk is not None:
            return utk.user_id
        else:
            return None


def get_all_tokens_for_user(
    database: db.Database, user_id: UUID
) -> Sequence[m.UserToken]:
    with Session(database.engine) as session:
        return session.exec(
            select(m.UserToken).where(m.UserToken.user_id == user_id)
        ).all()


def sign_in_and_create_user_session(
    database: db.Database, username: str, password: str
) -> m.UserSession | None:
    with Session(database.engine) as session:
        user_count = session.scalar(select(sqlalchemy.func.count(col(m.User.id))))
        if user_count == 0:
            # If the user database is empty, this is a new deployment. In that case, we
            # register a new admin account.
            print(f"First login by {username}. Will become admin")
            admin_user = db.create_admin_user(username, password)
            session.add(admin_user)
            session.commit()
            session.refresh(admin_user)

            user = admin_user
        else:
            user = session.exec(
                select(m.User)
                .where(m.User.username == username)
                .where(m.User.password_hash == m.User.hash_password(password))
            ).one_or_none()

        if user is None:
            return None
        else:
            user_session = m.UserSession(user_id=user.id)
            session.add(user_session)
            session.commit()
            session.refresh(user_session)
            return user_session


def logout(database: db.Database, user_session_id: UUID) -> m.User | None:
    with Session(database.engine) as session:
        user_session = session.get(m.UserSession, user_session_id)
        if user_session is not None:
            session.delete(user_session)
            session.commit()


def validate_user_session(
    database: db.Database, user_session_id: UUID
) -> m.User | None:
    with Session(database.engine) as session:
        user_session = session.get(m.UserSession, user_session_id)
        if user_session is None:
            return None

        time_delta = datetime.now() - user_session.last_access
        if time_delta.total_seconds() > m.UserSession.expiry_time_seconds():
            session.delete(user_session)
            session.commit()
            return None

        user_session.last_access = datetime.now()
        session.commit()
        session.refresh(user_session)

        return session.get_one(m.User, user_session.user_id)


def get_all_users(database: db.Database) -> Sequence[m.User]:
    with Session(database.engine) as session:
        return session.exec(select(m.User)).all()


def get_user(database: db.Database, user_id: UUID) -> m.User:
    with Session(database.engine) as session:
        return session.get_one(m.User, user_id)


def username_exists(session: Session, username: str):
    duplicate_user_count = session.scalar(
        select(sqlalchemy.func.count(col(m.User.id))).where(m.User.username == username)
    )
    return duplicate_user_count is not None and duplicate_user_count > 0


def create_user(
    database: db.Database, username: str, password: str, is_admin: bool
) -> m.User:
    with Session(database.engine) as session:
        if username_exists(session, username):
            raise Exception(f"Duplicate username '{username}'")

        user = m.User(
            username=username,
            password_hash=m.User.hash_password(password),
            email_address="",
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def update_user(
    database: db.Database,
    user_id: UUID,
    username: str | None,
    password: str | None,
    is_admin: bool | None,
) -> m.User:
    with Session(database.engine) as session:
        user = session.get_one(m.User, user_id)
        if username is not None and username != user.username:
            if username_exists(session, username):
                raise Exception(f"Duplicate username '{username}'")

        if username is not None:
            user.username = username
        if password is not None:
            user.password_hash = m.User.hash_password(password)
        if is_admin is not None:
            user.is_admin = is_admin
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def delete_user(
    database: db.Database,
    user_id: UUID,
):
    # TODO: This leaves all the data by this user in the database, leaving it in an
    # inconsistent state. We should either mark the user as deleted, but not remove it
    # from the DB, or cascade-remove all data from this user. The current version is
    # neither one nor the other and is wrong.
    with Session(database.engine) as session:
        user = session.get_one(m.User, user_id)
        session.delete(user)
        session.commit()
