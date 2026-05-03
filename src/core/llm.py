from typing import Type, Union, List, Literal, TypedDict
import os
import instructor
from pydantic import BaseModel
from openai import OpenAI

BASE_FIREWORKS_CLIENT = OpenAI(
    api_key=os.getenv("FIREWORKS_API_KEY"),
    base_url="https://api.fireworks.ai/inference/v1",
)

BASE_OPENROUTER_CLIENT = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

JSON_FIREWORKS_CLIENT = instructor.from_openai(
    BASE_FIREWORKS_CLIENT,
    mode=instructor.Mode.JSON,
)

JSON_OPENROUTER_CLIENT = instructor.from_openai(
    BASE_OPENROUTER_CLIENT,
    mode=instructor.Mode.JSON,
)

DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/glm-4p7"
DEFAULT_OPENROUTER_MODEL = "google/gemini-3.1-pro-preview"

# TypedDicts for strict typing
class TextContent(TypedDict):
    type: Literal["text"]
    text: str

class ImageUrl(TypedDict):
    url: str

class ImageContent(TypedDict):
    type: Literal["image_url"]
    image_url: ImageUrl

PromptType = Union[str, List[Union[TextContent, ImageContent]]]

def get_response(prompt: PromptType, reponse_model: Type[BaseModel], temperature: int = 0, max_tokens: int = 4096, model: str = DEFAULT_FIREWORKS_MODEL):
    # Select client based on model. Defaults to OpenRouter for Gemini.
    client = JSON_OPENROUTER_CLIENT
    if "fireworks" in model:
        client = JSON_FIREWORKS_CLIENT
        
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_model=reponse_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
