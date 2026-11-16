"""Met à jour data/history.json.
- Cartes non gradées : prix Cardmarket (EUR) via TCGdex, cartes en français.
- Cartes gradées : ventes réussies saisies à la main dans data/ventes_gradees.csv."""
import csv
import datetime as dt
import json
import os
import re
import statistics

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_PATH = os.path.join(ROOT, "data", "history.json")
CSV_PATH = os.path.join(ROOT, "data", "ventes_gradees.csv")
TODAY = dt.date.today().isoformat()

wl = json.load(open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8"))
hist = json.load(open(HIST_PATH, encoding="utf-8")) if os.path.exists(HIST_PATH) else {}
hist.pop("fx_usd_eur", None)
hist.setdefault("items", {})


def slug(text):
    return re.sub(r"\W+", "-", text.lower()).strip("-")


# --- Cartes non gradées : TCGdex (Cardmarket, en euros) ---
for c in wl.get("raw", []):
    try:
        r = requests.get(f"https://api.tcgdex.net/v2/fr/cards/{c['id']}", timeout=60)
        r.raise_for_status()
        cm = (r.json().get("pricing") or {}).get("cardmarket") or {}
        price = cm.get("trend") or cm.get("avg")
        if not price:
            print("Pas de prix Cardmarket pour", c["id"])
            continue
        item = hist["items"].setdefault(f"raw:{c['id']}", {"series": []})
        item.update(label=c["label"], kind="raw", below=c.get("below"), above=c.get("above"))
        item["series"] = [p for p in item["series"] if p[0] != TODAY] + [[TODAY, round(price, 2)]]
    except Exception as e:
        print("Échec", c["id"], e)

# --- Cartes gradées : ventes réussies saisies dans le CSV ---
alerts = {(c["label"], c["grade"]): c for c in wl.get("graded", [])}
sales = {}
if os.path.exists(CSV_PATH):
    lines = open(CSV_PATH, encoding="utf-8-sig").read().splitlines()
    if lines:
        delim = ";" if lines[0].count(";") else ","
        for row in csv.DictReader(lines, delimiter=delim):
            try:
                carte, grade = row["carte"].strip(), row["grade"].strip()
                date = dt.date.fromisoformat(row["date"].strip()).isoformat()
                price = float(row["prix_eur"].strip().replace(",", "."))
            except Exception:
                print("Ligne ignorée :", row)
                continue
            sales.setdefault((carte, grade), {}).setdefault(date, []).append(price)

for (carte, grade), days in sales.items():
    c = alerts.get((carte, grade), {})
    item = hist["items"].setdefault(f"graded:{slug(carte + ' ' + grade)}", {"series": []})
    item.update(label=f"{carte} — {grade}", kind="graded", below=c.get("below"), above=c.get("above"))
    item["series"] = [[d, round(statistics.median(v), 2)] for d, v in sorted(days.items())]

os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
json.dump(hist, open(HIST_PATH, "w", encoding="utf-8"), ensure_ascii=False)
