"""
MTG_Inventory: a command line tool for tracking your Magic the gathering bulk collection in a local database (SQLite), with card data autofetched from Scryfall.

Examples:
    python cli.py add "Lightning Bolt" --set lea --qty 4 --condition NM
    python cli.py add "Sol Ring" --foil
    python cli.py list
    python cli.py list --name bolt
    python cli.py remove 3 --qty 1
    python cli.py update-prices
    python cli.py stats
    python cli.py export collection.csv
"""

import argparse
import csv
import sys

import db 
import scryfall 

BANNER = r"""
 __  __ _____ ____   ___ _   ___     _______ _   _ _____ ___  ______   __
|  \/  |_   _/ ___| |_ _| \ | \ \   / / ____| \ | |_   _/ _ \|  _ \ \ / /
| |\/| | | || |  _   | ||  \| |\ \ / /|  _| |  \| | | || | | | |_) \ V / 
| |  | | | || |_| |  | || |\  | \ V / | |___| |\  | | || |_| |  _ < | |  
|_|  |_| |_| \____| |___|_| \_|  \_/  |_____|_| \_| |_| \___/|_| \_\|_|  
"""
def cmd_add(args):
    db.init_db()
    try:
        data = scryfall.fetch_card_by_name(args.name, set_code=args.set)
    except scryfall.CardNotFoundError as e:
        print(f"Card not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error contacting Scryfall: {e}", file=sys.stderr)
        sys.exit(1)
 
    row = scryfall.to_card_row(data)
    with db.get_conn() as conn:
        db.upsert_card(conn, row)
        existing = db.find_matching_inventory_row(
            conn, row["scryfall_id"], args.condition, args.foil, args.lang
        )
        if existing:
            db.increment_inventory_row(conn, existing["id"], args.qty)
            inv_id = existing["id"]
            new_qty = existing["quantity"] + args.qty
            print(
                f"Updated existing stack (id {inv_id}): {row['name']} "
                f"[{row['set_code'].upper()}] now at qty {new_qty}"
            )
        else:
            inv_id = db.add_inventory_row(
                conn, row["scryfall_id"], args.qty, args.condition,
                args.foil, args.lang, args.notes
            )
            print(
                f"Added (inventory id {inv_id}): {args.qty}x {row['name']} "
                f"[{row['set_code'].upper()}] ({args.condition}"
                f"{', foil' if args.foil else ''})"
            )
 
 
def cmd_list(args):
    db.init_db()
    with db.get_conn() as conn:
        rows = db.list_inventory(conn, name_filter=args.name, set_filter=args.set)
    if not rows:
        print("No matching cards in inventory.")
        return
    header = f"{'ID':<5} {'QTY':<4} {'NAME':<30} {'SET':<6} {'COND':<5} {'FOIL':<5} {'PRICE':<8}"
    print(BANNER)
    print(header)
    print("-" * len(header))
    for r in rows:
        price = r["price_usd_foil"] if r["foil"] and r["price_usd_foil"] else r["price_usd"]
        price_str = f"${price:.2f}" if price is not None else "n/a"
        print(
            f"{r['inventory_id']:<5} {r['quantity']:<4} {r['name'][:30]:<30} "
            f"{r['set_code'].upper():<6} {r['condition']:<5} "
            f"{'yes' if r['foil'] else 'no':<5} {price_str:<8}"
        )
 
 
def cmd_remove(args):
    db.init_db()
    with db.get_conn() as conn:
        result = db.remove_quantity(conn, args.inventory_id, args.qty)
    if result is None:
        print(f"No inventory row with id {args.inventory_id}", file=sys.stderr)
        sys.exit(1)
    elif result == 0:
        print(f"Removed inventory row {args.inventory_id} entirely.")
    else:
        print(f"Inventory row {args.inventory_id} now at quantity {result}.")
 
 
def cmd_update_prices(args):
    db.init_db()
    with db.get_conn() as conn:
        ids = db.all_scryfall_ids(conn)
        print(f"Refreshing prices/data for {len(ids)} card(s)...")
        for i, sid in enumerate(ids, 1):
            try:
                data = scryfall.fetch_card_by_scryfall_id(sid)
                row = scryfall.to_card_row(data)
                db.upsert_card(conn, row)
            except Exception as e:
                print(f"  [{i}/{len(ids)}] failed for {sid}: {e}", file=sys.stderr)
                continue
        print("Done.")
 
 
def cmd_stats(args):
    db.init_db()
    with db.get_conn() as conn:
        s = db.get_stats(conn)
    print(f"Total cards owned:     {s['total_cards']}")
    print(f"Unique printings:      {s['unique_printings']}")
    print(f"Estimated total value: ${s['total_value_usd']:.2f}")
 
 
def cmd_sets(args):
    try:
        sets = scryfall.fetch_all_sets()
    except Exception as e:
        print(f"Error contacting Scryfall: {e}", file=sys.stderr)
        sys.exit(1)
 
    if args.name:
        needle = args.name.lower()
        sets = [s for s in sets if needle in s.get("name", "").lower()]
 
    if not sets:
        print("No matching sets.")
        return
 
    # Most recent releases first.
    sets.sort(key=lambda s: s.get("released_at") or "", reverse=True)
 
    header = f"{'CODE':<8} {'RELEASED':<12} {'TYPE':<14} {'NAME'}"
    print(header)
    print("-" * len(header))
    for s in sets:
        print(
            f"{s.get('code', '').upper():<8} "
            f"{s.get('released_at') or 'n/a':<12} "
            f"{s.get('set_type', ''):<14} "
            f"{s.get('name', '')}"
        )
    print(f"\n{len(sets)} set(s).")
 
 
def cmd_export(args):
    db.init_db()
    with db.get_conn() as conn:
        rows = db.list_inventory(conn)
    if not rows:
        print("Nothing to export.")
        return
    fieldnames = rows[0].keys()
    with open(args.path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    print(f"Exported {len(rows)} row(s) to {args.path}")
 
 
def build_parser():
    parser = argparse.ArgumentParser(
        prog="mtg-inventory", description="Track your MTG card collection."
    )
    sub = parser.add_subparsers(dest="command", required=True)
 
    p_add = sub.add_parser("add", help="Add card(s) to your inventory")
    p_add.add_argument("name", help="Card name (fuzzy-matched via Scryfall)")
    p_add.add_argument("--set", help="Set code, e.g. lea, znr (optional)")
    p_add.add_argument("--qty", type=int, default=1, help="Quantity to add (default 1)")
    p_add.add_argument("--condition", default="NM",
                        choices=["M", "NM", "LP", "MP", "HP", "DMG"],
                        help="Card condition (default NM)")
    p_add.add_argument("--foil", action="store_true", help="Mark as foil")
    p_add.add_argument("--lang", default="en", help="Language code (default en)")
    p_add.add_argument("--notes", default=None, help="Free-text notes")
    p_add.set_defaults(func=cmd_add)
 
    p_list = sub.add_parser("list", help="List cards in your inventory")
    p_list.add_argument("--name", default=None, help="Filter by name substring")
    p_list.add_argument("--set", default=None, help="Filter by set code")
    p_list.set_defaults(func=cmd_list)
 
    p_remove = sub.add_parser("remove", help="Remove quantity from an inventory row")
    p_remove.add_argument("inventory_id", type=int, help="Inventory row id (see `list`)")
    p_remove.add_argument("--qty", type=int, default=1, help="Quantity to remove (default 1)")
    p_remove.set_defaults(func=cmd_remove)
 
    p_prices = sub.add_parser("update-prices", help="Refresh cached prices from Scryfall")
    p_prices.set_defaults(func=cmd_update_prices)
 
    p_sets = sub.add_parser("sets", help="List Magic set codes/names (from Scryfall)")
    p_sets.add_argument("--name", default=None,
                         help="Filter by set name substring, e.g. 'commander'")
    p_sets.set_defaults(func=cmd_sets)
 
    p_stats = sub.add_parser("stats", help="Show summary stats")
    p_stats.set_defaults(func=cmd_stats)
 
    p_export = sub.add_parser("export", help="Export inventory to CSV")
    p_export.add_argument("path", help="Output CSV file path")
    p_export.set_defaults(func=cmd_export)
 
    return parser
 
 
def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        print(BANNER)
        parser.print_help()
        return
    args = parser.parse_args()
    args.func(args)
    
 
if __name__ == "__main__":
    main()
 

def cmd_add(args):
    db.init
