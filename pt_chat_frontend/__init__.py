# Attempt to load a .env file, first of all. This ensures environment variables are set.
from dotenv import load_dotenv

load_dotenv()

import pt_chat_frontend.configuration as configuration
import pt_chat_frontend.persistence.db as database

# Import SQLModel models to trigger their registration
from pt_chat_frontend.persistence import db_queries, models as _

# Initialize the singletons early on so page modules can grab it when loaded.
config_file = configuration.get_config_file()
database.init_db()

from pt_chat_frontend.executor import conversation_task_manager

conversation_task_manager.init_conversation_task_manager()


from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/js", StaticFiles(directory="assets"), name="assets")

from pt_chat_frontend import pages

pages.register_routes(app)

from pt_chat_frontend import rest_api

rest_api.register_routes(app)
