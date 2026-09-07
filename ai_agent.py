import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests, sqlite3, os
from datetime import datetime
from html.parser import HTMLParser

DB_PATH = os.path.expanduser("~/Desktop/AIAgent/jimmy_memory.db")

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
    def __init__(self):
        super().__init__()
        self.in_result = False
        self.in_snippet = False
        self.results = []
        self.current_title = ""
        self.current_snippet = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        if tag == "a" and cls == "result__a":
            self.in_result = True
            self.current_title = ""
        if tag == "a" and cls == "result__snippet":
            self.in_snippet = True
            self.current_snippet = ""

    def handle_data(self, data):
        if self.in_result:
            self.current_title += data
        if self.in_snippet:
            self.current_snippet += data

    def handle_endtag(self, tag):
        if tag == "a" and self.in_result:
            self.in_result = False
        if tag == "a" and self.in_snippet:
            self.in_snippet = False
            if self.current_title.strip():
                self.results.append({
                    "title": self.current_title.strip(),
                    "snippet": self.current_snippet.strip()
                })

def research_topic(topic):
    try:
        r = requests.get(f"https://duckduckgo.com/html/?q={topic}",
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        parser = LinkExtractor()
        parser.feed(r.text)
        return parser.results[:5]
    except Exception as e:
        return []

def learn(conn, topic):
    print(f"Jimmy is researching: {topic}...")
    results = research_topic(topic)
    if not results:
        print("Jimmy could not find anything on that topic.")
        return

    learned_count = 0
    for item in results:
        if item["snippet"]:
            save_knowledge(conn, topic, item["snippet"], item["title"])
            learned_count += 1

    print(f"Jimmy learned {learned_count} new facts about '{topic}'.")
    print("Here is a summary of what Jimmy found:\n")
    for item in results:
        if item["snippet"]:
            print(f"- {item['snippet']} (source: {item['title']})")

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

    while True:
        q = input("You: ").strip()
        if not q:
            continue
        ql = q.lower()

        if ql == "exit":
            break

        elif ql.startswith("learn "):
            topic = q[6:].strip()
            learn(conn, topic)
            save_con

