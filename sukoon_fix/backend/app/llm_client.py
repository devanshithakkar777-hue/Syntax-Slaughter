"""Sukoon — optional real-LLM upgrade layer.

Every "agent" in Sukoon is, by default, a transparent rule engine over the
patient's own logged data (see agentic_engine.py) — deliberately, because an
autonomous system in eldercare should never hallucinate a wrong answer about
a real person's safety. This module is the *opt-in* upgrade path: if the
operator sets SUKOON_LLM_API_KEY as an environment variable, specific,
narrow, low-risk surfaces (the Companion Chat's free-text replies, and the
doctor-facing Clinical Insight brief) route through a real model with a
strict system prompt, instead of the rule-based responder.

Two providers are supported, chosen with SUKOON_LLM_PROVIDER:
  - "groq"      (default) -- Groq's free tier (no credit card required),
                 serving open models (Llama, GPT-OSS, etc.) over an
                 OpenAI-compatible REST API. Get a free key at
                 https://console.groq.com/keys
  - "anthropic" -- a real Claude model, if you have an Anthropic API key.

If no key is configured, or the call fails/times out for any reason, every
caller here gets back None and falls back to the existing rule-based logic
automatically -- the app must always work identically with or without an
LLM configured. Nothing that can autonomously *act* (escalate, notify,
change data) ever goes through this module; it only ever generates text
that a human reviews, the same safety boundary the rest of the agent
network follows.
"""
import os

import requests

_ENV_KEY = "SUKOON_LLM_API_KEY"
_PROVIDER = os.environ.get("SUKOON_LLM_PROVIDER", "groq").strip().lower()

_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-3-5-haiku-20241022",
}
_MODEL = os.environ.get("SUKOON_LLM_MODEL") or _DEFAULT_MODELS.get(_PROVIDER, _DEFAULT_MODELS["groq"])

_client = None
_client_init_attempted = False


def llm_enabled() -> bool:
    return bool(os.environ.get(_ENV_KEY))


def _get_anthropic_client():
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True
    api_key = os.environ.get(_ENV_KEY)
    if not api_key:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        _client = None
    return _client


def _generate_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> "str | None":
    client = _get_anthropic_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=_MODEL, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}], timeout=12.0,
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip() or None
    except Exception:
        return None


def _generate_groq(system_prompt: str, user_prompt: str, max_tokens: int) -> "str | None":
    api_key = os.environ.get(_ENV_KEY)
    if not api_key:
        return None
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": _MODEL,
                "max_tokens": max_tokens,
                "temperature": 0.6,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=12.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text or None
    except Exception:
        return None


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> "str | None":
    """Returns the model's text reply, or None if the LLM path is unavailable
    or the call failed for any reason (never raises)."""
    if not llm_enabled():
        return None
    if _PROVIDER == "anthropic":
        return _generate_anthropic(system_prompt, user_prompt, max_tokens)
    return _generate_groq(system_prompt, user_prompt, max_tokens)


# ---------------------------------------------------------------------------
# Scoped prompts for Sukoon's two LLM-eligible surfaces
# ---------------------------------------------------------------------------

COMPANION_SYSTEM_PROMPT = """You are Sukoon's Companion, a warm, patient, simple-spoken comfort companion for an elderly person, possibly living with mild cognitive impairment, in Assam, India. Rules you must never break:
- You are NOT a doctor. Never give medical, medication, or diagnostic advice. If asked, gently say to speak with their caregiver or doctor.
- Never claim to take any action (you cannot call anyone, send messages, or change reminders) — if they need help, tell them to press their SOS button or tell their caregiver.
- Keep replies to 1-3 short, simple sentences. Warm, respectful, unhurried tone. No jargon, no slang.
- If they mention being in danger, in pain, having fallen, or feeling seriously unwell, tell them clearly and immediately to press the SOS button or call their caregiver now.
- If they seem confused, sad, or lonely, respond with gentle reassurance and simple grounding (today's day, something pleasant), never with pity or clinical language.
- Never discuss anything unrelated to their comfort, memories, day, or wellbeing (no politics, news, financial, or legal topics) — gently redirect instead."""

CLINICAL_BRIEF_SYSTEM_PROMPT = """You are a clinical summarization assistant for a geriatric doctor using the Sukoon platform. You will be given structured, real, already-verified data about one patient's last 30 days (medicine adherence, cognitive activity scores, mood log, safety escalations). Write a concise 3-4 sentence plain-language pre-visit briefing a doctor can read in 10 seconds.
Rules:
- Only state facts present in the data given to you. Never invent a number, date, or clinical claim not in the input.
- Never suggest a diagnosis, medication change, or treatment plan — you are summarizing observed patterns only, for the doctor's own clinical judgment.
- Plain, direct clinical register. No filler, no bullet points, no headers — a short paragraph only."""
