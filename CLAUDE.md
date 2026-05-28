# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal "playground" project. The only active pipeline is an **Airbnb apartment hunter**: it drives a real Chromium browser to search airbnb.ae, uses LLMs to filter and verify listings (location text + interior-photo aesthetics), and pushes matches to Telegram.

## Commands

Uses [`uv`](https://docs.astral.sh/uv/) (see `uv.lock`), Python 3.12.

```bash
uv sync                          # install dependencies into .venv
uv run playwright install chromium   # one-time: install the browser Playwright drives

# Run the full pipeline (search -> filter -> verify -> Telegram notify)
uv run python -m src.scripts.airbnb

# Manual verification test (drives a real search, then asserts verify_listing
# matches "Dubai" and rejects "Paris")
uv run python -m src.scripts.test_verify
```

There is no formal test runner, linter, or build step — `test_verify.py` is a hand-run script, not a pytest suite.

## Running model & import conventions

- There are **no `__init__.py` files**; the code relies on namespace packages and absolute imports rooted at `src` (e.g. `from src.core.airbnb import ...`). Always run modules **from the project root with `-m`** (`python -m src.scripts.airbnb`), never `python src/scripts/airbnb.py` — the latter breaks the imports.
- Playwright uses a persistent profile at `./playwright_user_data` (relative to CWD, gitignored). Running from the project root keeps session/cookies consistent across runs. This is why the browser stays "logged in" between runs.

## Required environment

Only `src/scripts/airbnb.py` calls `load_dotenv()`. Env vars are read in two places:

- **LLM clients** (`src/core/llm.py`) read `FIREWORKS_API_KEY` and `OPENROUTER_API_KEY` directly from the OS environment. These are **not** in `.env` — they must already be exported in your shell, or LLM calls fail.
- **Telegram** (`src/core/telegram.py`) reads `APARTMENTS_BOT_TOKEN` and `MY_TELEGRAM_UID` (these *are* in `.env`).

Gotcha: `test_verify.py` does **not** call `load_dotenv()`, so it relies entirely on shell-exported vars for its LLM calls.

## Architecture

Two layers under `src/`:

- `src/core/` — reusable building blocks (no entry points).
- `src/scripts/` — runnable entry points (`if __name__ == "__main__"`) that wire the core pieces into a pipeline.

### The pipeline (`src/scripts/airbnb.py`)
A 4-stage funnel, each stage narrowing the list of `Listing` objects:
1. `search_listings(...)` — scrape candidate listings from airbnb.ae.
2. `filter_listings(...)` — cheap LLM pass dropping studios / shared rooms (keeps when unsure).
3. `verify_listings(...)` — expensive per-listing verification (re-scrapes each listing page).
4. `send_message(...)` — push survivors to Telegram. Tunable constants live at the top of the script (`MOVE_IN_DATE`, `LOCATION`, `MAX_PRICE`, `MAX_PAGES`, etc.). Dates use **`DD-MM-YYYY`** format.

### Scraping (`src/core/airbnb.py`)
The bulk of the complexity. Key things to know before editing:
- Targets **airbnb.ae** (UAE) specifically — URLs, the "Got it" one-price popup handling, and `AED` pricing are all hardcoded for this locale.
- `launch_persistent_context(headless=False)` — the browser is **visibly non-headless by design**; the search-form automation (typing location, navigating the month-by-month date picker by clicking "next", setting filters) depends on a real rendered page.
- Selectors are brittle Airbnb `data-testid` / `aria-label` strings (e.g. `card-container`, `structured-search-input-field-query`, `price_filter_max`). Expect these to break when Airbnb changes its DOM; extraction is wrapped in per-card try/except so partial failures don't abort the run.
- `search_listings` has a retry loop (default 3 attempts) around the whole browser session.
- `verify_listing` does two LLM checks per listing: (a) a **text** check that the scraped "Where you'll be" location matches the target, then (b) a **vision** check on up to 10 listing photos for a "minimalist/clean/bright" aesthetic. Both must pass.

### LLM access (`src/core/llm.py`)
Single `get_response(prompt, response_model, model=...)` entry point.
- Uses [`instructor`](https://python.useinstructor.com/) in **JSON mode** over the OpenAI SDK to coerce responses into a Pydantic model — every call site passes a `BaseModel` subclass and gets back a validated instance.
- **Provider routing is by model-name substring**: if `"fireworks"` is in the model string it uses the Fireworks client, otherwise the OpenRouter client. So the default text model (`accounts/fireworks/models/glm-4p7`) hits Fireworks, and any `google/...` Gemini model (including the vision model) hits OpenRouter. Changing a model constant can silently change which provider/key is used.
- `prompt` accepts either a plain string or OpenAI-style multimodal `content` parts (text + `image_url`); the vision path in `airbnb.py` builds the list form.
- Note: `openai` is imported here but is only a transitive dependency (via `instructor`), not declared in `pyproject.toml`.
