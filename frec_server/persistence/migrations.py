from datetime import datetime, timezone
from typing import Callable
from uuid import UUID
import sqlalchemy
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel
import sqlmodel

from frec_server.persistence import models


def drop_table(conn: sqlalchemy.Connection, table: str):
    return conn.execute(
        sqlalchemy.text(
            f"""DROP TABLE '{table}';
            """
        )
    )


def alter_table(conn: sqlalchemy.Connection, table: str, sql_alteration: str):
    return conn.execute(
        sqlalchemy.text(
            f"""ALTER TABLE '{table}'
                {sql_alteration};
            """
        )
    )


def add_column(engine: Engine, table: str, new_column: str, column_type: str):
    inspector = sqlalchemy.inspect(engine)
    with engine.connect() as conn:
        if not inspector.has_table(table):
            return
        columns = [col["name"] for col in inspector.get_columns(table)]
        if new_column not in columns:

            return alter_table(
                conn, table, f""" ADD COLUMN {new_column} {column_type}"""
            )


def drop_column(engine: Engine, table: str, column: str):
    inspector = sqlalchemy.inspect(engine)

    with engine.connect() as conn:
        if not inspector.has_table(table):
            return

        columns = [col["name"] for col in inspector.get_columns(table)]
        if column not in columns:
            return  # nothing to do

        return alter_table(conn, table, f""" DROP COLUMN {column}""")


def add_conversation_is_visible_on_web_2026_01_13(engine: Engine):
    add_column(engine, "conversation", "visible_on_web", "BOOLEAN DEFAULT TRUE")

# def add_conversation_file_missing_columns_2026_02_18(engine: Engine):
#     add_column(engine, "conversationfile", "data", "BLOB")
#     add_column(engine, "conversationfile", "filename", "VARCHAR")
#     add_column(engine, "conversationfile", "mime_type", "TEXT DEFAULT 'application/octet-stream'")
#     drop_column(engine, "conversationfile", "user_id")

# def drop_conversation_file_to_rebuild_it_2026_02_18(engine: Engine):
#     with engine.connect() as conn:
#         drop_table(conn, "conversationfile")

def add_toolcall_reply_message_id_2026_02_19(engine: Engine):
    # NOTE: Unfortunately, sqlite cannot alter a column to add a foreign key constraint so
    # we can only create the colum: https://stackoverflow.com/a/75020961
    add_column(engine, "toolcall", "reply_message_id", "CHAR(32)")


MIGRATIONS: list[Callable[[Engine], None]] = [
    add_conversation_is_visible_on_web_2026_01_13,
    add_toolcall_reply_message_id_2026_02_19,
]


def run_migrations(engine: Engine):
    def _ensure_migrations_table(engine: Engine):
        with engine.connect() as conn:
            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS migrations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )

    def _has_migration_been_applied(engine: Engine, name: str) -> bool:
        with engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text("SELECT 1 FROM migrations WHERE name = :name"),
                {"name": name},
            ).fetchone()
            return result is not None

    def _record_migration(engine: Engine, name: str):
        with engine.connect() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO migrations (name, applied_at) VALUES (:name, :applied_at)"
                ),
                {"name": name, "applied_at": datetime.now(timezone.utc)},
            )
            conn.commit()

    _ensure_migrations_table(engine)
    for m in MIGRATIONS:
        if not _has_migration_been_applied(engine, m.__name__):
            print(f"Running migration {m.__name__}")
            m(engine)
            _record_migration(engine, m.__name__)
