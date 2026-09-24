"""
llm_client.py
LLM access for the Step 2 harmonisation helpers.

Every LLM call in Step 2 has the same shape: a short instruction, some record
context, and a reply that must be one JSON object with known fields. This module
owns that call so the helpers never deal with the transport, and so the backend
can be switched without touching them. Two providers are supported:

- ``anthropic`` (default): Claude through the Anthropic API.
  Replies use structured outputs (``output_config.format``), so they always
  parse and enum fields can only take values the MOTEL schema allows. Large,
  stable context such as a registry listing is sent as a cached system block,
  and server-side refusal fallbacks are enabled.
- ``ollama``: a local model served by Ollama, such as ``qwen3:14b``. Needs no
  API key or network access, but needs a running Ollama server and, for a
  14B model, a GPU. The reply schema is passed as Ollama's ``format`` and the
  reply is parsed defensively, with one retry on invalid JSON.

Configuration is read from the environment and can be changed at run time
with ``configure()``:

    MOTEL_LLM_PROVIDER   anthropic | ollama, default anthropic
    MOTEL_LLM_MODEL      model name; default claude-opus-5 for anthropic,
                         qwen3:14b for ollama
    MOTEL_CLAUDE_EFFORT  low | medium | high | xhigh | max, default high;
                         Claude only. Set it to an empty string for models
                         without effort support such as claude-haiku-4-5
    ANTHROPIC_API_KEY    Claude credential (or any other source the Anthropic
                         SDK resolves)
    OLLAMA_HOST          Ollama server address, default http://localhost:11434

Token usage is tallied per run so the log records what a run consumed. Both
SDKs are imported on first use, so the no-LLM harmonisation path
(``use_llm=False``) runs without either installed.
"""

import json
import os
import re

PROVIDERS = ("anthropic", "ollama")
DEFAULT_MODELS = {"anthropic": "claude-opus-5", "ollama": "qwen3:14b"}

PROVIDER = os.environ.get("MOTEL_LLM_PROVIDER", "anthropic").strip().lower()
MODEL = os.environ.get("MOTEL_LLM_MODEL") or DEFAULT_MODELS.get(PROVIDER, "")
EFFORT = os.environ.get("MOTEL_CLAUDE_EFFORT", "high")
MAX_TOKENS = 16000
MAX_RETRIES = 5
# Re-runs a declined request on Anthropic's recommended fallback model, server-side.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

_anthropic_client = None
_ollama_client = None
usage = {"requests": 0, **{field: 0 for field in USAGE_FIELDS}}


class LLMError(RuntimeError):
    """Raised when the LLM returns no usable JSON reply or cannot be reached."""


def configure(provider=None, model=None, effort=None):
    """
    Switch the LLM backend for the rest of the session.

    Args:
        provider (str | None): "anthropic" or "ollama". None keeps the current one.
        model (str | None): Model name. None picks the provider's default when
            the provider changes, and keeps the current model otherwise.
        effort (str | None): Claude effort level; ignored by Ollama.

    Returns:
        dict: The settings now in effect, as returned by ``settings()``.
    """
    global PROVIDER, MODEL, EFFORT
    if provider is not None:
        provider = provider.strip().lower()
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM provider {provider!r}; use one of {PROVIDERS}")
        if provider != PROVIDER and model is None:
            MODEL = DEFAULT_MODELS[provider]
        PROVIDER = provider
    if model is not None:
        MODEL = model
    if effort is not None:
        EFFORT = effort
    return settings()


def settings():
    """Return the model settings to record in the harmonisation log."""
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "effort": (EFFORT or None) if PROVIDER == "anthropic" else None,
        "max_tokens": MAX_TOKENS if PROVIDER == "anthropic" else None,
    }


def reset_usage():
    """Zero the token tally at the start of a run."""
    for key in usage:
        usage[key] = 0


def ask_json(system, prompt, schema, context=""):
    """
    Ask the configured LLM for one JSON object matching ``schema``.

    Args:
        system (str): Role instruction for this kind of call.
        prompt (str): The record-specific request.
        schema (dict): JSON schema the reply must follow. Every object needs
            ``additionalProperties: false``.
        context (str): Large context that stays the same across many calls,
            such as a registry listing. Claude caches it, so it should not
            contain anything that changes per call.

    Returns:
        dict: The parsed reply.

    Raises:
        LLMError: When the model declines, the reply is cut off or unparseable,
            or the provider cannot be reached.
    """
    if PROVIDER == "anthropic":
        return _ask_anthropic(system, prompt, schema, context)
    if PROVIDER == "ollama":
        return _ask_ollama(system, prompt, schema, context)
    raise LLMError(f"Unknown LLM provider {PROVIDER!r}; use one of {PROVIDERS}")


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------
def get_anthropic_client():
    """Create the Anthropic client on first use."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(max_retries=MAX_RETRIES)
    return _anthropic_client


def _ask_anthropic(system, prompt, schema, context):
    system_blocks = [{"type": "text", "text": system}]
    if context:
        system_blocks.append({
            "type": "text",
            "text": context,
            "cache_control": {"type": "ephemeral"},
        })

    output_config = {"format": {"type": "json_schema", "schema": schema}}
    if EFFORT:
        output_config["effort"] = EFFORT

    try:
        response = get_anthropic_client().beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system_blocks,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
    except TypeError as exc:
        if "authentication" not in str(exc).lower():
            raise
        raise LLMError(
            "No Anthropic credential found. Set ANTHROPIC_API_KEY, switch to the "
            "local model with MOTEL_LLM_PROVIDER=ollama, or run the harmonisation "
            "with use_llm=False (--no-llm) for exact-match resolution."
        ) from exc

    usage["requests"] += 1
    for field in USAGE_FIELDS:
        usage[field] += getattr(response.usage, field, None) or 0
    if response.stop_reason == "refusal":
        raise LLMError(f"Claude declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise LLMError(f"Claude's reply was cut off at max_tokens={MAX_TOKENS}")

    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        reply = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Claude did not return valid JSON: {text[:200]!r}") from exc
    if not isinstance(reply, dict):
        raise LLMError(f"Claude returned {type(reply).__name__}, expected a JSON object")
    return reply


# ---------------------------------------------------------------------------
# Ollama (local model)
# ---------------------------------------------------------------------------
def get_ollama_client():
    """Create the Ollama client on first use; the host comes from OLLAMA_HOST."""
    global _ollama_client
    if _ollama_client is None:
        import ollama

        _ollama_client = ollama.Client()
    return _ollama_client


def _parse_json_object(content):
    """
    Extract one JSON object from a local model's reply.

    Local models may wrap the object in <think> blocks or Markdown fences even
    when a format is requested, so those are stripped before decoding.
    """
    raw = str(content or "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    raw = re.sub(r"```(?:json)?\s*|```", "", raw, flags=re.IGNORECASE).strip()
    if not raw:
        raise ValueError("the model returned an empty response")

    decoder = json.JSONDecoder()
    for start, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    preview = raw[:200].replace("\n", " ")
    raise ValueError(f"the model did not return a valid JSON object: {preview!r}")


def _ask_ollama(system, prompt, schema, context):
    import ollama

    system_text = f"{system}\n\n{context}" if context else system
    messages = [
        {"role": "system", "content": system_text + "\nOutput only valid JSON."},
        {"role": "user", "content": prompt},
    ]
    for attempt in range(2):
        try:
            response = get_ollama_client().chat(
                model=MODEL,
                messages=messages,
                format=schema,
                options={"temperature": 0.0},
            )
        except ConnectionError as exc:
            raise LLMError(
                f"Cannot reach the Ollama server ({exc}). Start it with `ollama serve`, "
                "or switch to Claude with MOTEL_LLM_PROVIDER=anthropic."
            ) from exc
        except ollama.ResponseError as exc:
            raise LLMError(
                f"Ollama rejected the request for model {MODEL!r}: {exc.error}. "
                f"If the model is missing, run `ollama pull {MODEL}`."
            ) from exc

        usage["requests"] += 1
        usage["input_tokens"] += response.get("prompt_eval_count") or 0
        usage["output_tokens"] += response.get("eval_count") or 0

        content = response["message"]["content"]
        try:
            return _parse_json_object(content)
        except ValueError as exc:
            if attempt == 1:
                raise LLMError(f"Ollama model {MODEL!r}: {exc}") from exc
            messages.extend([
                {"role": "assistant", "content": str(content or "")},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not a valid JSON object. "
                        f"Return only one JSON object with these fields: {list(schema.get('properties', {}))}"
                    ),
                },
            ])
