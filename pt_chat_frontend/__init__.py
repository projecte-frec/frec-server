# Attempt to load a .env file, first of all. This ensures environment variables are set.
from dotenv import load_dotenv

load_dotenv()

import frec_server.configuration as configuration
import frec_server.persistence.db as database

# Import SQLModel models to trigger their registration
from frec_server.persistence import db_queries, models as _

# Initialize the singletons early on so page modules can grab it when loaded.
config_file = configuration.get_config_file()
database.init_db()

from frec_server.executor import conversation_task_manager

conversation_task_manager.init_conversation_task_manager()


from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/js", StaticFiles(directory="assets"), name="assets")

from frec_server import pages

pages.register_routes(app)

from frec_server import rest_api

rest_api.register_routes(app)
