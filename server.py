# LIMITATION: ai_waiter.py uses module-level globals (tray, order).
# This server supports exactly ONE concurrent user session.
# If two browser tabs connect simultaneously they share the same tray/order
# state and order-update notifications are not demultiplexed per connection.

import asyncio
import json
import os
import threading
import time
from argparse import ArgumentParser

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

# load_dotenv must run before ai_waiter is imported — ai_waiter calls
# init_chat_model() at module level which reads GOOGLE_API_KEY.
load_dotenv()

import ai_waiter
from ai_waiter import build_graph, extract_text, get_reply, reset_state, State, DEFAULT_MODEL, TraceCallbackHandler

graph = build_graph()

_trace_config: dict = {}

# ── Order-update bridge ───────────────────────────────────────────────────────
# The simulation thread posts status strings here; the WebSocket pump task
# drains them and forwards to the connected client.

_order_queue: asyncio.Queue[str] = asyncio.Queue()
_event_loop: asyncio.AbstractEventLoop | None = None


def _patched_start_order_simulation() -> None:
    def _advance() -> None:
        for delay, status in [(60, "preparing"), (120, "ready"), (180, "served")]:
            time.sleep(delay)
            if ai_waiter.order is None:
                break
            ai_waiter.order["status"] = status
            if _event_loop is not None:
                _event_loop.call_soon_threadsafe(_order_queue.put_nowait, status)
    threading.Thread(target=_advance, daemon=True).start()


# Install the patch before any tool can trigger the original.
ai_waiter._start_order_simulation = _patched_start_order_simulation

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI()


@app.get("/", response_class=FileResponse)
async def serve_frontend() -> FileResponse:
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    global _event_loop
    await ws.accept()
    _event_loop = asyncio.get_running_loop()

    async def pump_order_updates() -> None:
        while True:
            status = await _order_queue.get()
            try:
                await ws.send_json({"type": "order_update", "status": status})
            except Exception:
                return

    pump_task = asyncio.create_task(pump_order_updates())
    session_state: State = {"messages": []}

    try:
        # Greeting
        session_state = await asyncio.to_thread(
            graph.invoke, {"messages": [{"role": "user", "content": "Hello"}]}, _trace_config
        )
        await ws.send_json({
            "type": "reply",
            "text": get_reply(session_state),
        })

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")

            if kind == "restart":
                reset_state()
                session_state = await asyncio.to_thread(
                    graph.invoke,
                    {"messages": [{"role": "user", "content": "Hello"}]},
                    _trace_config,
                )
                await ws.send_json({
                    "type": "reply",
                    "text": get_reply(session_state),
                })

            elif kind == "message":
                text = msg.get("text", "").strip()
                if not text:
                    continue
                session_state["messages"].append({"role": "user", "content": text})
                session_state = await asyncio.to_thread(graph.invoke, session_state, _trace_config)
                await ws.send_json({
                    "type": "reply",
                    "text": get_reply(session_state),
                })

            else:
                await ws.send_json({"type": "error", "text": "Unknown message type"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "text": str(exc)})
        except Exception:
            pass
    finally:
        pump_task.cancel()

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--trace", action="store_true", help="Print tool and graph node calls to stdout")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.trace:
        _trace_config = {"callbacks": [TraceCallbackHandler()]}

    model = os.getenv("MODEL", DEFAULT_MODEL)
    print(f"Starting server with model: {model}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, reload=False)
