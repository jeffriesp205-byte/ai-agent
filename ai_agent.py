import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "-q"])
import requests
from bs4 import BeautifulSoup
print("\nAI Agent Ready!")
while True:
    q = input("Ask: ").strip()
    if q.lower() == "exit": break
    try:
        r = requests.get(f"https://duckduckgo.com/html/?q={q}", headers={"User-Agent": "Mozilla"}, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        for result in soup.find_all("div", class_="result")[:3]:
            t = result.find("a", class_="result__a")
            if t: print(f"- {t.get_text()}")
    except: print("Error searching")
