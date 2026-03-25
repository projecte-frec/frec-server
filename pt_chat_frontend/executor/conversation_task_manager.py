import asyncio
import uuid
import os

from frec_server.executor.conversation_task import ConversationTask
from frec_server.llm.inference import LlmInference
from frec_server.persistence import db_queries, models
import frec_server.persistence.db

database = frec_server.persistence.db.get_global_db()


class ConversationTaskmanager:
    def __init__(self, llm: LlmInference, llm_model: str):
        self.llm = llm
        self.llm_model = llm_model

        self.tasks: dict[uuid.UUID, ConversationTask] = {}

    def get_conversation(self, conversation_id: uuid.UUID) -> ConversationTask:
        if conversation_id not in self.tasks:
            conv = db_queries.get_conversation(database, conversation_id)
            self.tasks[conversation_id] = ConversationTask(
                conversation_id=conversation_id,
                llm=self.llm,
                llm_model=self.llm_model,
                auto_generate_name=conv.visible_on_web,
            )

        conv = self.tasks[conversation_id]
        asyncio.create_task(conv.task_loop())

        return conv

    def start_new_conversation(
        self, user_id: uuid.UUID, name: str | None, visible_on_web: bool
    ) -> tuple[ConversationTask, models.Conversation]:
        conv = db_queries.start_conversation(
            database, user_id, name, visible_on_web=visible_on_web
        )
        return self.get_conversation(conv.id), conv


ctaskmgr: ConversationTaskmanager | None = None


def init_conversation_task_manager():
    global ctaskmgr
    from frec_server.llm.inference import (
        OpenAiInference,
        OllamaInference,
        PtInference,
        VllmInference,
    )

    def ensure_env_var(env_var: str) -> str:
        value = os.getenv(env_var)
        if value is None or value == "":
            raise Exception(f"Environment variable {env_var} is not defined.")
        return value

    def optional_env_var(env_var: str) -> str | None:
        value = os.getenv(env_var)
        if value is None or value == "":
            return None
        return value

    def first_defined_env_var(*env_vars: str) -> str:
        for env_var in env_vars:
            value = optional_env_var(env_var)
            if value is not None:
                return value
        raise Exception(
            f"None of the required environment variables are defined: {', '.join(env_vars)}."
        )

    provider = os.getenv("LLM_PROVIDER", "pt").strip().lower()
    llm: LlmInference
    llm_model: str

    if provider == "pt":
        llm = PtInference(
            ensure_env_var("PT_INFERENCE_HOST"),
            ensure_env_var("PT_INFERENCE_TOKEN"),
        )
        llm_model = ensure_env_var("PT_INFERENCE_MODEL")
    elif provider == "ollama":
        llm = OllamaInference(host=optional_env_var("OLLAMA_INFERENCE_HOST"))
        llm_model = first_defined_env_var("OLLAMA_INFERENCE_MODEL", "PT_INFERENCE_MODEL")
    elif provider == "vllm":
        llm = VllmInference(
            endpoint=first_defined_env_var("VLLM_INFERENCE_HOST"),
            token=optional_env_var("VLLM_INFERENCE_TOKEN"),
        )
        llm_model = first_defined_env_var("VLLM_INFERENCE_MODEL", "PT_INFERENCE_MODEL")
    elif provider == "openai":
        llm = OpenAiInference(
            token=ensure_env_var("OPENAI_API_KEY"),
            endpoint=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        llm_model = first_defined_env_var("OPENAI_MODEL", "PT_INFERENCE_MODEL")
    else:
        raise Exception(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported values are: pt, ollama, vllm, openai."
        )

    ctaskmgr = ConversationTaskmanager(
        llm=llm,
        llm_model=llm_model,
    )


def get_global_task_manager() -> ConversationTaskmanager:
    global ctaskmgr
    if ctaskmgr is None:
        raise Exception("Conversation Task Manager has not been initialized yet.")
    return ctaskmgr
