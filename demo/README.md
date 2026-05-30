# Demo Run

## Terminal runtime - console.py

`uv run python console.py`


```txt
warning: `VIRTUAL_ENV=~/ai-waiter/.venv` does not match the project environment path `.venv` and will be ignored; use `--active` to target the active environment instead
============================================================
  Welcome to Udupi Park Restaurant
  (type 'quit'/'exit' to leave, 'restart' to reset)
============================================================

Waiter: Hello! Welcome to Udupi Park. How can I help you today?

You: need a cup of tea with milk 

Waiter: Great! I've added one cup of Tea to your tray. Is there anything else I can get for you? Perhaps some dosas or idlis? They are quite popular!

You: no. just confirm the tea order

Waiter: Your current tray has 1 Tea for a total of ₹32. Would you like to confirm and place this order?

You: yes

Waiter: Great! Your order has been placed. I'll keep you updated on its status.

You: 
[Order update] Status changed to: PREPARING
You: exit
Thank you for visiting! Goodbye!
```

## WebServer with web sockets - cbatbot_server.py

```bash
uv run python server.py
```

Access the chatbot [http://localhost:8000](http://localhost:8000)

![server.png](./server.png)