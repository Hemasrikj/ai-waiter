import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, date
from typing import Annotated
from typing_extensions import TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage, RemoveMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from menu import MENU, menu_search, menu_section_search, format_section_results

DEFAULT_MODEL = "google_genai:gemini-2.5-flash"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a friendly AI waiter at Udupi Park restaurant.

LANGUAGE RULE (mandatory):
- Always reply in the same language the user writes in.
- If the user writes in Kannada, reply in Kannada. Tamil → Tamil. Hindi → Hindi. English → English.
- This applies to ALL responses — greetings, confirmations, error messages, and every tool result
  you present to the user.
- When calling get_full_menu, menu_lookup, or list_categories, pass lang= matching the user's
  language: "en" English, "kn" Kannada, "ta" Tamil, "te" Telugu, "ml" Malayalam, "mr" Marathi,
  "hi" Hindi, "ur" Urdu, "kok" Konkani, "tcy" Tulu, "or" Odia. Default "en" if unsure.
- Translate all natural-language content from other tool results (view_tray, place_order,
  check_order_status): status words (e.g. "placed", "preparing", "ready", "served"), labels
  (e.g. "Current tray", "Total", "Order placed"), and any descriptive text.
- Keep numbers, prices (₹), and item IDs unchanged — do not translate those.

GROUNDING RULE (mandatory):
- Never state item names, prices, or item IDs from memory — always get them from tool results.
- Never confirm an item is available unless menu_lookup or get_full_menu returned it.
- If a tool returns no results, say so — do not invent alternatives or suggest items you haven't looked up.
- Do not describe dishes (ingredients, taste, origin) unless the menu data includes that information.

MENU LOOKUP RULE (mandatory):
- Before every add_to_tray call, you MUST call menu_lookup first to get the correct item_id.
- Never guess or invent an item_id.

MENU OVERVIEW vs. ITEM LOOKUP:
- "What food/categories do you have?" or any open-ended menu overview → call get_full_menu()
- "What categories/sections exist?" → call list_categories()
- Once the user narrows to a specific item ("show me all dosas", "I want a coffee",
  "add masala dosa") → call menu_lookup(terms) to get item IDs, names, and prices.

TERM EXTRACTION (any language → English):
From the user message, extract English search terms covering:
  • item name (e.g. "masala dosa", "coffee", "gobi")
  • section/type (e.g. "dosa", "starters", "drinks", "ice cream", "biryani")
  • modifiers (e.g. "butter", "paneer", "fried", "schezwan")
Pass these terms as a list to menu_lookup.

WORKFLOW:
1. Greet warmly and ask how you can help.
2. User asks what's available (overview) → call get_full_menu().
3. User asks what categories exist → call list_categories().
4. User mentions a specific food → extract English terms → call menu_lookup(terms).
4. If one clear match: confirm with user, then add_to_tray(item_id, quantity).
5. If multiple matches: show options and ask which one.
6. If no match: tell the user and ask to clarify.
7. Show tray with view_tray when asked or before placing the order.
8. Place order with place_order only after the customer explicitly confirms.
9. Check status with check_order_status when asked.

Suggest popular items: dosas, idlis, coffee, tandoori starters, biriyani.
Always confirm before placing the order."""

# ── In-memory order state ─────────────────────────────────────────────────────

tray: dict[int, int] = {}   # item_id → quantity
order: dict | None = None   # set once user confirms
_display_output: str = ""   # last display-only tool result; read by get_reply()

ORDER_STATUSES = ["placed", "preparing", "ready", "served"]


def reset_state() -> None:
    """Reset tray and order to empty — call this on session restart."""
    global tray, order, _display_output
    tray = {}
    order = None
    _display_output = ""


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def menu_lookup(terms: list[str], lang: str = "en") -> str:
    """Search the menu by item name, section, or type using English keywords.
    Use for browsing ("what dosas do you have?") and before every add_to_tray.
    Pass lang= matching the user's language code (e.g. "ta", "kn").
    Returns up to 10 matches with item IDs, names, sections, and prices."""
    results = menu_search(terms)
    if not results:
        return f"No menu items found for: {', '.join(terms)}. Try different keywords."
    lines = [f"Found {len(results)} match(es):"]
    for item in results:
        name = item["names"].get(lang, item["name"])
        section = item["section_paths"].get(lang, item["section_path"])
        lines.append(f"  [{item['id']}] {name} ({section}) — ₹{item['price']}")
    return "\n".join(lines)


@tool
def list_categories(lang: str = "en") -> str:
    """List all top-level menu categories with item counts and sample items.
    Pass lang= matching the user's language code (e.g. "ta", "kn").
    Use when the user asks what categories/sections/types of dishes are available."""
    results = menu_section_search(None)
    return f"Found {len(results)} section(s):\n{format_section_results(results, lang)}"


@tool
def get_full_menu(lang: str = "en") -> str:
    """Return the complete menu — all categories, items, and prices.
    Pass lang= matching the user's language code (e.g. "ta", "kn").
    Use for broad overview questions like 'what do you have?', 'show me the menu',
    'what food is available?', or when the user wants to browse everything."""
    items = list(MENU.values())
    lines = [f"Full menu ({len(items)} items):"]
    for item in items:
        name = item["names"].get(lang, item["name"])
        section = item["section_paths"].get(lang, item["section_path"])
        lines.append(f"  [{item['id']}] {name} ({section}) — ₹{item['price']}")
    return "\n".join(lines)


@tool
def add_to_tray(item_id: int, quantity: int) -> str:
    """Add or update an item quantity in the tray. Use quantity=0 to remove."""
    global tray
    if item_id not in MENU:
        return f"Item id {item_id} not found on the menu."
    if quantity <= 0:
        tray.pop(item_id, None)
        return f"Removed {MENU[item_id]['name']} from tray."
    tray[item_id] = quantity
    return f"Tray updated: {quantity}× {MENU[item_id]['name']} (₹{MENU[item_id]['price']} each)."


@tool
def view_tray() -> str:
    """Show the current tray contents and total."""
    if not tray:
        return "Your tray is empty."
    lines = ["Current tray:"]
    total = 0
    for item_id, qty in tray.items():
        item = MENU[item_id]
        subtotal = item["price"] * qty
        total += subtotal
        lines.append(f"  {qty}× {item['name']} — ₹{item['price']} × {qty} = ₹{subtotal}")
    lines.append(f"Total: ₹{total}")
    return "\n".join(lines)


@tool
def place_order() -> str:
    """Place the order for everything currently in the tray."""
    global order, tray
    if not tray:
        return "Cannot place an empty order. Please add items to the tray first."
    order = {
        "items": dict(tray),
        "status": "placed",
        "status_index": 0,
    }
    tray = {}
    _start_order_simulation()
    return "Order placed! Status: placed. I'll keep you updated as it progresses."


@tool
def check_order_status() -> str:
    """Check the current status of the placed order."""
    if order is None:
        return "No order has been placed yet."
    items_summary = ", ".join(
        f"{qty}× {MENU[iid]['name']}" for iid, qty in order["items"].items()
    )
    return f"Order [{items_summary}] — Status: {order['status'].upper()}"


# ── Order status simulation ───────────────────────────────────────────────────

def _start_order_simulation():
    def _advance():
        for delay, status in [(60, "preparing"), (120, "ready"), (180, "served")]:
            time.sleep(delay)
            if order is None:
                break
            order["status"] = status
            print(f"\n[Order update] Status changed to: {status.upper()}")
            print("You: ", end="", flush=True)
    threading.Thread(target=_advance, daemon=True).start()


# ── LangGraph setup ───────────────────────────────────────────────────────────

tools = [menu_lookup, list_categories, get_full_menu, add_to_tray, view_tray, place_order, check_order_status]


class State(TypedDict):
    messages: Annotated[list, add_messages]


class TraceCallbackHandler(BaseCallbackHandler):
    def __init__(self):
        super().__init__()
        self._total_in = 0
        self._total_out = 0
        self._llm_calls = 0
        self._llm_start: float = 0.0
        self._tool_start: float = 0.0
        self._session_start: float = time.perf_counter()

    def on_chat_model_start(self, serialized, messages, **_kwargs):
        self._llm_calls += 1
        self._llm_start = time.perf_counter()
        print(f"[trace] llm call #{self._llm_calls}")

    def on_tool_start(self, serialized, input_str, **_kwargs):
        name = (serialized or {}).get("name", "?")
        self._tool_start = time.perf_counter()
        print(f"[trace] tool → {name}  args: {input_str}")

    def on_tool_end(self, output, **_kwargs):
        elapsed = time.perf_counter() - self._tool_start
        print(f"[trace] tool ← {output}  ({elapsed*1000:.0f}ms)")

    def on_chain_start(self, serialized, _inputs, **_kwargs):
        name = (serialized or {}).get("name", "")
        if name in ("chatbot", "tools", "LangGraph"):
            print(f"[trace] node → {name}")

    def on_llm_end(self, response, **_kwargs):
        llm_elapsed = time.perf_counter() - self._llm_start
        session_elapsed = time.perf_counter() - self._session_start
        lo = response.llm_output or {}
        usage = lo.get("usage_metadata") or lo.get("token_usage") or lo.get("usage") or {}
        if not usage and response.generations:
            gen = response.generations[0][0] if response.generations[0] else None
            if gen is not None:
                msg_meta = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                usage = msg_meta or (getattr(gen, "generation_info", {}) or {}).get("usage_metadata", {})
        if usage:
            inp = (usage.get("input_tokens") or usage.get("prompt_tokens")
                   or usage.get("prompt_token_count", 0))
            out = (usage.get("output_tokens") or usage.get("completion_tokens")
                   or usage.get("candidates_token_count", 0))
            self._total_in += inp
            self._total_out += out
            print(f"[trace] tokens  in={inp} out={out}"
                  f"  (session total in={self._total_in} out={self._total_out} calls={self._llm_calls})"
                  f"  llm={llm_elapsed*1000:.0f}ms  session={session_elapsed:.1f}s")
        else:
            print(f"[trace] tokens  n/a (llm_output keys: {list(lo.keys())})"
                  f"  llm={llm_elapsed*1000:.0f}ms  session={session_elapsed:.1f}s")


def _check_base_url(base_url: str) -> None:
    """Fail fast if the model server at base_url is unreachable."""
    try:
        with urllib.request.urlopen(base_url, timeout=3):
            pass
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"ERROR: Cannot reach model server at {base_url}\n"
            f"  Make sure your local model server is running.\n"
            f"  ({exc})"
        )


def build_graph():
    model = os.getenv("MODEL", DEFAULT_MODEL)
    base_url = os.getenv("MODEL_BASE_URL") or None
    if base_url:
        _check_base_url(base_url)
    kwargs = {"base_url": base_url} if base_url else {}
    llm = init_chat_model(model, **kwargs)

    llm_with_tools = llm.bind_tools(tools)

    def chatbot(state: State) -> State:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [llm_with_tools.invoke(messages)]}

    DISPLAY_TOOLS = {"get_full_menu", "list_categories"}

    def after_tools(state: State):
        """Short-circuit to prune node if ALL recent tool calls are display-only."""
        from langchain_core.messages import ToolMessage
        recent = [m for m in reversed(state["messages"])
                  if isinstance(m, ToolMessage)]
        # Collect the batch that belongs to the last LLM call (contiguous ToolMessages)
        if not recent:
            return "chatbot"
        batch_names = {m.name for m in recent}
        if batch_names and batch_names.issubset(DISPLAY_TOOLS):
            return "prune_display_output"
        return "chatbot"

    def prune_display_output(state: State) -> State:
        """Write all display-tool results to module global, replace with stubs in state."""
        global _display_output
        from langchain_core.messages import ToolMessage
        tool_msgs = [m for m in state["messages"] if isinstance(m, ToolMessage)
                     and m.name in DISPLAY_TOOLS and not str(m.content).startswith("[")]
        full_content = "\n\n".join(str(m.content) for m in tool_msgs)
        _display_output = full_content
        removes_and_stubs = []
        for m in tool_msgs:
            stub = f"[{m.name} result sent to user — {len(str(m.content))} chars, not stored in context]"
            removes_and_stubs.append(RemoveMessage(id=m.id))
            removes_and_stubs.append(m.__class__(content=stub, name=m.name, tool_call_id=m.tool_call_id))
        return {"messages": removes_and_stubs}

    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("prune_display_output", prune_display_output)
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition)
    builder.add_conditional_edges("tools", after_tools)
    builder.add_edge("prune_display_output", END)
    return builder.compile()


# ── Helpers ───────────────────────────────────────────────────────────────────

def current_time() -> str:
    """Return HH:MM:SS AM/PM for today, or DD-MM-YYYY HH:MM:SS AM/PM for another date."""
    now = datetime.now()
    time_part = now.strftime("%I:%M:%S %p")
    if now.date() == date.today():
        return time_part
    return now.strftime("%d-%m-%Y ") + time_part

def extract_text(content) -> str:
    """Extract display text from an AI or Tool message content."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = " ".join(parts).strip()
    else:
        text = str(content)
    return text.replace("\\n", "\n").replace("\\t", "\t")


def get_reply(state) -> str:
    """Return the text to show the user — consumes _display_output if set (auto-clears it)."""
    global _display_output
    if _display_output:
        result = _display_output
        _display_output = ""
        return result
    return extract_text(state["messages"][-1].content)
