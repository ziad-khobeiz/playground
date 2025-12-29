import os
import instructor
from pydantic import BaseModel
from typing import Type
from openai import OpenAI

BASE_CLIENT = OpenAI(
    api_key=os.getenv("FIREWORKS_API_KEY"),
    base_url="https://api.fireworks.ai/inference/v1",
)

JSON_CLIENT = instructor.from_openai(
    BASE_CLIENT,
    mode=instructor.Mode.JSON,
)

DEFAULT_MODEL = "accounts/fireworks/models/deepseek-v3p2"


def get_response(prompt: str, reponse_model: Type[BaseModel], temperature: int = 0, max_tokens: int = 4096, model: str = DEFAULT_MODEL):
    return JSON_CLIENT.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_model=reponse_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
