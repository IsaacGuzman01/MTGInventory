# MTG Inventory CLI

A command-line tool for tracking your Magic: The Gathering card collection
in a local SQLite database. Card data (set, rarity, oracle text, current
market price) is auto-fetched from the free [Scryfall API](https://scryfall.com/docs/api)
when you add a card — you just type the name.

## Setup

Requires Python 3.8+ and the `requests` library.

```bash
pip install requests
```

The database is a single file at `~/.mtg_inventory.db`, created
automatically the first time you run a command. No server or config needed.

## Usage

**Add cards** (auto-fetches card data from Scryfall by name; fuzzy matching
means small typos are fine):

```bash
python cli.py add "Lightning Bolt" --set lea --qty 4 --condition NM
python cli.py add "Sol Ring" --foil
python cli.py add "sol ring" --set cmr --qty 2 --condition LP
```

- `--set` — restrict to a specific set (3-letter code, e.g. `lea`, `znr`). Omit to get Scryfall's default/most recent printing.
- `--qty` — how many copies (default 1)
- `--condition` — one of `M NM LP MP HP DMG` (default `NM`)
- `--foil` — mark as foil
- `--lang` — language code (default `en`)
- `--notes` — free-text notes

Adding the same printing/condition/foil/language again **stacks the
quantity** onto the existing row rather than creating a duplicate.

**List your collection:**

```bash
python cli.py list
python cli.py list --name bolt
python cli.py list --set lea
```

**Remove cards** (by the inventory row id shown in `list`):

```bash
python cli.py remove 3 --qty 1
```

Removing more than you have deletes the row entirely.

**Look up set codes/names** (useful when you need the right `--set` code for `add`):

```bash
python cli.py sets
python cli.py sets --name commander
```

Lists code, release date, set type, and full name, newest first.

**Refresh prices** for everything already in your database:

```bash
python cli.py update-prices
```

**See summary stats** (total cards, unique printings, estimated value):

```bash
python cli.py stats
```

**Export to CSV:**

```bash
python cli.py export collection.csv
```

## Files

- `db.py` — SQLite schema and all database operations
- `scryfall.py` — thin wrapper around the Scryfall API
- `cli.py` — command-line interface (argparse)
- `test_flow.py` — offline sanity test using mocked card data (no network needed): `python test_flow.py`

## Schema

Two tables:

- **`cards`** — one row per unique printing (Scryfall id), caching the
  catalog data: name, set, rarity, oracle text, prices, etc.
- **`inventory`** — one row per stack you own (a printing + condition +
  foil + language combination), with quantity and notes.

Splitting these lets you refresh prices/oracle text without touching your
ownership records, and keeps distinct conditions/foils of the same card as
separate, trackable stacks.

## Ideas for extending this

- Track individual sale/purchase prices and dates for a running P&L
- Add a `decks` table + `deck_cards` join table to track which cards are in which decks
- Add a `--json` output mode to `list` for piping into other tools
- Swap the price source to also pull EUR/TCGplayer market prices (Scryfall includes both)
