"""
Shared OpenAI API helpers for ChatGPT validation and position scripts.
Used by: 06_chatgpt_existing_positions.py, 07_chatgpt_new_positions.py.
"""
import os
import time
from typing import Optional, Tuple

from openai import OpenAI
from logger_config import get_logger
from config import (
    OPENAI_CHATGPT_MODEL,
    OPENAI_CHATGPT_MAX_COMPLETION_TOKENS,
    OPENAI_API_TIMEOUT,
    OPENAI_CHATGPT_RETRY_ATTEMPTS,
    OPENAI_CHATGPT_RETRY_BASE_SECONDS,
)

logger = get_logger(__name__)


def require_openai_api_key(api_key_from_args: Optional[str] = None) -> str:
    """
    Resolve OpenAI API key from argument or environment.
    Raises SystemExit with a clear message if not set.
    """
    key = (api_key_from_args or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "OpenAI API key is required. Set OPENAI_API_KEY in .env or pass --api-key. "
            "Get a key at https://platform.openai.com/api-keys"
        )
    return key


def send_to_chatgpt(
    prompt: str,
    api_key: str,
    *,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    system_content: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Tuple[Optional[str], Optional[dict]]:
    """
    Send a single prompt to OpenAI Chat Completions API with retries.
    Returns (content, usage). usage may have prompt_tokens, completion_tokens, total_tokens.
    On failure returns (None, None).
    """
    model = model or OPENAI_CHATGPT_MODEL
    max_tokens = max_tokens if max_tokens is not None else OPENAI_CHATGPT_MAX_COMPLETION_TOKENS
    timeout = timeout or OPENAI_API_TIMEOUT
    client = OpenAI(api_key=api_key)

    messages = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(OPENAI_CHATGPT_RETRY_ATTEMPTS):
        try:
            # gpt-5.x and newer require max_completion_tokens; older models use max_tokens
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
                timeout=timeout,
            )
            choice = resp.choices[0] if resp.choices else None
            content = choice.message.content if choice and choice.message else None
            usage = None
            if resp.usage:
                usage = {
                    "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                    "total_tokens": getattr(resp.usage, "total_tokens", None),
                }
            return (content, usage)
        except Exception as e:
            wait = OPENAI_CHATGPT_RETRY_BASE_SECONDS * (attempt + 1)
            if attempt < OPENAI_CHATGPT_RETRY_ATTEMPTS - 1:
                logger.warning("OpenAI request failed (%s), retrying in %s s: %s", attempt + 1, wait, e)
                time.sleep(wait)
            else:
                logger.error("OpenAI request failed after %s attempts: %s", OPENAI_CHATGPT_RETRY_ATTEMPTS, e)
                return (None, None)
    return (None, None)
