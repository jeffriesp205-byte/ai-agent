import subprocess, sys
# install requests if missing
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests, sqlite3, os
from datetime import datetime
from html.parser import HTMLParser

# Database path: default to a file in the user's home directory
DB_PATH = os.path.expanduser("~/.jimmy_memory.db")


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
        # Titles often use 'result__a' class; snippets may be in a span/div with 'result__snippet' or similar
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
        # end of a result entry: when we finish a snippet, treat that as one result if title exists
        if self._capture:
            self._capture = None
            if self._current.get("title") or self._current.get("snippet"):
                # only append if we have something meaningful
                title = self._current.get("title", "").strip()
                snippet = self._current.get("snippet", "").strip()
                if title or snippet:
                    self.results.append({"title": title or "(no title)", "snippet": snippet})
                self._current = {"title": "", "snippet": ""}


def research_topic(topic):
    try:
        # DuckDuckGo's HTML endpoint works reasonably for simple scraping
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


def main():
    conn = init_db()
    print("\n=== Jimmy is online ===")
    print("Commands:")
    print("  learn <topic>      -> Jimmy researches and remembers a topic")
    print("  what do you know about <topic>  -> Jimmy recalls saved knowledge")
    print("  topics             -> list everything Jimmy has learned about")
    print("  exit               -> quit\n")

    try:
        while True:
            try:
                q = input("You: ").strip()
            except EOFError:
                break
            if not q:
                continue
            ql = q.lower()

            if ql == "exit":
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

            else:
                print("I didn't understand that command. Try: learn <topic>, what do you know about <topic>, topics, or exit")

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
