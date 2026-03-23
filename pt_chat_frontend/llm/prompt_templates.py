from dataclasses import dataclass
from jinja2 import Template
from pathlib import Path
from typing import Literal, TypedDict

from pt_chat_frontend.llm.inference import ChatMessage


@dataclass
class FewShotTemplate:
    user_query: Template
    llm_response: Template


@dataclass
class PromptTemplate:
    system_prompt: Template
    few_shot_examples: list[FewShotTemplate]
    user_prompt: Template | None

    @staticmethod
    def from_path(path_prefix: str) -> "PromptTemplate":
        # Locate files in the parent path:
        # - System prompt: with .system.j2 extension
        # - User prompt: with .user.j2 extension
        # - Fewshot example prompts: pairs with with .fewshot.0001.llm.j2,
        #   .fewshot.0001.user.j2 (where 0001 can be an arbitrary number)
        p = Path(path_prefix).parent
        pfx = Path(path_prefix).name
        system_prompt_path = p / f"{pfx}.system.j2"
        user_prompt_path = p / f"{pfx}.user.j2"

        # Sorting makes sure the fewshot examples are properly ordered. We will
        # do some sanity checks to ensure each llm file has a matching user file
        fewshot_prompt_paths = sorted(list(p.glob(f"{pfx}.fewshot.*.*.j2")))

        if len(fewshot_prompt_paths) % 2 != 0:
            raise ValueError(
                "Error loading prompt: Each fewshot example must have a user and llm prompt"
            )

        def fewshot_path_number(p: Path):
            return int(p.name.split(".")[-3])

        template = PromptTemplate(
            system_prompt=Template(system_prompt_path.read_text()),
            user_prompt=(
                Template(user_prompt_path.read_text())
                if user_prompt_path.exists()
                else None
            ),
            few_shot_examples=[],
        )

        # Load the templates from the files
        next_fewshot_number = 1
        for i in range(0, len(fewshot_prompt_paths), 2):
            llm_path = fewshot_prompt_paths[i]
            user_path = fewshot_prompt_paths[i + 1]

            if fewshot_path_number(llm_path) != fewshot_path_number(user_path):
                raise ValueError(
                    "Error loading prompt: Each fewshot example must have a user and llm prompt"
                )

            if fewshot_path_number(llm_path) != next_fewshot_number:
                raise ValueError(
                    "Error loading prompt: Fewshot examples must be numbered sequentially"
                )
            next_fewshot_number += 1

            template.few_shot_examples.append(
                FewShotTemplate(
                    user_query=Template(user_path.read_text()),
                    llm_response=Template(llm_path.read_text()),
                )
            )

        return template

    def render(self, params: dict) -> list[ChatMessage]:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self.system_prompt.render(params))
        ]

        for fewshot in self.few_shot_examples:
            messages.append(
                ChatMessage(role="user", content=fewshot.user_query.render(params))
            )
            messages.append(
                ChatMessage(role="user", content=fewshot.llm_response.render(params))
            )

        if self.user_prompt is not None:
            messages.append(
                ChatMessage(role="user", content=self.user_prompt.render(params))
            )

        return messages
