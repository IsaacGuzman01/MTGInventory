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



