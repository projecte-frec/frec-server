import asyncio
from enum import Enum, StrEnum
import traceback
from typing import Any
import uuid

from pydantic import BaseModel

from frec_server import configuration
from frec_server.tool_calling import (
    agent_client,
    mcp_manager,
    rag_client,
    tool_prompting,
)
from frec_server.executor.aio_utils import (
    BroadcastChannel,
    Subscription,
)
from frec_server.llm import inference
from frec_server.llm.inference import LlmInference
from frec_server.persistence import db_queries, models
from frec_server.persistence.db import get_global_db
from frec_server.tool_calling.conversation_title_generator import (
    try_generate_conversation_title,
)

database = get_global_db()


class ConversationInputEvent:
    pass


class UserMessage(BaseModel, ConversationInputEvent):
    content: str


class ConsentAction(BaseModel, ConversationInputEvent):
    tool_call_id: uuid.UUID
    user_consents: bool


class ExternalToolOutput(BaseModel):
    success: bool
    response: str


class ProvideExternalToolOuptut(BaseModel, ConversationInputEvent):
    tool_call_id: uuid.UUID
    output: ExternalToolOutput


class RequestGenerateTitle(BaseModel, ConversationInputEvent):
    pass


class TriggerToolResponse(BaseModel, ConversationInputEvent):
    tool_reply_message_id: uuid.UUID
    assistant_reply_msessage_id: uuid.UUID


class ConversationOutputEvent:
    pass


class MessageUpdate(BaseModel, ConversationOutputEvent):
    """Signals listeners that a message with `message_id` was updated, and now holds the
    given `contents`"""

    message_id: uuid.UUID
    role: models.MessageRole
    content: str


class NeededInputKind(StrEnum):
    AwaitingNextMessage = "awaiting_next_message"
    PendingToolConfirm = "pending_tool_confirm"
    AwaitingExternalTool = "awaiting_external_tool"


class NeedsUserInput(BaseModel, ConversationOutputEvent):
    """Sent when the system is now in a state where user input is required. No further
    action will be performed until input is sent"""

    kind: NeededInputKind


class ConversationError(BaseModel, ConversationOutputEvent):
    """Sent by the conversation when an error is encountered. Most errors are recovered
    and the conversation will be able to continue."""

    message: str
    payload: Any


class UpdateReadyState(BaseModel, ConversationOutputEvent):
    """Signals listeners that a message with `message_id` was updated, and now holds the
    given `contents`"""

    ready_for_user_messages: bool


class ConversationTitleUpdate(BaseModel, ConversationOutputEvent):
    """Signals that the conversation title has been updated by the system"""

    new_title: str


class Refresh(BaseModel, ConversationOutputEvent):
    """Signals listeners that an important operation just finished and they should reload
    the full UI state from the database to avoid any potential desyncs."""

    pass


class ToolStatusChanged(BaseModel, ConversationOutputEvent):
    message_id: uuid.UUID
    tool_call_id: uuid.UUID
    new_status: models.ToolCallStatus
    tool_result: dict | None


class ReadyForNextUserMessage(Enum):
    Yes = 0
    No = 1


class ToolCallTask:
    def __init__(
        self,
        conversation: "ConversationTask",
        tool_call_id: uuid.UUID,
        assistant_reply_msg_id: uuid.UUID,
    ):
        self.tool_call_id: uuid.UUID = tool_call_id
        self.assistant_reply_msg_id: uuid.UUID = assistant_reply_msg_id
        self.result: asyncio.Future[dict | None] = asyncio.Future()
        self.user_consent: asyncio.Future[bool] = asyncio.Future()
        self.external_tool_result: asyncio.Future[ExternalToolOutput] = asyncio.Future()
        self.conversation_task: ConversationTask = conversation

    async def task_loop(self):
        # Check if this tool has already been accepted. This could happen if the tool has
        # automatic permissions or in the rare case we're recovering from a crash.
        initial_status = db_queries.get_tool_call(database, self.tool_call_id).status

        user_consented: bool
        needs_to_process_tool = True

        if initial_status == models.ToolCallStatus.PendingConfirm:
            user_consented = await self.user_consent
            db_queries.set_tool_call_consent(
                database, self.tool_call_id, user_consented
            )
        elif initial_status == models.ToolCallStatus.Rejected:
            user_consented = False
        elif initial_status == models.ToolCallStatus.PendingExecution:
            user_consented = True
        elif initial_status == models.ToolCallStatus.PendingExternalResult:
            user_consented = True
        else:
            # Nothing to do. This is a rare situation that should never occur, but we
            # recover from it gracefully by just returning whatever tool call we need.
            self.conversation_task.report_error(
                f"[WARNING] Tool call {self.tool_call_id} started a task loop but its initial status was {initial_status}. Ignoring"
            )
            self.result.set_result(
                db_queries.get_tool_call(database, self.tool_call_id).tool_answer
            )
            needs_to_process_tool = False
            user_consented = False

        if user_consented and needs_to_process_tool:
            tool_call = db_queries.get_tool_call(database, self.tool_call_id)
            toolset = configuration.get_config_file().toolsets[tool_call.toolset_key]

            result_dict = {
                "success": False,
                "error": "Unknown",
            }

            try:
                if toolset.kind == "mcp":
                    text_so_far = await mcp_manager.call_tool(
                        database,
                        self.conversation_task.conversation_id,
                        toolset.endpoint,
                        tool_call.tool_key,
                        tool_call.tool_args,
                    )
                    if type(text_so_far) is mcp_manager.McpToolCallError:
                        result_dict = {
                            "success": False,
                            "error": text_so_far.error,
                        }
                    elif type(text_so_far) is mcp_manager.ToolResponse:
                        result_dict = {
                            "success": True,
                            "response": text_so_far.response,
                            "should_display_verbatim": text_so_far.should_display_verbatim,
                        }
                elif toolset.kind == "external":
                    # First, we notify the frontend/client that we are awaiting a reply
                    # for the result of the external tool and change the status
                    db_queries.set_tool_call_awaiting_for_external_tool(
                        database, self.tool_call_id
                    )
                    self.conversation_task.output_event_bus.publish(
                        ToolStatusChanged(
                            message_id=tool_call.message_id,
                            tool_call_id=tool_call.id,
                            new_status=models.ToolCallStatus.PendingExternalResult,
                            tool_result=None,
                        )
                    )
                    self.conversation_task.output_event_bus.publish(
                        NeedsUserInput(kind=NeededInputKind.AwaitingExternalTool)
                    )
                    external_result = await self.external_tool_result
                    result_dict = {
                        "success": external_result.success,
                        "response": external_result.response,
                    }
                elif toolset.kind == "rag":
                    if "query" not in tool_call.tool_args:
                        result_dict = {
                            "success": False,
                            "response": "Invalid tool call. You must provide a 'query'",
                        }
                    else:
                        text_so_far = ""
                        async for chunk in rag_client.call_rag_client(
                            toolset.url, toolset.token, tool_call.tool_args["query"]
                        ):
                            if type(chunk) == str:
                                # Stream the response directly into the assistant's response.
                                # This tool is "verbatim" so that improves the feeling of
                                # responsiveness.
                                text_so_far += chunk
                                self.conversation_task.output_event_bus.publish(
                                    MessageUpdate(
                                        message_id=self.assistant_reply_msg_id,
                                        role=models.MessageRole.Assistant,
                                        content=text_so_far,
                                    )
                                )
                            elif type(chunk) == rag_client.RagClientResponse:
                                # Add the citations for this message to the database and update the message with the final contents.
                                self.conversation_task.output_event_bus.publish(
                                    MessageUpdate(
                                        message_id=self.assistant_reply_msg_id,
                                        role=models.MessageRole.Assistant,
                                        content=chunk.full_response,
                                    )
                                )
                                for cit_literal, citation in chunk.references.items():
                                    db_queries.add_citation_to_message(
                                        database,
                                        message_id=self.assistant_reply_msg_id,
                                        rag_toolset_key=tool_call.toolset_key,
                                        rag_chunk_id=citation.id,
                                        citation_literal=cit_literal,
                                        text_contents=citation.text,
                                        document_filename=citation.document_filename,
                                        page_start=citation.page_start,
                                        page_end=citation.page_end,
                                    )

                                result_dict = {
                                    "success": True,
                                    "response": chunk.full_response,
                                    "should_display_verbatim": True,
                                }
                                break  # No more chunks should come after this, but just in case...
                elif toolset.kind == "agent":
                    if "query" not in tool_call.tool_args:
                        result_dict = {
                            "success": False,
                            "response": "Invalid tool call. You must provide a 'query'",
                        }
                    else:
                        text_so_far = ""
                        did_receive_final = False
                        async for chunk in agent_client.call_agent_client(
                            toolset.url, toolset.agent_key, tool_call.tool_args["query"]
                        ):
                            if type(chunk) == str:
                                # Stream the response directly into the assistant's response.
                                text_so_far += chunk
                                self.conversation_task.output_event_bus.publish(
                                    MessageUpdate(
                                        message_id=self.assistant_reply_msg_id,
                                        role=models.MessageRole.Assistant,
                                        content=text_so_far,
                                    )
                                )
                            elif type(chunk) == agent_client.AgentClientResponse:
                                did_receive_final = True
                                final_text = (
                                    chunk.full_response
                                    if chunk.full_response.strip() != ""
                                    else text_so_far
                                )
                                self.conversation_task.output_event_bus.publish(
                                    MessageUpdate(
                                        message_id=self.assistant_reply_msg_id,
                                        role=models.MessageRole.Assistant,
                                        content=final_text,
                                    )
                                )
                                result_dict = {
                                    "success": True,
                                    "response": final_text,
                                    "should_display_verbatim": True,
                                }
                                break

                        if not did_receive_final:
                            result_dict = {
                                "success": True,
                                "response": text_so_far,
                                "should_display_verbatim": True,
                            }

            except Exception as e:
                error_msg = f"[ERROR] Tool call '{self.tool_call_id}' ({tool_call.toolset_key}, {tool_call.tool_key}) failed with error: {e}."
                self.conversation_task.report_error(error_msg)
                result_dict = {"success": False, "response": error_msg}

            db_queries.store_tool_call_result(database, self.tool_call_id, result_dict)
            self.result.set_result(result_dict)
        else:
            self.result.set_result(None)

        # Regardless of the outcome, we send a ToolStatusChanged event to notify the
        # frontend of the completion status. Note that we fetch the tool again to get the
        # latest state.
        tool_call = db_queries.get_tool_call(database, self.tool_call_id)
        self.conversation_task.output_event_bus.publish(
            ToolStatusChanged(
                message_id=tool_call.message_id,
                tool_call_id=tool_call.id,
                new_status=tool_call.status,
                tool_result=tool_call.tool_answer,
            )
        )


class GenerateTitleTask:
    def __init__(
        self,
        conversation: "ConversationTask",
        messages: list[models.ChatMessage],
    ):
        self.conversation_task: ConversationTask = conversation
        self.messages: list[models.ChatMessage] = messages

    async def task_koop(self):
        print("Starting title generation task")
        title = await try_generate_conversation_title(
            self.conversation_task.llm, self.conversation_task.llm_model, self.messages
        )
        print(f"Got title: {title}")
        if title is not None:
            db_queries.rename_conversation(
                database, self.conversation_task.conversation_id, title
            )
            self.conversation_task.output_event_bus.publish(
                ConversationTitleUpdate(new_title=title)
            )


class ConversationTask:
    def __init__(
        self,
        conversation_id: uuid.UUID,
        llm: LlmInference,
        llm_model: str,
        auto_generate_name: bool = True,
    ) -> None:
        self.llm = llm
        self.llm_model = llm_model
        self.conversation_id = conversation_id
        self.auto_generate_name = auto_generate_name

        self.input_event_bus: asyncio.Queue[ConversationInputEvent] = asyncio.Queue()
        self.ready_for_user_message = True
        self.output_event_bus: BroadcastChannel[ConversationOutputEvent] = (
            BroadcastChannel()
        )

        self.pending_tool_calls: dict[uuid.UUID, ToolCallTask] = {}

        # Popuplate the inner runtime data structures from the DB state.
        self.populate_state_from_db()

    def send_input_event(self, input_event: ConversationInputEvent):
        self.input_event_bus.put_nowait(input_event)

    def subscribe_to_output_event(self) -> Subscription[ConversationOutputEvent]:
        return self.output_event_bus.subscribe()

    def set_ready_for_user_message(self, value: bool):
        self.ready_for_user_message = value
        self.output_event_bus.publish(UpdateReadyState(ready_for_user_messages=value))
        if value:
            self.output_event_bus.publish(
                NeedsUserInput(kind=NeededInputKind.AwaitingNextMessage)
            )

    def populate_state_from_db(self):
        """When starting the task, we could be loading an ongoing conversation. Depending
        on the state of the conversation, we need to initialize internal data
        structures."""

        # Spawn any tasks for pending tools, otherwise the conversation might be stuck
        messages = db_queries.get_conversation_messages(database, self.conversation_id)
        if len(messages) > 0:
            tool_calls = db_queries.get_message_tool_calls(database, messages[-1].id)

            still_pending = [
                t.id
                for t in tool_calls
                if t.status == models.ToolCallStatus.PendingConfirm
                or t.status == models.ToolCallStatus.PendingExecution
                or t.status == models.ToolCallStatus.PendingExternalResult
            ]
            if len(still_pending) > 0:
                self.set_ready_for_user_message(False)
                asyncio.create_task(
                    self.spawn_tools_and_wait_for_completion([t.id for t in tool_calls])
                )

    async def task_loop(self):
        try:
            while input_ev := await self.input_event_bus.get():
                try:
                    print(f"Got input event {input_ev}")
                    match input_ev:
                        case UserMessage():
                            if self.ready_for_user_message:
                                self.set_ready_for_user_message(False)
                                ready = await self.send_user_message(input_ev)

                                print(f"auto_generate_name: {self.auto_generate_name}")
                                print(
                                    f"name is none: {db_queries.get_conversation(database, self.conversation_id).name}"
                                )
                                if (
                                    self.auto_generate_name
                                    and db_queries.get_conversation(
                                        database, self.conversation_id
                                    ).name
                                    is None
                                ):
                                    print("Time to generate title")
                                    await self.generate_conversation_title()

                                if ready == ReadyForNextUserMessage.Yes:
                                    self.set_ready_for_user_message(True)
                            else:
                                print(
                                    f"Ignoring user message that was sent while conversation was busy: {input_ev.content}"
                                )
                        case ConsentAction():
                            print(f"Recived user consent action {input_ev}")
                            await self.set_tool_consent(
                                input_ev.tool_call_id, input_ev.user_consents
                            )
                        case RequestGenerateTitle():
                            print("Requested title generation")
                            await self.generate_conversation_title()
                        case TriggerToolResponse():
                            ready = await self.continue_after_tool_response(
                                tool_reply_msg_id=input_ev.tool_reply_message_id,
                                assistant_reply_msg_id=input_ev.assistant_reply_msessage_id,
                            )
                            if ready:
                                self.set_ready_for_user_message(True)
                        case ProvideExternalToolOuptut():
                            await self.provide_external_tool_output(
                                input_ev.tool_call_id, input_ev.output
                            )
                        case _:
                            self.report_error(f"[ERROR] Unkown input action {input_ev}")

                    # We ask the backend to fully refresh after processing every event. This
                    # ensures the data does not desync
                    self.output_event_bus.publish(Refresh())
                except:
                    self.report_error(
                        f"[FATAL] Exception in Conversation task while processing {input_ev}"
                    )
                    traceback.print_exc()

        except:
            self.report_error("[FATAL] Exception in Conversation task.")
            traceback.print_exc()

    def report_error(self, msg: str, payload: Any = None):
        self.output_event_bus.publish(ConversationError(message=msg, payload=payload))
        print(msg)

    async def create_user_msg(self, content: str) -> uuid.UUID:
        msg_id = db_queries.create_user_message(database, self.conversation_id, content)
        self.output_event_bus.publish(
            MessageUpdate(
                message_id=msg_id, role=models.MessageRole.User, content=content
            )
        )
        return msg_id

    async def create_empty_assistant_msg(self) -> uuid.UUID:
        msg_id = db_queries.create_empty_assistant_message(
            database, self.conversation_id
        )
        self.output_event_bus.publish(
            MessageUpdate(
                message_id=msg_id, role=models.MessageRole.Assistant, content=""
            )
        )
        return msg_id

    async def create_empty_tool_response_msg(
        self,
        tool_calls_being_replied_to: list[uuid.UUID],
    ) -> uuid.UUID:
        msg_id = db_queries.create_tool_reply_message(
            database,
            self.conversation_id,
            "",
            tool_calls_being_replied_to=tool_calls_being_replied_to,
        )
        self.output_event_bus.publish(
            MessageUpdate(message_id=msg_id, role=models.MessageRole.Tool, content="")
        )
        return msg_id

    async def set_tool_response_msg_content(
        self,
        tool_response_msg_id: uuid.UUID,
        content: str,
    ):
        db_queries.update_message_content(
            database,
            tool_response_msg_id,
            new_raw_content=content,
            new_visible_content=content,
        )
        self.output_event_bus.publish(
            MessageUpdate(
                message_id=tool_response_msg_id,
                role=models.MessageRole.Tool,
                content=content,
            )
        )

    async def send_user_message(self, message: UserMessage) -> ReadyForNextUserMessage:
        # Record the user message and generate the prompt
        _ = await self.create_user_msg(message.content)
        prompt = await db_queries.get_chat_prompt_for_inference(
            database, conversation_id=self.conversation_id
        )

        # Create an empty message to hold the reply
        reply_msg_id = await self.create_empty_assistant_msg()

        # Start generating tokens
        return await self.generate_llm_response(prompt, reply_msg_id)

    async def generate_llm_response(
        self, prompt: list[inference.ChatMessage], reply_msg_id: uuid.UUID
    ) -> ReadyForNextUserMessage:
        response = self.llm.chat_stream(self.llm_model, messages=prompt)

        content = ""
        async for part in response:
            content += part
            # print("LLM:", part)
            self.output_event_bus.publish(
                MessageUpdate(
                    message_id=reply_msg_id,
                    role=models.MessageRole.Assistant,
                    content=content,
                )
            )

        tool_ids = db_queries.record_reply_message_and_parse_tool_calls(
            database, msg_id=reply_msg_id, content=content
        )

        if len(tool_ids) > 0:
            asyncio.create_task(self.spawn_tools_and_wait_for_completion(tool_ids))
            return ReadyForNextUserMessage.No
        else:
            return ReadyForNextUserMessage.Yes

    async def spawn_tools_and_wait_for_completion(self, tool_call_ids: list[uuid.UUID]):
        # Create the response messages: One for the tool, and one for the assistant's
        # reply. They're both empty at this point.
        # This will hold the reply for the assistant message
        tool_reply_msg_id = await self.create_empty_tool_response_msg(
            tool_calls_being_replied_to=tool_call_ids
        )
        assistant_reply_msg_id = db_queries.create_empty_assistant_message(
            database, self.conversation_id
        )

        tool_call_tasks = [
            # NOTE: The assistant_reply_msg_id is passed to the tool call task so that
            # some tools can stream back the resposne directly into the assistant's
            # resposne message without us having to wait for completion.
            ToolCallTask(
                self, tool_call_id=tid, assistant_reply_msg_id=assistant_reply_msg_id
            )
            for tid in tool_call_ids
        ]

        print(f"SPAWNING TOOLS {tool_call_ids}")

        # Store in state so we can communicate consent status later
        for tct in tool_call_tasks:
            asyncio.create_task(tct.task_loop())
            print(f"TOOLS {tool_call_ids} is pending")
            self.pending_tool_calls[tct.tool_call_id] = tct

        # Signal that user input is required if any of the tools needs confirmation
        any_tool_needs_confirm = any(
            t
            for t in [db_queries.get_tool_call(database, tid) for tid in tool_call_ids]
            if t.status == models.ToolCallStatus.PendingConfirm
        )
        if any_tool_needs_confirm:
            self.output_event_bus.publish(
                NeedsUserInput(kind=NeededInputKind.PendingToolConfirm)
            )

        # Wait for all tasks to have a result
        await asyncio.gather(*[tct.result for tct in tool_call_tasks])

        # All tools have finished processing. Now we generate a reply message to tell the
        # LLM about any tool outputs
        tool_calls = [db_queries.get_tool_call(database, tid) for tid in tool_call_ids]
        tool_response_content = tool_prompting.tool_call_result_prompt(tool_calls)
        await self.set_tool_response_msg_content(
            tool_reply_msg_id,
            tool_response_content,
        )

        # And finally, we trigger an event so the main loop can initiate the reply.
        self.send_input_event(
            TriggerToolResponse(
                tool_reply_message_id=tool_reply_msg_id,
                assistant_reply_msessage_id=assistant_reply_msg_id,
            )
        )

    async def continue_after_tool_response(
        self,
        tool_reply_msg_id: uuid.UUID,
        assistant_reply_msg_id: uuid.UUID,
    ) -> ReadyForNextUserMessage:
        tools = db_queries.get_tool_reply_message_tool_calls(
            database, tool_reply_msg_id
        )

        # If no tools require reply by the LLM, we work in "verbatim mode", where we
        # generate the assistant response right away without an LLM call.
        verbatim_mode = True
        some_verbatim = False
        for tool in tools:
            if tool.tool_answer and tool.tool_answer.get(
                "should_display_verbatim", False
            ):
                some_verbatim = True
            else:
                verbatim_mode = False

        # @JosepC 2026-02-19 If some tool responses are verbatim, but not all of them,
        # we're in a tricky situation: We want to show the verbatim content to the user
        # right away, but there is some content to be interpreted by the LLM as well.
        #
        # The ideal solution here is to generate part of the assistant's response, and let
        # the LLM complete from there. Doing two consecutive assistant response messages
        # is not well supported by inference APIs, and also contradicts the model's
        # training data, so ideally what we should do is have a way to tell the inference
        # API to continue the existing assistant message we started. This is theoretically
        # possible but adding support to our inference wrapper is something that needs to
        # be investigated.
        if some_verbatim and not verbatim_mode:
            print(
                "[WARNING] Tool response has mixed verbatim / non-verbatim content. The verbatim content will not be displayed as-is but sent to the LLM instead.",
                flush=True,
            )

        if not verbatim_mode:
            prompt = await db_queries.get_chat_prompt_for_inference(
                database, conversation_id=self.conversation_id
            )
            return await self.generate_llm_response(prompt, assistant_reply_msg_id)
        else:
            # Generate the assistant response right away.
            msg_content = "\n".join(
                tool.tool_answer.get("response", "")
                for tool in tools
                if tool.tool_answer is not None
            )
            self.output_event_bus.publish(
                MessageUpdate(
                    message_id=assistant_reply_msg_id,
                    role=models.MessageRole.Assistant,
                    content=msg_content,
                )
            )
            tool_ids = db_queries.record_reply_message_and_parse_tool_calls(
                database,
                msg_id=assistant_reply_msg_id,
                content=msg_content,
                # For security reasons. We do not want verbatim tools to be triggering
                # other tools. This should never happen.
                ignore_tool_calls=True,
            )
            assert len(tool_ids) == 0
            return ReadyForNextUserMessage.Yes

    async def set_tool_consent(self, tool_call_id: uuid.UUID, user_consents: bool):
        if tool_call_id in self.pending_tool_calls:
            self.pending_tool_calls[tool_call_id].user_consent.set_result(user_consents)
        else:
            self.report_error(
                f"Got user consent for tool that isn't pending. It will be ignored. Pending tool ids: {list(self.pending_tool_calls.keys())}",
                self.pending_tool_calls.keys(),
            )

    async def provide_external_tool_output(
        self, tool_call_id: uuid.UUID, output: ExternalToolOutput
    ):
        if tool_call_id in self.pending_tool_calls:
            tool_call = db_queries.get_tool_call(database, tool_call_id)
            if tool_call.status != models.ToolCallStatus.PendingExternalResult:
                self.report_error(
                    f"Got result for externalt tool for a tool that is not external, or wasn't expecting a result: {tool_call.toolset_key}, {tool_call.tool_key}"
                )
            self.pending_tool_calls[tool_call_id].external_tool_result.set_result(
                output
            )
        else:
            self.report_error(
                f"Got external tool result consent for tool that isn't pending. It will be ignored. Pending tool ids: {list(self.pending_tool_calls.keys())}",
                self.pending_tool_calls.keys(),
            )

    async def generate_conversation_title(self):
        messages = db_queries.get_conversation_messages(database, self.conversation_id)
        task = GenerateTitleTask(self, list(messages))
        asyncio.create_task(task.task_koop())
