# Jimmy

Jimmy is a local, learning AI agent that lives in your terminal.

## What Jimmy does
- **Talks**: free-form conversation, not just commands.
- **Learns**: researches topics on the web and remembers the facts.
- **Remembers**: stores knowledge and past conversations in a local SQLite database.
- **Trades (paper)**: tracks a paper portfolio, can place simulated trades, and reviews performance.

## Run it
```bash
python ai_agent.py
```

No API keys required. Everything is stored in `~/.jimmy_memory.db`.

## Example
```
You: hey jimmy
Jimmy: Hey! I'm here. What are we getting into?

You: learn quantum computing
Jimmy: Jimmy is researching: quantum computing...
Jimmy learned 5 new facts about 'quantum computing'.

You: what do you know about quantum computing
Jimmy: Here is what Jimmy remembers about 'quantum computing':
- ...

You: buy 10 shares of AAPL at 200
Jimmy: Bought 10 shares of AAPL at $200.00. Portfolio value: $2,000.00.

You: portfolio
Jimmy: Cash: $8,000.00 | Holdings: AAPL x10 @ $200.00 | Value: $2,000.00
```
