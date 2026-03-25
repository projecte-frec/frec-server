from typing import Any
from uuid import UUID
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from frec_server.executor import conversation_task as ct, conversation_task_manager
from frec_server.pages.common import get_request_user_id, set_request_user
from frec_server.persistence.db import get_global_db
from frec_server.persistence import db_queries, models

db = get_global_db()
ctaskmgr = conversation_task_manager.get_global_task_manager()


def register_routes(fastapi_app: FastAPI):
    api = FastAPI()

    @api.middleware("http")
    async def validate_token(request: Request, call_next):
        if "Authorization" not in request.headers:
            return Response(
                content="'Authorization' not found in request headers. You must set that header to the string 'Bearer <your-token>'",
                status_code=400,
            )
        auth = request.headers["Authorization"]
        if not auth.startswith("Bearer "):
            return Response(
                content="'Authorization' header must be of the form 'Bearer <your-token>'",
                status_code=400,
            )
        token = auth[len("Bearer ") :]
        user_id = db_queries.get_user_id_of_token(db, token_str=token)
        if user_id is None:
            return Response(content="Provided token is not valid.", status_code=401)
        else:
            set_request_user(request, db_queries.get_user(db, user_id))
            return await call_next(request)

    @api.get("/version")
    def get_version():
        return "0.1.0"

    @api.post("/start-chat")
    def start_chat(request: Request):
        conversation = db_queries.start_conversation(
            db,
            user_id=get_request_user_id(request),
            name=None,
            visible_on_web=False,
        )
        return {"conversation_id": conversation.id}

    async def subscribe_and_return_new_messages(
        ctask: ct.ConversationTask,
    ) -> dict[str, Any] | Response:
        print("Subscribe and return new messages...", flush=True)
        with ctask.subscribe_to_output_event() as sub:
            new_messages = []
            while True:
                new_event = await sub.get()
                if new_event is None:
                    continue

                print(f"Got event: {new_event}", flush=True)

                if type(new_event) == ct.MessageUpdate:
                    if new_event.role in [
                        models.MessageRole.User,
                        models.MessageRole.Assistant,
                    ]:
                        if new_event.message_id not in new_messages:
                            new_messages.append(new_event.message_id)
                elif type(new_event) == ct.ConversationError:
                    return Response(
                        status_code=400,
                        content=f"Error processing message: {new_event.message}",
                    )
                elif type(new_event) == ct.NeedsUserInput:
                    conv_messages = db_queries.get_conversation_messages(
                        db, conversation_id=ctask.conversation_id
                    )

                    # Done, assemble resopnse and send back to user:
                    messages_to_send = [
                        msg
                        for msg in conv_messages
                        if msg.id in new_messages
                        and msg.role
                        in [models.MessageRole.User, models.MessageRole.Assistant]
                    ]
                    response = {
                        "stop_reason": new_event.kind,
                        "new_messages": [],
                    }

                    def tool_call_to_json(tool_call: models.ToolCall) -> dict:
                        return {
                            "id": tool_call.id,
                            "status": tool_call.status,
                            "toolset_name": tool_call.toolset_key,
                            "tool_name": tool_call.tool_key,
                            "tool_args": tool_call.tool_args,
                            "tool_answer": tool_call.tool_answer,
                        }

                    for msg in messages_to_send:
                        msg_json = {
                            "id": msg.id,
                            "role": msg.role,
                            "content": msg.visible_content,
                            "tool_calls": [],
                        }
                        for tool_call in db_queries.get_message_tool_calls(db, msg.id):
                            msg_json["tool_calls"].append(tool_call_to_json(tool_call))
                        response["new_messages"].append(msg_json)

                    pending_consent = []
                    pending_external = []
                    if len(conv_messages) >= 1:
                        for tool_call in db_queries.get_message_tool_calls(
                            db, conv_messages[-1].id
                        ):
                            if tool_call.status == models.ToolCallStatus.PendingConfirm:
                                pending_consent.append(tool_call_to_json(tool_call))
                            elif (
                                tool_call.status
                                == models.ToolCallStatus.PendingExternalResult
                            ):
                                pending_external.append(tool_call_to_json(tool_call))

                    response["tools_pending_consent"] = pending_consent
                    response["tools_pending_external"] = pending_external

                    return response

    class SendMessage(BaseModel):
        conversation_id: UUID
        content: str

    @api.post("/send-message")
    async def send_message(body: SendMessage):
        print("Sending message to conversation", flush=True)
        ctask = ctaskmgr.get_conversation(body.conversation_id)
        if not ctask.ready_for_user_message:
            return Response(
                content="This conversation is currently processing another message.",
                status_code=409,
            )

        ctask.send_input_event(ct.UserMessage(content=body.content))
        return await subscribe_and_return_new_messages(ctask)

    class ToolConsent(BaseModel):
        conversation_id: UUID
        tool_consents: dict[UUID, bool]

    @api.post("/tool-consent")
    async def tool_consent(body: ToolConsent):
        invalid_ids = []
        for tool_call_id in body.tool_consents.keys():
            try:
                tool_call = db_queries.get_tool_call(db, tool_call_id)
                if tool_call.status != models.ToolCallStatus.PendingConfirm:
                    invalid_ids.append(tool_call_id)
            except:
                invalid_ids.append(tool_call_id)

        if len(invalid_ids) > 0:
            return Response(
                content=f"The following ids do not correspond to pending tool calls: {invalid_ids}",
                status_code=400,
            )

        print("Sending tool consent to conversation", flush=True)
        ctask = ctaskmgr.get_conversation(body.conversation_id)
        for tool_call_id, user_consents in body.tool_consents.items():
            ctask.send_input_event(
                ct.ConsentAction(tool_call_id=tool_call_id, user_consents=user_consents)
            )
        return await subscribe_and_return_new_messages(ctask)

    class ExternalToolOutputs(BaseModel):
        conversation_id: UUID
        tool_outputs: dict[UUID, ct.ExternalToolOutput]

    @api.post("/external-tool-output")
    async def external_tool_output(body: ExternalToolOutputs):
        invalid_ids = []
        for tool_call_id in body.tool_outputs.keys():
            try:
                tool_call = db_queries.get_tool_call(db, tool_call_id)
                if tool_call.status != models.ToolCallStatus.PendingExternalResult:
                    invalid_ids.append(tool_call_id)
            except:
                invalid_ids.append(tool_call_id)

        if len(invalid_ids) > 0:
            return Response(
                content=f"The following ids do not correspond to pending external results: {invalid_ids}",
                status_code=400,
            )

        print("Sending external tool outputs to conversation", flush=True)
        ctask = ctaskmgr.get_conversation(body.conversation_id)
        for tool_call_id, tool_output in body.tool_outputs.items():
            ctask.send_input_event(
                ct.ProvideExternalToolOuptut(
                    tool_call_id=tool_call_id, output=tool_output
                )
            )
        return await subscribe_and_return_new_messages(ctask)

    fastapi_app.mount("/api", api)
