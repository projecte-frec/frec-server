import asyncio
import datetime
import os
import random
import re
from signal import Signals
from typing import Literal
from uuid import UUID

import aiohttp
import htpy
from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.consts import ElementPatchMode
from datastar_py.fastapi import DatastarResponse, ReadSignals
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from pt_chat_frontend import configuration
import pt_chat_frontend.executor.conversation_task as ct
import pt_chat_frontend.llm.inference as inference
import pt_chat_frontend.pages.chat.views as views
from pt_chat_frontend.pages.common import (
    markdown_to_html,
    get_request_user,
    get_request_user_id,
)
import pt_chat_frontend.persistence.models as models

from pt_chat_frontend.executor.conversation_task_manager import get_global_task_manager
from pt_chat_frontend.persistence import db_queries, db as database
from pt_chat_frontend.tool_calling import rag_client
from pt_chat_frontend.utils import uuid_to_html_id


ctaskmgr = get_global_task_manager()
db = database.get_global_db()
cache_key = abs(random.randint(0, 9999999))


def register_routes(app: FastAPI):
    @app.post(
        "/attach_conversation_task/{conversation_id}", response_class=DatastarResponse
    )
    def attach_conversation_task(conversation_id: str, signals: ReadSignals):
        async def inner():
            print("ATTACH conversation task")
            ctask = ctaskmgr.get_conversation(UUID(conversation_id))
            yield SSE.patch_signals(
                {views.ChatSignals.UserCanSendInput: ctask.ready_for_user_message}
            )

            rendered_messages = set()

            def update_message_content(
                message_id: UUID,
                content: str,
                role: models.MessageRole,
                tool_calls: list[models.ToolCall],
                citations: list[models.DocumentCitation],
            ):
                if message_id not in rendered_messages:
                    rendered_messages.add(message_id)
                    yield SSE.patch_elements(
                        elements=views.chat_message(
                            uuid_to_html_id(message_id), role, tool_calls, citations
                        ),
                        selector=f"#{views.Ids.MessagesList}",
                        mode=ElementPatchMode.APPEND,
                    )

                yield SSE.patch_elements(
                    elements=markdown_to_html(content),
                    selector=f"#{uuid_to_html_id(message_id)}",
                    mode=ElementPatchMode.INNER,
                )
                yield SSE.execute_script(
                    f"window.{views.JsFunctions.ScrollChatToBottom}();"
                )

            def refresh_chat():
                print("Refreshing chat")
                rendered_messages.clear()

                # Clear the chat list
                yield SSE.patch_elements(
                    elements="",
                    selector=f"#{views.Ids.MessagesList}",
                    mode=ElementPatchMode.INNER,
                )

                messages = db_queries.get_conversation_messages(
                    db, UUID(conversation_id)
                )
                for message in messages:

                    if message.role in [
                        models.MessageRole.User,
                        models.MessageRole.Assistant,
                    ]:
                        tool_calls = db_queries.get_message_tool_calls(db, message.id)
                        citations = db_queries.get_message_citations(db, message.id)
                        print(f"Patching message {message.id}")
                        for ev in update_message_content(
                            message.id,
                            message.visible_content,
                            role=message.role,
                            tool_calls=list(tool_calls),
                            citations=list(citations),
                        ):
                            yield ev

            for ev in refresh_chat():
                yield ev

            with ctask.subscribe_to_output_event() as sub:
                while True:
                    new_event = await sub.get()
                    if new_event is None:
                        # TODO: When does this happen? Is it safe to ignore? Maybe we
                        # should display an error.
                        continue

                    if type(new_event) == ct.MessageUpdate:
                        if new_event.role in [
                            models.MessageRole.User,
                            models.MessageRole.Assistant,
                        ]:
                            for ev in update_message_content(
                                new_event.message_id,
                                new_event.content,
                                new_event.role,
                                # NOTE: This is typically a streaming update, so we do not
                                # fetch tool calls and citations from the db. Those are
                                # typically only fetched after the message streaming has
                                # finished and a full refresh is triggered
                                tool_calls=[],
                                citations=[],
                            ):
                                yield ev
                    elif type(new_event) == ct.UpdateReadyState:
                        yield SSE.patch_signals(
                            {
                                views.ChatSignals.UserCanSendInput: new_event.ready_for_user_messages
                            }
                        )
                        yield SSE.execute_script(
                            f"window.{views.JsFunctions.FocusInputBox}();"
                        )
                    elif type(new_event) == ct.ConversationTitleUpdate:
                        yield SSE.patch_signals(
                            {views.ChatSignals.TitleValue: new_event.new_title}
                        )
                    elif type(new_event) == ct.ToolStatusChanged:
                        patched_tool_call = db_queries.get_tool_call(
                            db, new_event.tool_call_id
                        )
                        patched_tool_call.status = new_event.new_status
                        patched_tool_call.tool_answer = new_event.tool_result
                        yield SSE.patch_elements(
                            elements=views.tool_call_box(patched_tool_call),
                            selector=f"#{uuid_to_html_id(new_event.tool_call_id)}",
                            mode=ElementPatchMode.OUTER,
                        )
                    elif type(new_event) == ct.Refresh:
                        for ev in refresh_chat():
                            yield ev

        return DatastarResponse(inner())

    @app.post("/send-message/{conversation_id}")
    async def send_message(
        request: Request, conversation_id: str, signals: ReadSignals
    ):
        assert signals

        async def inner():
            message = signals[views.ChatSignals.UserMessage]
            if conversation_id == "new":
                ctask, new_conv = ctaskmgr.start_new_conversation(
                    user_id=get_request_user_id(request),
                    name=None,
                    visible_on_web=True,
                )
                post_script = f"window.location.replace('/chat/{new_conv.id}');"
            else:
                ctask = ctaskmgr.get_conversation(UUID(conversation_id))
                post_script = None
            ctask.send_input_event(ct.UserMessage(content=message))
            yield SSE.patch_signals({views.ChatSignals.UserMessage: ""})
            if post_script is not None:
                yield SSE.execute_script(post_script)

        return DatastarResponse(inner())

    @app.post("/tool-consent/{toolcall_id}/{consent_status}")
    async def tool_consent(
        toolcall_id: UUID, consent_status: Literal["accept"] | Literal["reject"]
    ):
        tool = db_queries.get_tool_call(db, toolcall_id)
        message = db_queries.get_message(db, tool.message_id)
        conversation = db_queries.get_conversation(db, message.conversation_id)

        ctask = ctaskmgr.get_conversation(conversation.id)
        ctask.send_input_event(
            ct.ConsentAction(
                tool_call_id=toolcall_id, user_consents=consent_status == "accept"
            )
        )

    @app.post("/external-tool-output/{toolcall_id}")
    async def external_tool_output(toolcall_id: UUID, signals: ReadSignals):
        tool = db_queries.get_tool_call(db, toolcall_id)
        message = db_queries.get_message(db, tool.message_id)
        conversation = db_queries.get_conversation(db, message.conversation_id)

        assert signals
        tool_output = signals[views.ChatSignals.ExternalToolOutputs][str(toolcall_id)]

        ctask = ctaskmgr.get_conversation(conversation.id)
        ctask.send_input_event(
            ct.ProvideExternalToolOuptut(
                tool_call_id=toolcall_id,
                output=ct.ExternalToolOutput(success=True, response=tool_output),
            )
        )

    @app.post("/rename_conversation/{conversation_id}")
    async def rename_conversation(conversation_id: UUID, signals: ReadSignals):
        assert signals
        new_title = signals[views.ChatSignals.TitleValue]
        conv = db_queries.rename_conversation(db, conversation_id, new_title)

    @app.post("/generate_conversation_title/{conversation_id}")
    async def generate_conversation_title(conversation_id: UUID):
        print("Backend got 'generate_conversation_title'")
        ctask = ctaskmgr.get_conversation(conversation_id)
        ctask.send_input_event(ct.RequestGenerateTitle())

    @app.post("/show-document-citation-overview/{citation_id}")
    async def show_document_citation_overview(citation_id: UUID):
        async def inner():
            citation = db_queries.get_document_citation(db, citation_id)

            # We cleanup the markdown content from some oddities that come from the
            # RAG server such as marker page separators
            filtered_content = ""
            for line in citation.text_contents.splitlines():
                # NOTE: From marker documentation
                # --paginate_output: Paginates the output, using \n\n{PAGE_NUMBER} followed by - * 48, then \n\n
                page_marker_pattern = r"{(\d+)}-{48}"
                if re.match(page_marker_pattern, line) is not None:
                    continue

                filtered_content += line + "\n"

            yield SSE.patch_signals(
                {
                    # NOTE: We must add 1 to the page because PDF viewers in browsers
                    # start counting at 1
                    views.ChatSignals.CitationOverviewModalHref: f"/chat/citations/{citation_id}/document_file?cache_key={cache_key}#page={(citation.page_start or 0)+1}"
                }
            )
            yield SSE.patch_elements(
                selector=f"#{views.Ids.CitationOverviewModalHeading}",
                mode=ElementPatchMode.INNER,
                elements=f"{citation.document_filename}",
            )
            yield SSE.patch_elements(
                selector=f"#{views.Ids.CitationOverviewModalContent}",
                mode=ElementPatchMode.INNER,
                elements=markdown_to_html(
                    filtered_content, cleanup_links=True, remove_images=True
                ),
            )
            yield SSE.execute_script(f"{views.Ids.CitationOverviewModal}.showModal();")

        return DatastarResponse(inner())

    @app.get("/chat")
    def chat_root():
        return RedirectResponse("/chat/new")

    @app.get("/chat/{conversation_id}", response_class=HTMLResponse)
    def chat_view(request: Request, conversation_id: str):
        user = get_request_user(request)
        return str(
            views.chat_page(
                username=user.username,
                conversation=(
                    db_queries.get_conversation(db, UUID(conversation_id))
                    if conversation_id != "new"
                    else None
                ),
                all_conversations=list(db_queries.get_conversations(db, user.id)),
            )
        )

    @app.get("/chat/{conversation_id}/files/{file_id}", response_class=Response)
    def chat_file_view(request: Request, conversation_id: UUID, file_id: UUID):
        user = get_request_user(request)

        try:
            conversation = db_queries.get_conversation(db, conversation_id)
        except:
            return Response(status_code=404, content="Conversation not found")

        # Authorization check
        if conversation.user_id != user.id:
            return Response(status_code=403, content="Forbidden")

        file = db_queries.get_conversation_file(db, conversation_id, file_id)
        if file is None:
            return Response(status_code=404, content="File not found")

        media_type = file.mime_type or "application/octet-stream"
        filename = file.filename or f"{file.id}"

        # Inline for common browser-viewable types; otherwise force download
        inline_types_prefixes = ("image/", "text/")
        inline_types_exact = {
            "application/pdf",
            "application/json",
        }
        is_inline = (
            media_type.startswith(inline_types_prefixes)
            or media_type in inline_types_exact
        )
        disposition = "inline" if is_inline else "attachment"

        headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}

        return Response(
            content=file.data,
            media_type=media_type,
            headers=headers,
        )

    @app.get("/chat/citations/{citation_id}/document_file")
    async def chat_rag_citation_file(request: Request, citation_id: UUID):
        user_id = get_request_user_id(request)
        if not db_queries.validate_user_of_citation(
            db, citation_id=citation_id, user_id=user_id
        ):
            return Response(status_code=403, content="Unauthorized")

        citation = db_queries.get_document_citation(db, citation_id)
        config = configuration.get_config_file()
        if citation.rag_toolset_key not in config.toolsets:
            return Response(
                status_code=404,
                content=f"The RAG server '{citation.rag_toolset_key}' that originally produced this citation is gone from the configuration file.",
            )
        rag_toolset_config = config.toolsets[citation.rag_toolset_key]
        assert type(rag_toolset_config) == configuration.RagToolset

        return await rag_client.get_rag_document_file(
            session=aiohttp.ClientSession(),
            url=rag_toolset_config.url,
            token=rag_toolset_config.token,
            request_headers=request.headers,
            chunk_id=citation.rag_chunk_id,
        )
