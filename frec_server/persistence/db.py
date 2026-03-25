import os
from dataclasses import dataclass
from pydantic import BaseModel
import sqlalchemy
from sqlmodel import SQLModel, Session, col, select
import sqlmodel

from frec_server.persistence import migrations
from frec_server.persistence import models as m


FREC_DEPLOY_MODE_ENV = "FREC_DEPLOY_MODE"
FREC_ADMIN_USERNAME_ENV = "FREC_ADMIN_USERNAME"
FREC_ADMIN_PASSWORD_ENV = "FREC_ADMIN_PASSWORD"


def _is_production_deployment() -> bool:
    mode = (os.getenv(FREC_DEPLOY_MODE_ENV) or "development").strip().lower()
    return mode in ["prod", "production"]


def create_admin_user(username: str, password: str) -> m.User:
    return m.User(
        username=username,
        password_hash=m.User.hash_password(password),
        email_address="",
        is_admin=True,
    )


def _bootstrap_admin_user_if_needed(db: "Database"):
    with Session(db.engine) as session:
        user_count = session.scalar(select(sqlalchemy.func.count(col(m.User.id)))) or 0
        if user_count > 0:
            return

        admin_username = (os.getenv(FREC_ADMIN_USERNAME_ENV) or "").strip()
        admin_password = os.getenv(FREC_ADMIN_PASSWORD_ENV) or ""
        has_admin_credentials = len(admin_username) > 0 and len(admin_password) > 0

        if has_admin_credentials:
            session.add(create_admin_user(admin_username, admin_password))
            session.commit()
            print(
                f"Created initial admin user '{admin_username}' from environment",
                flush=True,
            )
            return

        if _is_production_deployment():
            raise Exception(
                "No users exist and admin credentials are not configured. "
                "Set FREC_ADMIN_USERNAME and FREC_ADMIN_PASSWORD for production."
            )

        print(
            "No users exist and no admin credentials were configured. "
            "Continuing in development mode; first login will become admin.",
            flush=True,
        )


@dataclass
class Database:
    engine: sqlalchemy.engine.Engine


global_db: Database | None = None


def get_global_db() -> Database:
    if global_db is not None:
        return global_db
    else:
        raise Exception("Called `get_global_db` but database is not initialized yet.")


def init_db(setup_global: bool = True) -> Database:
    engine = sqlmodel.create_engine("sqlite:///database.db")

    # Run migrations first, so that the schemas SQLModel sees are all correct
    migrations.run_migrations(engine)

    SQLModel.metadata.create_all(engine)

    db = Database(engine=engine)
    _bootstrap_admin_user_if_needed(db)

    if setup_global:
        global global_db
        global_db = db

    return db


# from: https://gist.github.com/imankulov/4051b7805ad737ace7d8de3d3f934d6b
class PydanticType(sqlalchemy.types.TypeDecorator):
    """Pydantic type.
    SAVING:
    - Uses SQLAlchemy JSON type under the hood.
    - Accepts the pydantic model and converts it to a dict on save.
    - SQLAlchemy engine JSON-encodes the dict to a string.
    RETRIEVING:
    - Pulls the string from the database.
    - SQLAlchemy engine JSON-decodes the string to a dict.
    - Uses the dict to create a pydantic model.
    """

    # If you work with PostgreSQL, you can consider using
    # sqlalchemy.dialects.postgresql.JSONB instead of a
    # generic sa.types.JSON
    #
    # Ref: https://www.postgresql.org/docs/13/datatype-json.html
    impl = sqlalchemy.types.JSON

    def __init__(self, pydantic_type: type[BaseModel]):
        super().__init__()
        self.pydantic_type = pydantic_type

    def load_dialect_impl(self, dialect):
        # Use JSONB for PostgreSQL and JSON for other databases.
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(sqlalchemy.JSON())

    def process_bind_param(self, value, dialect):
        return value.dict() if value else None

    def process_result_value(self, value, dialect):
        import pydantic

        return (
            pydantic.TypeAdapter(self.pydantic_type).validate_python(value)
            if value
            else None
        )
