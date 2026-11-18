"""Project paths, seasons and the shared-venue mapping."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"

FIRST_SEASON = 2014
LAST_SEASON = 2026

# Venues used by both championships. Key -> (display name, Jolpica circuitId, MotoGP circuit name)
VENUES = {
    "cota": ("Circuit of the Americas", "americas", "Circuit Of The Americas"),
    "silverstone": ("Silverstone", "silverstone", "Silverstone Circuit"),
    "red_bull_ring": ("Red Bull Ring", "red_bull_ring", "Red Bull Ring - Spielberg"),
    "barcelona": ("Barcelona-Catalunya", "catalunya", "Circuit de Barcelona-Catalunya"),
    "lusail": ("Lusail (Qatar)", "losail", "Lusail International Circuit"),
    "sepang": ("Sepang", "sepang", "Petronas Sepang International Circuit"),
    "mugello": ("Mugello", "mugello", "Autodromo Internazionale del Mugello"),
    "portimao": ("Portimão", "portimao", "Autódromo Internacional do Algarve"),
}

# Two layouts are treated as the same when their data-derived lap lengths agree within this
# (0.25 % is ~13 m on a 5 km lap: tight enough to separate e.g. F1's 2021-22 Barcelona chicane
# layout, 4.675 km, from MotoGP's 4.655 km).
SAME_LAYOUT_TOLERANCE = 0.0025
