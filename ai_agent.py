import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests, sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.expanduser("~/Desktop/AIAgent/agent_memory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        question TEXT,
        answer TEXT
    )""")
    conn.commit()
    return conn

def save_memory(conn, question, answer):
    c = conn.cursor()
    c.execute("INSERT INTO conversations (timestamp, question, answer) VALUES (?, ?, ?)",
              (datetime.now().isoformat(), question, answer))
    conn.commit()

def get_crypto_price(symbol):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
        r = requests.get(url, timeout=5)
        data = r.json()
        if symbol in data:
            return f"{symbol.upper()} is currently trading at ${data[symbol]['usd']}"
        return None
    except:
        return None

def get_stock_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return f"{symbol.upper()} is currently trading at ${price}"
    except:
        return None

CRYPTO_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "xrp": "ripple", "ripple": "ripple",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano"
}

def answer_question(q):
    ql = q.lower()

    for name, cg_id in CRYPTO_MAP.items():
        if name in ql and ("price" in ql or "worth" in ql or "cost" in ql or "trading" in ql):
            result = get_crypto_price(cg_id)
            if result:
                return result

    words = q.replace("?", "").split()
    for w in words:
        if w.isupper() and 1 < len(w) <= 5:
            result = get_stock_price(w)
            if result:
                return result

    if "price" in ql or "stock" in ql:
        for w in words:
            clean = w.strip(".,!?").upper()
            if clean.isalpha() and 1 < len(clean) <= 5:
                result = get_stock_price(clean)
                if result:
                    return result

    return None

def web_search_fallback(q):
    try:
        r = requests.get(f"https://duckduckgo.com/html/?q={q}",
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        from html.parser import HTMLParser

        class LinkExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_result = False
                self.results = []
                self.current = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and attrs_dict.get("class") == "result__a":
                    self.in_result = True
                    self.current = ""

            def handle_data(self, data):
                if self.in_result:
                    self.current += data

            def handle_endtag(self, tag):
                if tag == "a" and self.in_result:
                    self.in_result = False
                    if self.current.strip():
                        self.results.append(self.current.strip())

        parser = LinkExtractor()
        parser.feed(r.text)
        return parser.results[:3]
    except:
        return []

def main():
    conn = init_db()
    print("\nAI Agent Ready! (now with price lookups and memory)")
    print("Type exit to quit.\n")

    while True:
        q = input("Ask: ").strip()
        if q.lower() == "exit":
            break
        if not q:
            continue

        direct_answer = answer_question(q)

        if direct_answer:
            print(f"-> {direct_answer}")
            save_memory(conn, q, direct_answer)
        else:
            results = web_search_fallback(q)
            if results:
                answer_text = " | ".join(results)
                print("Top results:")
                for r in results:
                    print(f"- {r}")
                save_memory(conn, q, answer_text)
            else:
                print("Sorry, could not find an answer.")
                save_memory(conn, q, "NO ANSWER FOUND")

    conn.close()
    print("Goodbye!")

if __name__ == "__main__":
    main()
