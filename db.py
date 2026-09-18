"""
SQLit database layer for the inventory tracker

schema design:
    - 'cards' holds one row per unique printing (Scryfall id = a specific set + collector number + language variant of a card). This is the "catalog" data fetched from Scryfall and cached locally.
    - 'inventory' holds one row per physical stack of cards you own of a given printing (so you can have ex. 2 NM non-foil + LP foil of the same card as seperate rows, or just one row per printing if you prefer).

splitting these two allows us to refresh prices / oracle text for a card without touching your ownership records, and lets a single printing be referenced by multiple inventory rows (different conditions, foile vs non-foil, etc).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path 

DEFAULT_DB_PATH = Path.home() / ".mtg_inventory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    scryfall_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    set_code        TEXT NOT NULL,
    set_name        TEXT,
    collector_number TEXT,
    rarity          TEXT,
    mana_cost       TEXT,
    cmc             REAL,
    type_line       TEXT,
    oracle_text     TEXT,
    colors          TEXT,
    image_url       TEXT,
    price_usd       REAL,
    price_usd_foil  REAL,
    price_updated_at TEXT
);
 
CREATE TABLE IF NOT EXISTS inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scryfall_id     TEXT NOT NULL REFERENCES cards(scryfall_id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    condition       TEXT NOT NULL DEFAULT 'NM',
    foil            INTEGER NOT NULL DEFAULT 0,
    language        TEXT NOT NULL DEFAULT 'en',
    notes           TEXT,
    date_added      TEXT NOT NULL DEFAULT (datetime('now'))
);
 
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
CREATE INDEX IF NOT EXISTS idx_inventory_scryfall_id ON inventory(scryfall_id);
"""

@contextmanager
def get_conn(db_path: Path = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH):
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def upsert_card(conn, card: dict):
    """insert or refresh a card's catalog data (from Scryfall)."""
    conn.execute(
            """
            INSERT INTO cards (
                scryfall_id, name, set_code, set_name, collector_number,
                rarity, mana_cost, cmc, type_line, oracle_text, colors,
                image_url, price_usd, price_usd_foil, price_updated_at
            )VALUES (
                :scryfall_id,:name, :set_code, :set_name, :collector_number,
                 :rarity, :mana_cost, :cmc, :type_line, :oracle_text, :colors,
                :image_url, :price_usd, :price_usd_foil, datetime('now')
            )
            ON CONFLICT(scryfall_id) DO UPDATE SET
                name=excluded.name,
                set_code=excluded.set_code,
                set_name=excluded.set_name,
                collector_number=excluded.collector_number,
                rarity=excluded.rarity,
                mana_cost=excluded.mana_cost,
                cmc=excluded.cmc,
                type_line=excluded.type_line,
                oracle_text=excluded.oracle_text,
                colors=excluded.colors,
                image_url=excluded.image_url,
                price_usd=excluded.price_usd,
                price_usd_foil=excluded.price_usd_foil,
                price_updated_at=datetime('now')
            """,
            card,
        )

 
def add_inventory_row(conn, scryfall_id: str, quantity: int, condition: str,
                       foil: bool, language: str, notes: str = None):
    cur = conn.execute(
        """
        INSERT INTO inventory (scryfall_id, quantity, condition, foil, language, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (scryfall_id, quantity, condition, int(foil), language, notes),
    )
    return cur.lastrowid
 
 
def find_matching_inventory_row(conn, scryfall_id: str, condition: str,
                                 foil: bool, language: str):
    """Look for an existing inventory row with the same printing/condition/
    foil/language so repeated `add` calls stack quantity instead of creating
    duplicate rows."""
    row = conn.execute(
        """
        SELECT id, quantity FROM inventory
        WHERE scryfall_id = ? AND condition = ? AND foil = ? AND language = ?
        """,
        (scryfall_id, condition, int(foil), language),
    ).fetchone()
    return row
 
 
def increment_inventory_row(conn, row_id: int, quantity: int):
    conn.execute(
        "UPDATE inventory SET quantity = quantity + ? WHERE id = ?",
        (quantity, row_id),
    )
 
 
def list_inventory(conn, name_filter: str = None, set_filter: str = None):
    query = """
        SELECT
            inventory.id AS inventory_id,
            cards.name, cards.set_code, cards.set_name, cards.collector_number,
            cards.rarity, cards.price_usd, cards.price_usd_foil,
            inventory.quantity, inventory.condition, inventory.foil,
            inventory.language, inventory.notes
        FROM inventory
        JOIN cards ON cards.scryfall_id = inventory.scryfall_id
        WHERE 1=1
    """
    params = []
    if name_filter:
        query += " AND cards.name LIKE ?"
        params.append(f"%{name_filter}%")
    if set_filter:
        query += " AND cards.set_code = ?"
        params.append(set_filter.lower())
    query += " ORDER BY cards.name, cards.set_code"
    return conn.execute(query, params).fetchall()
 
 
def remove_quantity(conn, inventory_id: int, quantity: int):
    row = conn.execute(
        "SELECT quantity FROM inventory WHERE id = ?", (inventory_id,)
    ).fetchone()
    if row is None:
        return None
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        conn.execute("DELETE FROM inventory WHERE id = ?", (inventory_id,))
        return 0
    else:
        conn.execute(
            "UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, inventory_id)
        )
        return new_qty
 
 
def get_stats(conn):
    total_cards = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS n FROM inventory"
    ).fetchone()["n"]
    unique_printings = conn.execute(
        "SELECT COUNT(DISTINCT scryfall_id) AS n FROM inventory"
    ).fetchone()["n"]
    total_value = conn.execute(
        """
        SELECT COALESCE(SUM(
            inventory.quantity *
            CASE WHEN inventory.foil = 1
                 THEN COALESCE(cards.price_usd_foil, cards.price_usd, 0)
                 ELSE COALESCE(cards.price_usd, 0)
            END
        ), 0) AS v
        FROM inventory JOIN cards ON cards.scryfall_id = inventory.scryfall_id
        """
    ).fetchone()["v"]
    return {
        "total_cards": total_cards,
        "unique_printings": unique_printings,
        "total_value_usd": round(total_value, 2),
    }
 
 
def all_scryfall_ids(conn):
    return [r["scryfall_id"] for r in conn.execute("SELECT scryfall_id FROM cards").fetchall()]
