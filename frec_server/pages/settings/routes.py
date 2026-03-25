import asyncio
from typing import Annotated
from uuid import UUID

from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.consts import ElementPatchMode
from datastar_py.fastapi import DatastarResponse, ReadSignals

from fastapi import FastAPI, Form, Request
import fastapi
from fastapi.responses import HTMLResponse
import htpy
from pydantic import BaseModel

from frec_server import configuration
from frec_server.pages.common import get_request_user, get_request_user_id
from frec_server.pages.settings import views
from frec_server.persistence import db_queries, db as database, models
from frec_server.tool_calling import agent_client, mcp_manager, rag_client


db = database.get_global_db()


def register_routes(app: FastAPI):
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        user = get_request_user(request)

        all_users = None
        if user.is_admin:
            all_users = list(db_queries.get_all_users(db))
        toolsets_and_cfg = db_queries.get_all_toolsets_and_config(db, user.id)
        tokens = db_queries.get_all_tokens_for_user(db, user.id)

        return str(
            views.settings_page(
                current_user_id=user.id,
                username=user.username,
                users=all_users,
                toolsets_and_cfg=list(toolsets_and_cfg),
                tokens=list(tokens),
            )
        )

    @app.get("/settings/tool-conn/{toolset_key}", response_class=HTMLResponse)
    async def tool_settings_page(request: Request, toolset_key: str):
        user = get_request_user(request)
        permissions = []

        cfg_file = configuration.get_config_file()
        toolset = cfg_file.toolsets[toolset_key]
        permissions = await db_queries.get_toolset_permissions(
            db, user_id=user.id, toolset_key=toolset_key
        )
        return str(
            views.tool_settings_page(
                username=user.username,
                toolset=toolset,
                permissions=permissions,
            )
        )

    @app.post("/fetch_toolset_status/{toolset_key}")
    def fetch_toolset_status_details(signals: ReadSignals, toolset_key: str):
        async def inner():
            toolset = configuration.get_config_file().toolsets[toolset_key]

            frontend_status = views.ToolsetStatus.Pending
            heading = ""
            body = ""

            if toolset.kind == "mcp":
                status = await mcp_manager.check_status(toolset_key, toolset.endpoint)

                if type(status) is mcp_manager.ChatToolSet:
                    frontend_status = views.ToolsetStatus.Online
                    heading = f"{toolset.name} - Online"
                    body = str(
                        htpy.div[
                            htpy.h2(".font-semibold.text-md")["Available functions"],
                            htpy.ul[[htpy.li[fn] for fn in status.available_functions]],
                        ]
                    )
                elif type(status) is mcp_manager.McpConnectionError:
                    frontend_status = views.ToolsetStatus.Offline
                    heading = f"{toolset.name} - Offline"
                    body = str(
                        htpy.div[
                            htpy.h2(".font-semibold.text-md")["MCP Connection error"],
                            [htpy.p[line] for line in status.error.splitlines()],
                        ]
                    )
            elif toolset.kind == "external":
                frontend_status = views.ToolsetStatus.Online
                heading = f"{toolset.name} - External Tool"
                body = str(
                    htpy.div[
                        htpy.h2(".font-semibold.text-md")["Available functions"],
                        htpy.ul[[htpy.li[fn] for fn in toolset.tools.keys()]],
                    ]
                )
            elif toolset.kind == "rag":
                status, text = await rag_client.get_status(toolset.url, toolset.token)
                if status == rag_client.RagServerStatus.Online:
                    frontend_status = views.ToolsetStatus.Online
                    heading = f"{toolset.name} - Online"
                else:
                    frontend_status = views.ToolsetStatus.Offline
                    heading = f"{toolset.name} - Unavailable"
                body = text
            elif toolset.kind == "agent":
                try:
                    description = await agent_client.get_agent_description(
                        toolset.url, toolset.agent_key
                    )
                    frontend_status = views.ToolsetStatus.Online
                    heading = f"{toolset.name} - Online"
                    body = str(
                        htpy.div[
                            htpy.h2(".font-semibold.text-md")["Agent"],
                            htpy.p[f"Agent key: {toolset.agent_key}"],
                            htpy.h2(".font-semibold.text-md.mt-4")["Description"],
                            htpy.p[description],
                        ]
                    )
                except Exception as e:
                    frontend_status = views.ToolsetStatus.Offline
                    heading = f"{toolset.name} - Unavailable"
                    body = str(
                        htpy.div[
                            htpy.h2(".font-semibold.text-md")["Agent connection error"],
                            [htpy.p[line] for line in str(e).splitlines()],
                        ]
                    )
            else:
                print(f"[WARNING]: Unhandled toolset kind {toolset.kind}")
                frontend_status = views.ToolsetStatus.Offline
                heading = f"{toolset.name} - Unavailable"
                body = f"Unhandled toolset kind {toolset.kind}"

            yield SSE.patch_signals(
                {views.Signals.ToolsetStatus: {toolset_key: frontend_status}}
            )
            yield SSE.patch_elements(
                selector=f"#{views.Ids.ToolsetModalContents}",
                elements=body,
                mode=ElementPatchMode.INNER,
            )
            yield SSE.patch_elements(
                selector=f"#{views.Ids.ToolsetModalHeading}",
                elements=heading,
                mode=ElementPatchMode.INNER,
            )

        return DatastarResponse(inner())

    @app.post("/toggle_toolset_enabled/{toolset_key}")
    def toggle_toolset_enabled(
        request: Request, signals: ReadSignals, toolset_key: str
    ):
        user = get_request_user(request)

        async def inner():
            new_status = db_queries.update_toolset_connection_enabled(
                db,
                user_id=user.id,
                toolset_key=toolset_key,
                update_enabled=lambda e: not e,
            )
            yield SSE.patch_signals(
                {views.Signals.ToolsetEnabled: {str(toolset_key): new_status}}
            )

        return DatastarResponse(inner())

    @app.get("/settings/user/{user_id}", response_class=HTMLResponse)
    async def user_settings_page(request: Request, user_id: str):
        this_user = get_request_user(request)
        user_to_edit = None
        if user_id != "new":
            user_to_edit = db_queries.get_user(db, UUID(user_id))
        return str(
            views.user_settings_page(
                username=this_user.username,
                user=user_to_edit,
            )
        )

    @app.post("/create_user")
    async def create_user(request: Request, signals: ReadSignals):
        assert signals

        async def inner():
            try:
                if "username" not in signals:
                    raise Exception("Missing username")
                elif "password" not in signals:
                    raise Exception("Missing password")
                if len(signals.get("password", "")) == 0:
                    raise Exception("Password cannot be empty")

                username = signals["username"]
                password = signals["password"]
                is_admin = signals["is_admin"]

                yield SSE.patch_signals({views.Signals.UserCrudPageMsg: ""})
                db_queries.create_user(
                    db, username=username, password=password, is_admin=is_admin
                )
                yield SSE.patch_signals(
                    {views.Signals.UserCrudPageMsg: "Created successfully"}
                )
                await asyncio.sleep(0.5)
                yield SSE.execute_script("window.location.href = '/settings'")
            except Exception as e:
                yield SSE.patch_signals(
                    {views.Signals.UserCrudPageError: f"Error: {e}"}
                )

        return DatastarResponse(inner())

    @app.post("/update_user/{user_id}")
    async def update_user(user_id: UUID, signals: ReadSignals):
        assert signals

        async def inner():
            try:
                yield SSE.patch_signals({views.Signals.UserCrudPageError: f""})
                yield SSE.patch_signals({views.Signals.UserCrudPageMsg: ""})

                db_queries.update_user(
                    db,
                    user_id,
                    signals["username"],
                    signals["password"] if len(signals["password"]) > 0 else None,
                    signals["is_admin"],
                )
                yield SSE.patch_signals(
                    {views.Signals.UserCrudPageMsg: "Updated successfully"}
                )
                await asyncio.sleep(4)
                yield SSE.patch_signals({views.Signals.UserCrudPageMsg: ""})
            except BaseException as e:
                yield SSE.patch_signals(
                    {views.Signals.UserCrudPageError: f"Error: {e}"}
                )

        return DatastarResponse(inner())

    @app.post("/delete_user/{user_id}")
    async def delete_user(request: Request, user_id: UUID):
        async def inner():
            db_queries.delete_user(db, user_id)
            yield SSE.execute_script("window.location.reload()")

        return DatastarResponse(inner())

    @app.post("/set_tool_permission/{permission_id}/{kind}")
    async def set_tool_permission(permission_id: UUID, kind: models.ToolPermissionKind):
        async def inner():
            db_queries.set_tool_permission(db, permission_id, kind)
            yield SSE.patch_elements(
                selector=f"#{views.Ids.tool_permission_id(permission_id)}",
                elements=str(
                    views.permission_tri_state_switch(
                        db_queries.get_tool_permission(db, permission_id)
                    )
                ),
                mode=ElementPatchMode.OUTER,
            )

        return DatastarResponse(inner())

    @app.post("/create_new_user_token")
    async def create_new_user_token(request: Request):
        async def inner():
            user_id = get_request_user_id(request)
            token_str = db_queries.create_user_token(db, user_id)
            all_tokens = db_queries.get_all_tokens_for_user(db, user_id)
            yield SSE.patch_elements(
                selector=f"#{views.Ids.TokenModalContents}",
                elements=token_str,
                mode=ElementPatchMode.INNER,
            )
            yield SSE.patch_elements(
                selector=f"#{views.Ids.TokenSectionTable}",
                elements=str(views.token_section_table(list(all_tokens))),
                mode=ElementPatchMode.OUTER,
            )
            yield SSE.execute_script(f"{views.Ids.TokenCreateModal}.showModal();")

        return DatastarResponse(inner())

    @app.post("/delete_user_token/{token_sha512}")
    async def delete_user_token(request: Request, token_sha512: str):
        async def inner():
            user_id = get_request_user_id(request)
            db_queries.delete_user_token(db, token_sha512)
            yield SSE.execute_script(f"{views.Ids.TokenDeleteModal}.close();")
            all_tokens = db_queries.get_all_tokens_for_user(db, user_id)
            yield SSE.patch_elements(
                selector=f"#{views.Ids.TokenSectionTable}",
                elements=str(views.token_section_table(list(all_tokens))),
                mode=ElementPatchMode.OUTER,
            )

        return DatastarResponse(inner())
