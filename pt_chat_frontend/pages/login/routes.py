from typing import Annotated
from uuid import UUID
from datastar_py.consts import ElementPatchMode
from datastar_py.fastapi import DatastarResponse
from datastar_py import ServerSentEventGenerator as SSE
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from pt_chat_frontend.pages.common import (
    get_request_user_id,
    get_request_user_session,
    set_request_user,
    set_request_user_session,
)
from pt_chat_frontend.persistence import db_queries
from pt_chat_frontend.persistence.db import get_global_db

from pt_chat_frontend.pages.login import views

db = get_global_db()

AUTH_COOKIE = "frec_auth_session"


def get_user_id(request: Request) -> UUID:
    return request.state.user_id


def register_routes(app: FastAPI):
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if (
            request.url.path.startswith("/api")
            or request.url.path.startswith("/assets")
            or request.url.path.startswith("/login")
        ):
            return await call_next(request)
        else:
            if AUTH_COOKIE in request.cookies:
                session_id = UUID(request.cookies["frec_auth_session"])
                if (
                    user := db_queries.validate_user_session(db, session_id)
                ) is not None:
                    set_request_user(request, user)
                    set_request_user_session(request, session_id)
                    return await call_next(request)

            return RedirectResponse("/login")

    @app.get("/login", response_class=HTMLResponse)
    def signin_post():
        return str(views.login_page())

    @app.post("/login/auth", response_class=DatastarResponse)
    def login_auth(username: Annotated[str, Form()], password: Annotated[str, Form()]):
        async def inner():
            user_session = db_queries.sign_in_and_create_user_session(
                db, username, password
            )
            if user_session is not None:
                response = Response(content="Login Successful", status_code=200)
                response.set_cookie(AUTH_COOKIE, str(user_session.id))
                # The setCookie function is defined in `cookieManager.js`
                yield SSE.execute_script(
                    f"setCookie('{AUTH_COOKIE}', '{user_session.id}', 30);"
                )
                yield SSE.execute_script(f"window.location.replace('/');")
            else:
                yield SSE.patch_elements(
                    selector=f"#{views.Ids.ErrorText}",
                    elements="Invalid username and password combination",
                    mode=ElementPatchMode.INNER,
                )

        return DatastarResponse(inner())

    @app.post("/log-out", response_class=DatastarResponse)
    def log_out(request: Request):
        async def inner():
            user_session_id = get_request_user_session(request)
            db_queries.logout(db, user_session_id)
            yield SSE.execute_script(f"window.location.replace('/login');")

        return DatastarResponse(inner())
