"""Met à jour data/history.json : prix Cardmarket (EUR) pour les cartes non gradées,
prix eBay PSA (USD, convertis en EUR) pour les cartes gradées."""
import datetime as dt
import json
import os
import re

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_PATH = os.path.join(ROOT, "data", "history.json")
TODAY = dt.date.today().isoformat()

wl = json.load(open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8"))
hist = json.load(open(HIST_PATH, encoding="utf-8")) if os.path.exists(HIST_PATH) else {}
hist.setdefault("fx_usd_eur", None)
hist.setdefault("items", {})


def put(key, label, kind, price, c):
    item = hist["items"].setdefault(key, {"series": []})
    item.update(label=label, kind=kind, below=c.get("below"), above=c.get("above"))
    item["series"] = [p for p in item["series"] if p[0] != TODAY] + [[TODAY, round(price, 2)]]


# --- Cartes non gradées : pokemontcg.io (Cardmarket, en euros) ---
headers = {"X-Api-Key": os.environ["POKEMONTCG_KEY"]} if os.environ.get("POKEMONTCG_KEY") else {}
for c in wl["raw"]:
    try:
        r = requests.get(f"https://api.pokemontcg.io/v2/cards/{c['id']}", headers=headers, timeout=60)
        r.raise_for_status()
        p = r.json()["data"]["cardmarket"]["prices"]
        price = p.get("trendPrice") or p.get("averageSellPrice")
        if price:
            put(f"raw:{c['id']}", c["label"], "raw", price, c)
        else:
            print("Pas de prix pour", c["id"])
    except Exception as e:
        print("Échec", c["id"], e)

# --- Taux de change USD -> EUR ---
try:
    r = requests.get("https://api.frankfurter.dev/v1/latest",
                     params={"base": "USD", "symbols": "EUR"}, timeout=30)
    hist["fx_usd_eur"] = r.json()["rates"]["EUR"]
except Exception as e:
    print("Taux de change indisponible, on garde le dernier connu :", e)

# --- Cartes gradées : PokemonPriceTracker (eBay, en dollars) ---
PRICE_FIELDS = ("smartMarketPrice", "avg", "averagePrice", "medianPrice", "marketPrice")


def find_grade_price(node, n):
    """Cherche récursivement le prix du grade PSA n (le format exact de l'API est à confirmer)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if re.sub(r"[^a-z0-9]", "", k.lower()) in (f"psa{n}", f"g{n}", str(n)) and isinstance(v, dict):
                for f in PRICE_FIELDS:
                    if isinstance(v.get(f), (int, float)):
                        return v[f]
            found = find_grade_price(v, n)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = find_grade_price(v, n)
            if found is not None:
                return found
    return None


token, fx = os.environ.get("PPT_KEY"), hist["fx_usd_eur"]
if token and fx:
    for c in wl["graded"]:
        try:
            r = requests.get(
                "https://www.pokemonpricetracker.com/api/v2/cards",
                params={"tcgPlayerId": c["tcgPlayerId"], "includeEbay": "true", "days": 30},
                headers={"Authorization": f"Bearer {token}"}, timeout=60)
            r.raise_for_status()
            data = r.json()["data"]
            card = data[0] if isinstance(data, list) else data
            ebay = card.get("ebay") or {}
            usd = find_grade_price(ebay, int(re.search(r"\d+", c["grade"]).group()))
            if usd:
                put(f"psa:{c['tcgPlayerId']}:{c['grade']}", f"{c['label']} — {c['grade']}",
                    "graded", usd * fx, c)
            else:
                print("Prix introuvable pour", c["label"], c["grade"], "(voir data/debug_ebay.json)")
                json.dump(ebay, open(os.path.join(ROOT, "data", "debug_ebay.json"), "w"), indent=1)
        except Exception as e:
            print("Échec", c["label"], c["grade"], e)
else:
    print("Cartes gradées ignorées : clé PPT_KEY ou taux de change manquant.")

os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
json.dump(hist, open(HIST_PATH, "w", encoding="utf-8"), ensure_ascii=False)
