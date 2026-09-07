import subprocess, sys
# install requests if missing
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests
import sqlite3, os, re, json, random
from datetime import datetime
from html.parser import HTMLParser

# Database path: default to a file in the user's home directory
DB_PATH = os.path.expanduser("~/.jimmy_memory.db")
STARTING_CASH = 10000.0


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        topic TEXT,
        fact TEXT,
        source TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        question TEXT,
        answer TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT UNIQUE,
        shares REAL,
        avg_price REAL,
        updated TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        side TEXT,
        shares REAL,
        price REAL,
        note TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    # seed starting cash if not present
    c.execute("SELECT value FROM settings WHERE key='cash'")
    if c.fetchone() is None:
        c.execute("INSERT INTO settings (key, value) VALUES ('cash', ?)", (str(STARTING_CASH),))
    conn.commit()
    return conn


def save_knowledge(conn, topic, fact, source):
    c = conn.cursor()
    c.execute("INSERT INTO knowledge (timestamp, topic, fact, source) VALUES (?, ?, ?, ?)",
              (datetime.now().isoformat(), topic, fact, source))
    conn.commit()


def save_conversation(conn, question, answer):
    c = conn.cursor()
    c.execute("INSERT INTO conversations (timestamp, question, answer) VALUES (?, ?, ?)",
              (datetime.now().isoformat(), question, answer))
    conn.commit()


def recall_knowledge(conn, topic):
    c = conn.cursor()
    c.execute("SELECT fact, source, timestamp FROM knowledge WHERE topic LIKE ? ORDER BY timestamp DESC LIMIT 5",
              (f"%{topic}%",))
    return c.fetchall()


def list_topics(conn):
    c = conn.cursor()
    c.execute("SELECT DISTINCT topic FROM knowledge ORDER BY topic")
    return [row[0] for row in c.fetchall()]


def get_cash(conn):
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='cash'")
    row = c.fetchone()
    return float(row[0]) if row else STARTING_CASH


def set_cash(conn, amount):
    c = conn.cursor()
    c.execute("INSERT INTO settings (key, value) VALUES ('cash', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (str(amount),))
    conn.commit()


def get_holdings(conn):
    c = conn.cursor()
    c.execute("SELECT symbol, shares, avg_price FROM portfolio ORDER BY symbol")
    return c.fetchall()


def get_price(symbol):
    """Best-effort price lookup. Tries a few free endpoints; falls back to a simulated price."""
    sym = symbol.upper().strip()
    # 1) Yahoo chart API (no key)
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        data = r.json()
        price = data["chart"]["result"][0]["meta"].get("regularMarketPrice")
        if price:
            return float(price), "yahoo"
    except Exception:
        pass
    # 2) Stooq CSV
    try:
        r = requests.get(f"https://stooq.com/q/l/?s={sym.lower()}.us&f=sd2t2ohlcv&h&e=csv",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        parts = r.text.strip().split(",")
        if len(parts) >= 7 and parts[-1] not in ("N/D", ""):
            return float(parts[-1]), "stooq"
    except Exception:
        pass
    # 3) simulated fallback so the bot never dies
    return round(random.uniform(50, 500), 2), "simulated"


def place_trade(conn, symbol, side, shares, price=None, note=""):
    sym = symbol.upper().strip()
    if price is None:
        price, src = get_price(sym)
    else:
        src = "manual"
    cash = get_cash(conn)
    c = conn.cursor()
    c.execute("SELECT shares, avg_price FROM portfolio WHERE symbol=?", (sym,))
    row = c.fetchone()
    cur_shares = row[0] if row else 0.0
    cur_avg = row[1] if row else 0.0

    if side == "buy":
        cost = shares * price
        if cost > cash + 1e-6:
            return None, f"Not enough cash. You have ${cash:,.2f}, need ${cost:,.2f}."
        new_shares = cur_shares + shares
        new_avg = ((cur_shares * cur_avg) + (shares * price)) / new_shares if new_shares else 0.0
        c.execute("""INSERT INTO portfolio (symbol, shares, avg_price, updated)
                       VALUES (?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET
                       shares=excluded.shares, avg_price=excluded.avg_price, updated=excluded.updated""",
                  (sym, new_shares, new_avg, datetime.now().isoformat()))
        set_cash(conn, cash - cost)
    else:  # sell
        if shares > cur_shares + 1e-9:
            return None, f"You only hold {cur_shares} shares of {sym}."
        proceeds = shares * price
        new_shares = cur_shares - shares
        if new_shares < 1e-9:
            c.execute("DELETE FROM portfolio WHERE symbol=?", (sym,))
        else:
            c.execute("UPDATE portfolio SET shares=?, updated=? WHERE symbol=?",
                      (new_shares, datetime.now().isoformat(), sym))
        set_cash(conn, cash + proceeds)

    c.execute("INSERT INTO trades (timestamp, symbol, side, shares, price, note) VALUES (?,?,?,?,?,?)",
              (datetime.now().isoformat(), sym, side, shares, price, note or src))
    conn.commit()
    return price, src


def portfolio_summary(conn):
    cash = get_cash(conn)
    holdings = get_holdings(conn)
    lines = [f"Cash: ${cash:,.2f}"]
    total = cash
    for sym, shares, avg in holdings:
        price, src = get_price(sym)
        val = shares * price
        total += val
        lines.append(f"{sym}: {shares:g} shares @ avg ${avg:,.2f} | now ${price:,.2f} ({src}) = ${val:,.2f}")
    lines.append(f"Total value: ${total:,.2f}")
    return "\n".join(lines)


def recent_trades(conn, n=5):
    c = conn.cursor()
    c.execute("SELECT timestamp, symbol, side, shares, price FROM trades ORDER BY id DESC LIMIT ?", (n,))
    rows = c.fetchall()
    if not rows:
        return "No trades yet."
    return "\n".join(f"{t}  {side.upper()} {shares:g} {sym} @ ${price:,.2f}" for t, sym, side, shares, price in rows)


class LinkExtractor(HTMLParser):
    """Very small HTML parser to extract titles/snippets from DuckDuckGo's simple HTML result page.
    This is intentionally forgiving rather than strictly tied to exact tag/class combinations.
    """
    def __init__(self):
        super().__init__()
        self.results = []
        self._capture = None
        self._current = {"title": "", "snippet": ""}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._capture = "title"
            self._current["title"] = ""
        elif tag in ("a", "div", "span") and "result__snippet" in cls:
            self._capture = "snippet"
            self._current["snippet"] = ""

    def handle_data(self, data):
        if not self._capture:
            return
        self._current[self._capture] += data

    def handle_endtag(self, tag):
        if self._capture:
            self._capture = None
            if self._current.get("title") or self._current.get("snippet"):
                title = self._current.get("title", "").strip()
                snippet = self._current.get("snippet", "").strip()
                if title or snippet:
                    self.results.append({"title": title or "(no title)", "snippet": snippet})
                self._current = {"title": "", "snippet": ""}


def research_topic(topic):
    try:
        r = requests.get(f"https://duckduckgo.com/html/?q={requests.utils.quote(topic)}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        parser = LinkExtractor()
        parser.feed(r.text)
        return parser.results[:5]
    except Exception:
        return []


def learn(conn, topic):
    print(f"Jimmy is researching: {topic}...")
    results = research_topic(topic)
    if not results:
        print("Jimmy could not find anything on that topic.")
        return 0

    learned_count = 0
    for item in results:
        if item.get("snippet"):
            save_knowledge(conn, topic, item["snippet"], item.get("title", "unknown"))
            learned_count += 1

    print(f"Jimmy learned {learned_count} new facts about '{topic}'.")
    if learned_count:
        print("Here is a summary of what Jimmy found:\n")
        for item in results:
            if item.get("snippet"):
                print(f"- {item['snippet']} (source: {item.get('title', 'unknown')})")
    return learned_count


def show_knowledge(conn, topic):
    facts = recall_knowledge(conn, topic)
    if not facts:
        print(f"Jimmy does not know anything about '{topic}' yet. Try: learn {topic}")
        return
    print(f"\nHere is what Jimmy remembers about '{topic}':\n")
    for fact, source, ts in facts:
        print(f"- {fact} (source: {source})")


# ---- conversational layer ----
GREETINGS = ("hi", "hello", "hey", "yo", "sup", "what's up", "whats up", "howdy")
THANKS = ("thanks", "thank you", "thx", "ty")


def chat(conn, q):
    """Free-form conversation. Uses saved knowledge when relevant, otherwise responds naturally."""
    ql = q.lower().strip()
    # greetings
    if any(ql == g or ql.startswith(g + " ") or ql.startswith(g + "!") for g in GREETINGS):
        return random.choice([
            "Hey! I'm here. What are we getting into?",
            "Hi there! Ready to learn something or make a trade?",
            "Yo! Jimmy's online. Ask me anything.",
        ])
    if any(t in ql for t in THANKS):
        return "Anytime. That's what I'm here for."
    if "how are you" in ql or "how're you" in ql:
        return "Running smooth and getting smarter every conversation. How about you?"
    if "your name" in ql or "who are you" in ql:
        return "I'm Jimmy — your learning agent, conversationalist, and paper trader."
    if "what can you do" in ql or "help" in ql or ql == "?":
        return ("I can chat, research and remember topics, and run a paper portfolio. "
                "Try: learn <topic>, what do you know about <topic>, buy/sell, portfolio, trades, topics.")

    # try to answer from memory
    # pick likely topic words
    words = re.findall(r"[a-zA-Z]{4,}", ql)
    for w in words:
        facts = recall_knowledge(conn, w)
        if facts:
            fact, source, _ = facts[0]
            return f"From what I've learned: {fact} (source: {source})"

    # nothing stored — offer to learn
    return (f"I don't have that stored yet. Want me to look it up? "
            f"Just say 'learn {q}'.")


def parse_trade(q):
    """Return (symbol, side, shares) or None."""
    m = re.search(r"(buy|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([a-zA-Z]{1,5})",
                  q, re.I)
    if not m:
        return None
    side = m.group(1).lower()
    shares = float(m.group(2))
    symbol = m.group(3).upper()
    return symbol, side, shares


def main():
    conn = init_db()
    print("\n=== Jimmy is online ===")
    print("Commands:")
    print("  learn <topic>                 -> research & remember a topic")
    print("  what do you know about <topic> -> recall saved knowledge")
    print("  topics                        -> list learned topics")
    print("  buy/sell <n> <SYMBOL>         -> paper trade")
    print("  portfolio                     -> show cash + holdings")
    print("  trades                        -> recent trades")
    print("  (or just talk to me)          -> free conversation")
    print("  exit                          -> quit\n")

    try:
        while True:
            try:
                q = input("You: ").strip()
            except EOFError:
                break
            if not q:
                continue
            ql = q.lower()

            if ql == "exit" or ql in ("quit", "bye"):
                print("Jimmy: Catch you later!")
                break

            elif ql.startswith("learn "):
                topic = q[6:].strip()
                learned = learn(conn, topic)
                save_conversation(conn, f"learn {topic}", f"learned {learned} facts")

            elif ql.startswith("what do you know about "):
                topic = q[len("what do you know about "):].strip()
                show_knowledge(conn, topic)
                save_conversation(conn, f"what do you know about {topic}", "recalled knowledge")

            elif ql == "topics":
                topics = list_topics(conn)
                if not topics:
                    print("Jimmy hasn't learned any topics yet.")
                else:
                    print("Jimmy knows about these topics:\n")
                    for t in topics:
                        print(f"- {t}")
                save_conversation(conn, "topics", "listed topics")

            elif ql in ("portfolio", "holdings", "balance"):
                print(portfolio_summary(conn))
                save_conversation(conn, ql, "showed portfolio")

            elif ql in ("trades", "history"):
                print(recent_trades(conn))
                save_conversation(conn, ql, "showed trades")

            else:
                trade = parse_trade(q)
                if trade:
                    symbol, side, shares = trade
                    price, src = place_trade(conn, symbol, side, shares)
                    if price is None:
                        print(f"Jimmy: {src}")
                    else:
                        print(f"Jimmy: {side.upper()} {shares:g} {symbol} @ ${price:,.2f} ({src}).")
                        print(portfolio_summary(conn))
                    save_conversation(conn, q, f"{side} {shares} {symbol}")
                else:
                    reply = chat(conn, q)
                    print(f"Jimmy: {reply}")
                    save_conversation(conn, q, reply)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
