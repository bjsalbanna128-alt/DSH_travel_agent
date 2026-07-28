"""DeepSeek provider — OpenAI-compatible client wrapper with JSON self-healing."""

import json
import re
import logging
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.core.exceptions import LLMCallError, ParseError

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """Wrapper around DeepSeek API (OpenAI-compatible)."""

    CHAT_MODEL = "deepseek-chat"
    REASONER_MODEL = "deepseek-reasoner"

    def __init__(self, model: str | None = None):
        import os
        self.model = model or self.CHAT_MODEL
        api_key = settings.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = settings.deepseek_base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((LLMCallError,)),
        reraise=True,
    )
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat request and return the text response."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self.client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            content = msg.content or ""
            # DeepSeek reasoner may put final answer in reasoning_content when content is empty
            if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                content = msg.reasoning_content
                logger.warning("Reasoner returned empty content, using reasoning_content as fallback")
            if not content:
                logger.warning(
                    f"DeepSeek returned empty response. "
                    f"Finish reason: {response.choices[0].finish_reason}"
                )
            return content
        except Exception as e:
            raise LLMCallError(f"DeepSeek API call failed: {e}") from e

    async def chat_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a chat request with tool calling support."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                return {
                    "type": "tool_calls",
                    "calls": [
                        {
                            "name": tc.function.name,
                            "arguments": safe_json_parse(
                                tc.function.arguments, "tool_call"
                            ),
                        }
                        for tc in msg.tool_calls
                    ],
                }

            return {"type": "text", "content": msg.content or ""}

        except Exception as e:
            raise LLMCallError(f"DeepSeek tool call failed: {e}") from e


def safe_json_parse(raw: str, source: str = "unknown") -> Any:
    """5-level JSON self-healing parser (truncation-resistant)."""
    # Level 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Level 2: extract from markdown code block
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # Level 3: find largest balanced { } block
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    # Level 4: find largest balanced [ ] block
    bracket_match = re.search(r"\[[\s\S]*\]", raw)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass

    # Level 5: try to repair truncated JSON (close unclosed braces/brackets/strings)
    try:
        repaired = _repair_truncated_json(raw)
        if repaired:
            return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    raise ParseError(
        f"[{source}] Cannot parse JSON from output. "
        f"Raw (first 300 chars): {raw[:300]}"
    )


def _repair_truncated_json(raw: str) -> str | None:
    """Attempt to close unclosed braces, brackets, and strings in truncated JSON."""
    s = raw.strip()
    if not s:
        return None

    # Remove trailing incomplete fragments (cut off mid-field)
    # Find last valid structural character
    for cut_marker in ['\n    ', '\n  ', ',\n', '",\n']:
        last_comma = s.rfind(',')
        last_brace = s.rfind('{')
        last_bracket = s.rfind('[')
        last_key = s.rfind('"')
        if last_key > max(last_comma, last_brace, last_bracket):
            # Cut off mid-string or mid-value — trim to last comma/brace
            cut = max(s.rfind(',\n'), s.rfind('{'), s.rfind('['), s.rfind('",'))
            if cut > 0:
                s = s[:cut + 1]

    # Count unclosed braces and brackets
    open_braces = s.count('{') - s.count('}')
    open_brackets = s.count('[') - s.count(']')

    # Check if last non-whitespace char looks like an unclosed string
    s = s.rstrip()
    if s.endswith(','):
        s = s[:-1]  # remove trailing comma

    # Count quotes to detect unclosed strings
    in_string = False
    i = 0
    while i < len(s):
        if s[i] == '\\':
            i += 2
            continue
        if s[i] == '"':
            in_string = not in_string
        i += 1
    if in_string:
        s += '"'

    # Close remaining structures
    s += ']' * open_brackets
    s += '}' * open_braces

    if open_braces > 0 or open_brackets > 0 or in_string:
        return s
    return None
