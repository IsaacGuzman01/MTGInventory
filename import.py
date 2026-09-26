import argparse
import csv
import sqlite3
import sys
import time 

import db 
import scryfall

CONDITION_ALIASES = {
        "mint": "M",
        "m": "M",
        "near mint": "NM",
        "near_mint": "NM",
        "nm": "NM",
        "lightly played": "LP",
        "lightly_played": "LP",
        "lp": "LP",
        "moderately played": "MP",
        "moderately_played": "MP",
        "mp": "MP",
        "heavily played": "HP",
        "heavily_played": "HP",
        "hp": "HP",
        "damaged": "DMG",
        "dmg": "DMG",

        }

def normalize_condition(raw: str) -> str:
    if not raw:
        return "NM:"
    return CONDITION_ALIASES.get(raw.strip().lower, raw.strip().upper())

def is_foil(raw: str) -> bool:
    if not raw:
        return False
    return "foil" in raw.strip().lower() and "non" not in raw.strip().lower()


def import_row(conn, row:dict, row_num:int, verbose: bool = True):
    """Process one CSV row then returns true on success or false on failure"""
    scryfall_id = (row.get("Scryfall ID")or "").strip()
    name = (row.get("Name") or "").strip()
    set_code = (row.get("Set code") or "").strip()

    try:
        qty = int(float(row.get("Quantity") or 1))
    except ValueError:
        qty = 1
    condition = normalize_condition(row.get("Condition"))
    foil = is_foil(row.get("Foil"))
    language = (row.get("Language") or "en").strip() or "en"

    if qty <=0:
        return True

    try:
        if scryfall_id:
            data = scryfall.fetch_card_by_scryfall_id(scryfall_id)
        elif name:
            data = scryfall.fetch_card_by_name(name, set_code=set_code or None)
        else:
            print(f"  [row {row_num}] skipped: no Scryfall ID or Name present", file=sys.stderr)
            return False
    except scryfall.CardNotFoundError as e:
        print(f"  [row {row_num}] not found ({name or scryfall_id}): {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [row {row_num}] error fetching {name or scryfall_id}: {e}", file=sys.stderr)
        return False
 
    card_row = scryfall.to_card_row(data)
    db.upsert_card(conn, card_row)
    existing = db.find_matching_inventory_row(
        conn, card_row["scryfall_id"], condition, foil, language
    )
    if existing:
        db.increment_inventory_row(conn, existing["id"], qty)
        new_qty = existing["quantity"] + qty
        if verbose:
            print(f"  [row {row_num}] stacked: {card_row['name']} "
                  f"[{card_row['set_code'].upper()}] qty now {new_qty}")
    else:
        db.add_inventory_row(conn, card_row["scryfall_id"], qty, condition, foil, language)
        if verbose:
            print(f"  [row {row_num}] added: {qty}x {card_row['name']} "
                  f"[{card_row['set_code'].upper()}] ({condition}{', foil' if foil else ''})")
    return True
 
 
def main():
    parser = argparse.ArgumentParser(
        description="Import a ManaBox collection CSV export into the mtg-inventory database."
    )
    parser.add_argument("csv_path", help="Path to the ManaBox CSV export")
    parser.add_argument("--dry-run", action="store_true",
                         help="Parse and look up cards but don't write to the database")
    parser.add_argument("--errors-out", default=None,
                         help="Write failed rows to this CSV so you can fix and retry them")
    parser.add_argument("--quiet", action="store_true", help="Only print the summary at the end")
    parser.add_argument("--db-path", default=None,
                         help="Path to the inventory database (default: ~/.mtg_inventory.db). "
                              "Useful for testing an import against a scratch file first.")
    args = parser.parse_args()
    db_path = args.db_path or db.DEFAULT_DB_PATH
 
    try:
        with open(args.csv_path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        sys.exit(1)
 
    if not rows:
        print("CSV file has no data rows.")
        return
 
    required_any = {"Name", "Scryfall ID"}
    if not required_any & set(rows[0].keys()):
        print(
            "This doesn't look like a ManaBox export -- expected a 'Name' or "
            "'Scryfall ID' column. Found columns: " + ", ".join(rows[0].keys()),
            file=sys.stderr,
        )
        sys.exit(1)
 
    db.init_db(db_path)
    start = time.time()
    succeeded = 0
    failed_rows = []
 
    if args.dry_run:
        print(f"[dry run] would process {len(rows)} row(s), no changes will be written.\n")
 
    # db.get_conn() always commits on exit, which would defeat --dry-run, so
    # for a dry run we open our own connection and simply never commit --
    # closing an sqlite3 connection with uncommitted changes discards them.
    if args.dry_run:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            for i, row in enumerate(rows, start=1):
                ok = import_row(conn, row, i, verbose=not args.quiet)
                succeeded += 1 if ok else 0
                if not ok:
                    failed_rows.append(row)
        finally:
            conn.close()  # no commit -- all changes made during the dry run are discarded
    else:
        with db.get_conn(db_path) as conn:
            for i, row in enumerate(rows, start=1):
                ok = import_row(conn, row, i, verbose=not args.quiet)
                succeeded += 1 if ok else 0
                if not ok:
                    failed_rows.append(row)
 
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s: {succeeded}/{len(rows)} row(s) imported "
          f"{'(dry run, nothing saved)' if args.dry_run else ''}, "
          f"{len(failed_rows)} failed.")
 
    if failed_rows and args.errors_out:
        with open(args.errors_out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(failed_rows)
        print(f"Failed rows written to {args.errors_out} for review/retry.")
 
 
if __name__ == "__main__":
    main()
