"""Orchestration engine using real ReAct pattern with OpenAI function calling."""
import json
import logging
import re
from typing import Dict, Any, AsyncIterator

from openai import AsyncOpenAI

from app.core.guardrails import GuardrailsEngine
from app.tools.executor import ToolExecutor
from app.tools.registry import TOOL_DEFINITIONS
from app.services.memory import MemoryService
from app.utils.config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ShopAssist — a warm, natural AI shopping companion. Think of yourself as a knowledgeable friend who loves helping people find great products, but also just enjoys a good conversation.

YOUR PERSONALITY:
- Talk like a real person, not a product catalog. Be warm, casual, and genuinely helpful.
- When someone greets you, greet them back naturally and ask what brings them in today.
- If someone asks a general question (time, weather, trivia), answer it briefly and naturally pivot: e.g. "I can't check the time, but if you're looking for a great watch I can help with that 😄"
- Gently nudge conversations toward shopping, but never force it. Let curiosity lead.
- If the user is vague ("I need something nice"), ask a friendly clarifying question — budget? occasion? who's it for?

TOOL RULES (non-negotiable):
1. ALWAYS use search_products or browse_category when the user asks about any product, category, or shopping need. NEVER answer product questions from memory.
2. ONLY call tools when the user has clear shopping intent. Greetings, small talk, and general questions get a natural response with NO tool calls.
3. Never invent prices, discounts, or promo codes. Use ONLY data returned by tools.
4. Never claim a product is in stock without verifying via tools.
5. When presenting products, always mention merchant name and price.
6. If the user asks to add something to cart, use the add_to_cart tool.

RESPONSE STYLE:
- Keep it concise and conversational — no walls of text.
- For product results, give a short friendly intro before listing items.
- End shopping responses with a natural follow-up question ("Want me to narrow it down by budget or color?").

User context:
- Recent products: {recent_products}
- Cart: {cart_info}
- Preferences: {preferences}"""

# Pure greeting / social phrases (full-message match)
_GREETING_RE = re.compile(
    r"^\s*(hi+|hey+|hello+|howdy|hiya|yo+|greetings|"
    r"what'?s\s*up|sup|what'?s\s*good|what'?s\s*new|"
    r"how\s*are\s*(you|u)\??|how'?s\s*it\s*going\??|"
    r"good\s*(morning|afternoon|evening|day)|"
    r"thanks|thank\s*you|thx|ty|"
    r"bye|goodbye|see\s*ya|later|"
    r"ok(ay)?|cool|nice|great|awesome|sounds\s*good|got\s*it|"
    r"sure|yep|yeah|nope|lol|lmao|haha)\s*[!.?,]*\s*$",
    re.IGNORECASE,
)

# Message STARTS with a greeting word (catches "hi whatsuo", "hey there", "hello friend" etc.)
_GREETING_START_RE = re.compile(
    r"^\s*(hi+|hey+|hello+|howdy|hiya|yo+|sup|greetings|good\s*(morning|afternoon|evening|day))\b",
    re.IGNORECASE,
)

# General non-shopping questions that should never trigger a product search
_NON_SHOPPING_RE = re.compile(
    r"^\s*(what'?s?\s*(the\s*)?(time|day|date|year|month)|"
    r"what\s*(time|day|date|year|month|is\s*(it|the\s*(time|date|day)))|"
    r"who\s*(are\s*you|made\s*you|created\s*you|built\s*you|is\s*your\s*creator)|"
    r"what\s*are\s*you|tell\s*me\s*about\s*yourself|"
    r"how\s*does\s*(this|the\s*app)\s*work|what\s*can\s*you\s*(do|help)|"
    r"what'?s?\s*the\s*weather|are\s*you\s*(a\s*)?(bot|ai|robot|human|real)|"
    r"do\s*you\s*(have\s*feelings|feel|think|know\s*everything))\b",
    re.IGNORECASE,
)

# Time/date/meta questions that can appear anywhere in a short message
_TIME_QUESTION_RE = re.compile(
    r"(what'?s?\s*(the\s*)?(time|day|date|year)|"
    r"what\s+time\s+is\s+it|"
    r"do\s+you\s+know\s+the\s+time|"
    r"current\s+(time|date|day|year))",
    re.IGNORECASE,
)

# Phrases that explicitly tell the assistant not to search / show products
_NO_SEARCH_PHRASES = (
    "don't show", "dont show", "do not show",
    "no products", "don't search", "dont search", "do not search",
    "just chat", "just talk", "just saying", "just hi", "just hello",
    "not shopping", "not looking to buy", "not looking for",
    "just browsing", "don't recommend", "dont recommend",
    "stop showing", "without products", "no recommendations",
)


def _is_conversational(message: str) -> bool:
    """True when the message has no shopping intent OR explicitly asks to skip product search."""
    stripped = message.strip()
    lowered = stripped.lower()

    # Explicit opt-out phrases
    if any(phrase in lowered for phrase in _NO_SEARCH_PHRASES):
        return True

    # Exact full-message greeting match
    if _GREETING_RE.match(stripped):
        return True

    # Short message (≤8 words) that starts with a greeting word
    # Catches "hi whatsuo", "hey there how are you", "hello friend" etc.
    if len(stripped.split()) <= 8 and _GREETING_START_RE.match(stripped):
        return True

    # General knowledge / meta questions — answer naturally, never search
    if _NON_SHOPPING_RE.match(stripped):
        return True

    # Short messages (≤10 words) that contain a time/date question anywhere
    if len(stripped.split()) <= 10 and _TIME_QUESTION_RE.search(stripped):
        return True

    return False


class OrchestrationEngine:
    """Processes user messages through guardrails -> ReAct tool loop -> streaming response."""

    def __init__(self, guardrails: GuardrailsEngine, tool_executor: ToolExecutor, memory: MemoryService):
        self.guardrails = guardrails
        self.executor = tool_executor
        self.memory = memory
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def process_message(
        self, user_id: str, session_id: str, message: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Full pipeline: guardrails -> ReAct -> stream response."""

        # --- Pre-check guardrails ---
        blocked = self.guardrails.check_input(message)
        if blocked:
            yield {"type": "text", "content": blocked}
            yield {"type": "done"}
            return

        # --- Load conversation context ---
        ctx = await self.memory.get_context(user_id, session_id)
        await self.memory.add_message(ctx, "user", message)

        # --- Build messages for the LLM ---
        recent = ", ".join(ctx.recent_products[-3:]) if ctx.recent_products else "none"
        cart_info = f"{len(ctx.cart_items)} items" if ctx.cart_items else "empty"
        prefs = str(ctx.user_preferences) if ctx.user_preferences else "not set"

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    recent_products=recent, cart_info=cart_info, preferences=prefs
                ),
            }
        ]
        # Include last few conversation turns
        for m in ctx.messages[-8:]:
            messages.append({"role": m["role"], "content": m["content"]})

        # ----------------------------------------------------------------
        # FAST PATH — conversational messages skip the ReAct loop entirely.
        # No tools are offered, so no products can leak through.
        # One LLM call → stream → done. Roughly 2× faster than shopping path.
        # ----------------------------------------------------------------
        if _is_conversational(message):
            log.info("Conversational message — skipping ReAct loop")
            full_response = ""
            try:
                stream = await self._client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response += delta.content
                        yield {"type": "text", "content": delta.content}
            except Exception as exc:
                log.error("LLM streaming failed (conversational): %s", exc)
                full_response = "Hey! How can I help you today?"
                yield {"type": "text", "content": full_response}

            full_response = self.guardrails.check_output(full_response)
            await self.memory.add_message(ctx, "assistant", full_response)
            yield {"type": "done"}
            return

        # ----------------------------------------------------------------
        # SHOPPING PATH — full ReAct loop with tools
        # ----------------------------------------------------------------
        products_collected = []
        llm_error = False  # True only when the LLM API call itself fails

        for iteration in range(settings.MAX_REACT_ITERATIONS):
            try:
                resp = await self._client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )
            except Exception as exc:
                log.error("LLM call failed: %s", exc)
                llm_error = True
                break

            assistant_msg = resp.choices[0].message

            if not assistant_msg.tool_calls:
                # LLM deliberately chose not to call tools — trust that decision.
                # This is the correct path for non-shopping queries that slipped
                # past _is_conversational (e.g. "time", "I am asking for the time").
                break

            messages.append(assistant_msg.model_dump(exclude_none=True))

            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                log.info("ReAct iter %d: %s(%s)", iteration, tool_name, args)
                result_str = await self.executor.run(tool_name, args, user_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

                try:
                    result_data = json.loads(result_str)
                    if "products" in result_data:
                        products_collected.extend(result_data["products"])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Fallback search ONLY when the LLM API itself failed — not when the LLM
        # consciously decided to skip tools (that would override correct behaviour).
        if llm_error and not products_collected:
            log.info("LLM error — running fallback search for: %s", message[:80])
            try:
                fallback_result = await self.executor.run(
                    "search_products", {"query": message}, user_id
                )
                fallback_data = json.loads(fallback_result)
                if "products" in fallback_data:
                    products_collected.extend(fallback_data["products"])
                    messages.append({
                        "role": "system",
                        "content": f"[System: search returned {len(fallback_data['products'])} results. Present these to the user.]"
                    })
            except Exception as exc:
                log.warning("Fallback search failed: %s", exc)

        # Stream final response
        full_response = ""
        try:
            stream = await self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content
                    yield {"type": "text", "content": delta.content}
        except Exception as exc:
            log.error("LLM streaming failed: %s", exc)
            if products_collected:
                full_response = f"I found {len(products_collected)} product{'s' if len(products_collected) != 1 else ''} for you — check them out in the results panel! Want me to filter by budget or anything else?"
            else:
                full_response = "I didn't quite catch that — could you tell me what you're looking for? I can help with clothing, tech, home goods, and more!"
            yield {"type": "text", "content": full_response}

        # Send deduplicated product cards
        if products_collected:
            seen_ids: set = set()
            unique_products = []
            for p in products_collected:
                pid = p.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    unique_products.append(p)
            yield {"type": "products", "products": unique_products}

        full_response = self.guardrails.check_output(full_response)
        await self.memory.add_message(ctx, "assistant", full_response)
        yield {"type": "done"}
