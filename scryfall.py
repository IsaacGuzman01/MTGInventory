"""
Thin wrapper around the Scryfall API (https://scryfall.com/docs/api).
 
Scryfall asks that clients:
- Set a descriptive User-Agent and Accept header
- Keep requests to roughly 5-10 per second (we sleep briefly between calls)
No API key is required.
"""
 
import time
import requests
 
BASE_URL = "https://api.scryfall.com"
HEADERS = {
    "User-Agent": "MTGInventoryCLI/1.0 (personal collection tracker)",
    "Accept": "application/json",
}
# Be polite to Scryfall's servers between successive requests.
REQUEST_DELAY_SECONDS = 0.1
 
 
class CardNotFoundError(Exception):
    pass
 
 
def _get(path: str, params: dict = None):
    resp = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
    time.sleep(REQUEST_DELAY_SECONDS)
    if resp.status_code == 404:
        raise CardNotFoundError(resp.json().get("details", "Card not found"))
    resp.raise_for_status()
    return resp.json()
 
 
def fetch_card_by_name(name: str, set_code: str = None) -> dict:
    """Fuzzy-match a card by name via Scryfall's /cards/named endpoint,
    optionally constrained to a specific set."""
    params = {"fuzzy": name}
    if set_code:
        params["set"] = set_code.lower()
    return _get("/cards/named", params=params)
 
 
def fetch_card_by_scryfall_id(scryfall_id: str) -> dict:
    return _get(f"/cards/{scryfall_id}")
 
 
def fetch_all_sets() -> list:
    """Fetch the full list of Magic sets from Scryfall's /sets endpoint.
    Returns a list of dicts with (at least) 'code', 'name', 'set_type',
    and 'released_at'. This endpoint is a single call (not paginated)."""
    data = _get("/sets")
    return data.get("data", [])
 
 
def to_card_row(data: dict) -> dict:
    """Convert a Scryfall card JSON object into the flat dict our db layer expects."""
    prices = data.get("prices", {}) or {}
    usd = prices.get("usd")
    usd_foil = prices.get("usd_foil")
    return {
        "scryfall_id": data["id"],
        "name": data["name"],
        "set_code": data.get("set", ""),
        "set_name": data.get("set_name", ""),
        "collector_number": data.get("collector_number", ""),
        "rarity": data.get("rarity", ""),
        "mana_cost": data.get("mana_cost", ""),
        "cmc": data.get("cmc", 0.0),
        "type_line": data.get("type_line", ""),
        "oracle_text": data.get("oracle_text", ""),
        "colors": ",".join(data.get("colors", []) or []),
        "image_url": (data.get("image_uris") or {}).get("normal", ""),
        "price_usd": float(usd) if usd else None,
        "price_usd_foil": float(usd_foil) if usd_foil else None,
    }
 
