import itertools
import os
import sys
import threading
from dotenv import load_dotenv

load_dotenv()

from ai_waiter import build_graph, extract_text, reset_state, State, DEFAULT_MODEL


def thinking(stop_event: threading.Event) -> None:
    for frame in itertools.cycle([".  ", ".. ", "..."]):
        if stop_event.is_set():
            break
        sys.stdout.write(f"\rWaiter: thinking{frame}")
        sys.stdout.flush()
        stop_event.wait(0.4)
    sys.stdout.write("\r" + " " * 24 + "\r")
    sys.stdout.flush()


def invoke_with_spinner(graph, state):
    result = [None]
    error = [None]
    stop = threading.Event()

    def run():
        try:
            result[0] = graph.invoke(state)
        except Exception as exc:
            error[0] = exc
        finally:
            stop.set()

    threading.Thread(target=run, daemon=True).start()
    thinking(stop)
    if error[0]:
        raise error[0]
    return result[0]


def main():
    graph = build_graph()
    model = os.getenv("MODEL", DEFAULT_MODEL)

    print("=" * 60)
    print("  Welcome to Udupi Park Restaurant")
    print(f"  Model: {model}")
    print("  (type 'quit'/'exit' to leave, 'restart' to reset)")
    print("=" * 60)

    state = invoke_with_spinner(graph, {"messages": [{"role": "user", "content": "Hello"}]})
    print(f"Waiter: {extract_text(state['messages'][-1].content)}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nThank you for visiting! Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            print("Thank you for visiting! Goodbye!")
            break
        if user_input.lower() == "restart":
            reset_state()
            state = invoke_with_spinner(graph, {"messages": [{"role": "user", "content": "Hello"}]})
            print(f"Waiter: {extract_text(state['messages'][-1].content)}\n")
            continue

        state["messages"].append({"role": "user", "content": user_input})
        state = invoke_with_spinner(graph, state)
        print(f"Waiter: {extract_text(state['messages'][-1].content)}\n")


if __name__ == "__main__":
    main()
