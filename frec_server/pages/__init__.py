from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .login import routes as login_routes
from .chat import routes as chat_routes
from .settings import routes as settings_routes


def register_routes(app: FastAPI):
    @app.get("/")
    def root():
        return RedirectResponse("/chat/new")

    login_routes.register_routes(app)
    chat_routes.register_routes(app)
    settings_routes.register_routes(app)
