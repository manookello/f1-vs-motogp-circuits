"""Fetch Formula 1 (Jolpica-F1 API) and MotoGP (motogp.com results API) data, 2014-2026.

Both clients cache every response on disk, throttle requests and back off on 429/5xx. The cache
layout matches the companion projects, so you can point ``--f1-cache`` / ``--motogp-cache`` at an
existing cache (e.g. from ``f1-race-outcome-predictor`` / ``motogp-performance-analytics``) and
avoid downloading anything twice.

Usage::

    python -m f1_vs_motogp.data
    python -m f1_vs_motogp.data --f1-cache ../f1-race-outcome-predictor/data/raw/jolpica \\
        --motogp-cache ../motogp-performance-analytics/data/raw/motogp
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

from f1_vs_motogp.config import DATA_PROCESSED, DATA_RAW, FIRST_SEASON, LAST_SEASON

JOLPICA_URL = "https://api.jolpi.ca/ergast/f1"
MOTOGP_URL = "https://api.motogp.pulselive.com/motogp/v1/results"
USER_AGENT = "f1-vs-motogp-circuits/0.1 (open-source research)"


def lap_time_to_seconds(value) -> float | None:
    """'1:28.782' / '01:28.782' / '1:02:03.456' / '83.4' -> seconds."""
    if not value or not isinstance(value, str):
        return None
    try:
        parts = [float(p) for p in value.strip().split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _PoliteClient:
    def __init__(self, min_interval: float, max_retries: int = 6) -> None:
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0

    def _fetch(self, url: str, params: dict):
        for attempt in range(self.max_retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException:
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2 ** (attempt + 2))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Giving up on {url}")


class JolpicaClient(_PoliteClient):
    def __init__(self, cache_dir: Path = DATA_RAW / "jolpica") -> None:
        super().__init__(min_interval=1.0)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def races(self, path: str, refresh: bool = False) -> list[dict]:
        """All races (with nested results) for a paginated endpoint like ``2024/results``."""
        races, offset, stem = [], 0, path.strip("/").replace("/", "_")
        while True:
            cache = self.cache_dir / f"{stem}_{offset}.json"
            if cache.exists() and not refresh:
                payload = json.loads(cache.read_text(encoding="utf-8"))
            else:
                payload = self._fetch(
                    f"{JOLPICA_URL}/{path.strip('/')}/", {"limit": 100, "offset": offset}
                )
                cache.write_text(json.dumps(payload), encoding="utf-8")
            mr = payload["MRData"]
            races += mr["RaceTable"]["Races"]
            offset += 100
            if offset >= int(mr["total"]):
                return races


class MotoGPClient(_PoliteClient):
    def __init__(self, cache_dir: Path = DATA_RAW / "motogp") -> None:
        super().__init__(min_interval=0.5)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, path: str, params: dict | None = None, refresh: bool = False):
        params = params or {}
        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cache = self.cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.json"
        if cache.exists() and not refresh:
            return json.loads(cache.read_text(encoding="utf-8"))
        payload = self._fetch(f"{MOTOGP_URL}/{path}", params)
        cache.write_text(json.dumps(payload), encoding="utf-8")
        return payload


# --------------------------------------------------------------------------------------
# Formula 1
# --------------------------------------------------------------------------------------


def fetch_f1(start: int, end: int, client: JolpicaClient) -> dict[str, pd.DataFrame]:
    current = dt.date.today().year
    races, results, quali = [], [], []
    for season in range(start, end + 1):
        refresh = season >= current
        for race in client.races(f"{season}/results", refresh=refresh):
            key = {"series": "F1", "season": int(race["season"]), "round": int(race["round"])}
            races.append(
                {
                    **key,
                    "race_name": race["raceName"],
                    "date": race["date"],
                    "circuit_id": race["Circuit"]["circuitId"],
                    "circuit_name": race["Circuit"]["circuitName"],
                }
            )
            for r in race["Results"]:
                fl = r.get("FastestLap", {})
                drv = r["Driver"]
                results.append(
                    {
                        **key,
                        "competitor": drv["driverId"],
                        "competitor_name": f"{drv['givenName']} {drv['familyName']}",
                        "team": r["Constructor"]["name"],
                        "position": _num(r.get("position")),
                        "classified": r.get("positionText", "").isdigit(),
                        "points": _num(r.get("points")) or 0.0,
                        "laps": _num(r.get("laps")),
                        "race_time_s": (_num(r.get("Time", {}).get("millis")) or float("nan"))
                        / 1000,
                        "fastest_lap_s": lap_time_to_seconds(fl.get("Time", {}).get("time")),
                        "fastest_lap_kph": _num(fl.get("AverageSpeed", {}).get("speed")),
                    }
                )
        for race in client.races(f"{season}/qualifying", refresh=refresh):
            key = {"series": "F1", "season": int(race["season"]), "round": int(race["round"])}
            for q in race["QualifyingResults"]:
                times = [lap_time_to_seconds(q.get(s)) for s in ("Q1", "Q2", "Q3")]
                times = [t for t in times if t]
                quali.append(
                    {
                        **key,
                        "competitor": q["Driver"]["driverId"],
                        "position": _num(q.get("position")),
                        "best_lap_s": min(times) if times else None,
                    }
                )
        print(f"F1 {season} done", flush=True)
    races = pd.DataFrame(races).drop_duplicates(["season", "round"])
    return {
        "f1_races": races,
        "f1_results": pd.DataFrame(results).drop_duplicates(),
        "f1_quali": pd.DataFrame(quali).drop_duplicates(),
    }


# --------------------------------------------------------------------------------------
# MotoGP
# --------------------------------------------------------------------------------------


def _official(sessions: list[dict], stype: str, number: int | None = None) -> dict | None:
    hits = [
        s
        for s in sessions
        if s.get("type") == stype and (number is None or s.get("number") == number)
    ]
    return sorted(hits, key=lambda s: s.get("date") or "")[-1] if hits else None


def fetch_motogp(start: int, end: int, client: MotoGPClient) -> dict[str, pd.DataFrame]:
    current = dt.date.today().year
    year_to_id = {s["year"]: s["id"] for s in client.get("seasons", refresh=True)}
    races, results, quali = [], [], []
    for year in range(start, end + 1):
        events = (
            client.get(
                "events",
                {"seasonUuid": year_to_id[year], "isFinished": "true"},
                refresh=year >= current,
            )
            or []
        )
        events = sorted(
            (e for e in events if not e.get("test")), key=lambda e: e.get("date_start") or ""
        )
        for rnd, event in enumerate(events, start=1):
            cats = client.get("categories", {"eventUuid": event["id"]}) or []
            cat = next((c for c in cats if (c.get("name") or "").startswith("MotoGP")), None)
            if cat is None:
                continue
            sessions = (
                client.get("sessions", {"eventUuid": event["id"], "categoryUuid": cat["id"]}) or []
            )
            key = {"series": "MotoGP", "season": year, "round": rnd}
            race_sess = _official(sessions, "RAC")
            race_payload = (
                client.get(f"session/{race_sess['id']}/classification", {"test": "false"})
                if race_sess
                else None
            )
            if not race_payload or not race_payload.get("classification"):
                continue  # cancelled / no classification
            fastest = next(
                (r for r in race_payload.get("records") or [] if r.get("type") == "fastestLap"), {}
            )
            races.append(
                {
                    **key,
                    "race_name": event.get("name"),
                    "date": event.get("date_start"),
                    "circuit_id": (event.get("circuit") or {}).get("id"),
                    "circuit_name": (event.get("circuit") or {}).get("name"),
                    "race_fastest_lap_s": lap_time_to_seconds(
                        (fastest.get("bestLap") or {}).get("time")
                    ),
                    "race_fastest_lap_kph": _num(fastest.get("speed")),
                    "track_condition": ((race_sess.get("condition") or {}).get("track")),
                }
            )
            for e in race_payload["classification"]:
                rider = e.get("rider") or {}
                results.append(
                    {
                        **key,
                        "competitor": rider.get("riders_api_uuid") or rider.get("id"),
                        "competitor_name": rider.get("full_name"),
                        "team": (e.get("constructor") or {}).get("name"),
                        "position": _num(e.get("position")),
                        "classified": e.get("position") is not None,
                        "points": _num(e.get("points")) or 0.0,
                        "laps": _num(e.get("total_laps")),
                        "race_time_s": lap_time_to_seconds(e.get("time")),
                        "gap_first_s": _num((e.get("gap") or {}).get("first")),
                        "average_speed_kph": _num(e.get("average_speed")),
                    }
                )
            for number in (1, 2):
                q = _official(sessions, "Q", number)
                payload = (
                    client.get(f"session/{q['id']}/classification", {"test": "false"})
                    if q
                    else None
                )
                for e in (payload or {}).get("classification") or []:
                    rider = e.get("rider") or {}
                    quali.append(
                        {
                            **key,
                            "session": f"Q{number}",
                            "competitor": rider.get("riders_api_uuid") or rider.get("id"),
                            "position": _num(e.get("position")),
                            "best_lap_s": lap_time_to_seconds(
                                (e.get("best_lap") or {}).get("time")
                            ),
                        }
                    )
        print(f"MotoGP {year} done", flush=True)
    return {
        "mgp_races": pd.DataFrame(races),
        "mgp_results": pd.DataFrame(results),
        "mgp_quali": pd.DataFrame(quali),
    }


def build_dataset(
    start: int = FIRST_SEASON,
    end: int = LAST_SEASON,
    f1_cache: Path = DATA_RAW / "jolpica",
    motogp_cache: Path = DATA_RAW / "motogp",
    out_dir: Path = DATA_PROCESSED,
) -> dict[str, pd.DataFrame]:
    frames = fetch_f1(start, end, JolpicaClient(f1_cache))
    frames |= fetch_motogp(start, end, MotoGPClient(motogp_cache))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return frames


TABLES = ("f1_races", "f1_results", "f1_quali", "mgp_races", "mgp_results", "mgp_quali")


def load_tables(data_dir: Path = DATA_PROCESSED) -> dict[str, pd.DataFrame]:
    return {n: pd.read_parquet(data_dir / f"{n}.parquet") for n in TABLES}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", type=int, default=FIRST_SEASON)
    parser.add_argument("--end", type=int, default=LAST_SEASON)
    parser.add_argument("--f1-cache", type=Path, default=DATA_RAW / "jolpica")
    parser.add_argument("--motogp-cache", type=Path, default=DATA_RAW / "motogp")
    args = parser.parse_args()
    build_dataset(args.start, args.end, args.f1_cache, args.motogp_cache)


if __name__ == "__main__":
    main()
