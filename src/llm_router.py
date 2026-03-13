"""Lightweight LLM router for BigClaw — cheap models via OpenRouter.

Uses Gemini Flash for routine data summarization tasks, reserving
Sonnet/Opus for analytical work that requires deep reasoning.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

# Model IDs on OpenRouter
GEMINI_FLASH = "google/gemini-2.5-flash"
GEMINI_FLASH_LITE = "google/gemini-3.1-flash-lite-preview"
SONNET = "anthropic/claude-sonnet-4-6"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_openrouter(prompt: str, system: str = "", model: str = GEMINI_FLASH,
                    max_tokens: int = 2048, temperature: float = 0.3) -> str:
    """Call a model via OpenRouter API.

    Args:
        prompt: User message content
        system: System prompt (optional)
        model: OpenRouter model ID (default: Gemini Flash)
        max_tokens: Max response tokens
        temperature: Sampling temperature

    Returns:
        Model response text, or error string prefixed with "ERROR:"
    """
    api_key = OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "ERROR: OPENROUTER_API_KEY not set"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bigclaw.grandpapa.net",
        "X-Title": "BigClaw AI",
    }

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        logger.info(f"OpenRouter call: model={model}, prompt_len={len(prompt)}")
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        logger.info(f"OpenRouter response: {len(content)} chars")
        return content
    except requests.exceptions.Timeout:
        logger.error(f"OpenRouter timeout for {model}")
        return "ERROR: OpenRouter request timed out"
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return f"ERROR: OpenRouter call failed: {e}"


def summarize_with_flash(data: str, instruction: str, max_tokens: int = 2048) -> str:
    """Summarize/format data using Gemini Flash (cheap).

    Args:
        data: Raw data to summarize
        instruction: What to do with the data
        max_tokens: Max response tokens

    Returns:
        Summarized text
    """
    system = (
        "You are BigClaw AI, a crab-themed investment research assistant. "
        "Be concise and actionable. Use markdown formatting."
    )
    prompt = f"{instruction}\n\n---\nDATA:\n{data}"
    return call_openrouter(prompt, system=system, max_tokens=max_tokens)
