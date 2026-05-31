import os
import threading
import time
import urllib.error
import urllib.request
from typing import Annotated
from typing_extensions import TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from menu import MENU, menu_search

DEFAULT_MODEL = "google_genai:gemini-2.5-flash"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a friendly AI waiter at Udupi Park restaurant.

MENU LOOKUP RULE (mandatory):
- Before every add_to_tray call, you MUST call menu_lookup first to get the correct item_id.
- Never guess or invent an item_id.
- When browsing ("what dosas do you have?", "show me starters"), call menu_lookup to list options.

TERM EXTRACTION (any language → English):
From the user message, extract English search terms covering:
  • item name (e.g. "masala dosa", "coffee", "gobi")
  • section/type (e.g. "dosa", "starters", "drinks", "ice cream", "biryani")
  • modifiers (e.g. "butter", "paneer", "fried", "schezwan")
Pass these terms as a list to menu_lookup.

WORKFLOW:
1. Greet warmly and ask how you can help.
2. User mentions food → extract English terms → call menu_lookup(terms).
3. If one clear match: confirm with user, then add_to_tray(item_id, quantity).
4. If multiple matches: show options and ask which one.
5. If no match: tell the user and ask to clarify.
6. Show tray with view_tray when asked or before placing the order.
7. Place order with place_order only after the customer explicitly confirms.
8. Check status with check_order_status when asked.

Suggest popular items: dosas, idlis, coffee, tandoori starters, biriyani.
Always confirm before placing the order."""

# ── In-memory order state ─────────────────────────────────────────────────────

tray: dict[int, int] = {}   # item_id → quantity
order: dict | None = None   # set once user confirms

ORDER_STATUSES = ["placed", "preparing", "ready", "served"]


def reset_state() -> None:
    """Reset tray and order to empty — call this on session restart."""
    global tray, order
    tray = {}
    order = None


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def menu_lookup(terms: list[str]) -> str:
    """Search the menu by item name, section, or type using English keywords.
    Use for browsing ("what dosas do you have?") and before every add_to_tray.
    Returns up to 10 matches with item IDs, names, sections, and prices."""
    results = menu_search(terms)
    if not results:
        return f"No menu items found for: {', '.join(terms)}. Try different keywords."
    lines = [f"Found {len(results)} match(es):"]
    for item in results:
        lines.append(f"  [{item['id']}] {item['name']} ({item['section']}) — ₹{item['price']}")
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

tools = [menu_lookup, add_to_tray, view_tray, place_order, check_order_status]


class State(TypedDict):
    messages: Annotated[list, add_messages]


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

    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition)
    builder.add_edge("tools", "chatbot")
    return builder.compile()


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text(content) -> str:
    """Gemini 2.5 returns content as a list of typed blocks; extract text."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = " ".join(parts).strip()
    else:
        text = str(content)
    return text.replace("\\n", "\n").replace("\\t", "\t")
