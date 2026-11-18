"""Per-race summaries, shared-venue comparisons and competitiveness (parity) metrics.

Definitions (applied identically to both series):

* **Pole lap** – fastest qualifying lap. F1: best of Q1/Q2/Q3. MotoGP: fastest Q2 lap.
* **Qualifying spread** – (P10's best lap − pole lap) / pole lap, in %. Lower = tighter.
* **Winning margin** – P2's gap to the winner as % of the winner's race time (races differ in
  length, so we normalise). Only when P2 finished on the lead lap.
* **Lap length** – derived from the data: speed × lap time. F1 uses the fastest-lap average speed
  reported by Jolpica; MotoGP uses the race's fastest-lap record speed. Gaps (e.g. F1 seasons
  where the speed isn't published) are filled from the same venue's nearest season.
* **Points Gini** – inequality of Grand Prix points among regular starters (≥ half the races);
  0 = everyone scores the same, 1 = one competitor scores everything.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1_vs_motogp.config import SAME_LAYOUT_TOLERANCE, VENUES

SERIES = ["F1", "MotoGP"]


# --------------------------------------------------------------------------------------
# Per-race summaries
# --------------------------------------------------------------------------------------


def _p10(quali: pd.DataFrame, key: list[str]) -> pd.Series:
    """Best lap of the driver/rider classified 10th. If the source lists two competitors at
    P10 (e.g. F1 2024 Dutch GP after a qualifying disqualification) the quicker lap is used."""
    return quali[quali["position"] == 10].groupby(key)["best_lap_s"].min().rename("p10_s")


def _margin(results: pd.DataFrame, time_col: str = "race_time_s") -> pd.DataFrame:
    """Winner time and P2 margin per race (P2 must be on the lead lap)."""
    top = results[results["position"].isin([1, 2])].pivot_table(
        index=["season", "round"], columns="position", values=time_col
    )
    out = pd.DataFrame(index=top.index)
    out["winner_time_s"] = top.get(1.0)
    out["margin_s"] = top.get(2.0) - top.get(1.0)
    return out


def f1_race_summary(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    races, res, q = t["f1_races"], t["f1_results"], t["f1_quali"]
    key = ["season", "round"]
    pole = q.groupby(key)["best_lap_s"].min().rename("pole_s")
    p10 = _p10(q, key)
    fl = res.groupby(key)["fastest_lap_s"].min().rename("race_fastest_lap_s")
    lap_km = (
        (res["fastest_lap_kph"] * res["fastest_lap_s"] / 3600)
        .groupby([res["season"], res["round"]])
        .median()
        .rename("lap_km")
    )
    winner = res[res["position"] == 1].set_index(key)[["competitor_name", "team"]]
    winner.columns = ["winner", "winner_team"]
    out = races.set_index(key).join([pole, p10, fl, lap_km, winner, _margin(res)])
    return out.reset_index()


def mgp_race_summary(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    races, res, q = t["mgp_races"], t["mgp_results"], t["mgp_quali"]
    key = ["season", "round"]
    q2 = q[q["session"] == "Q2"]
    pole = q2.groupby(key)["best_lap_s"].min().rename("pole_s")
    p10 = _p10(q2, key)
    winner = res[res["position"] == 1].set_index(key)[["competitor_name", "team"]]
    winner.columns = ["winner", "winner_team"]
    gap = res[res["position"] == 2].set_index(key)["gap_first_s"].rename("margin_s")
    win_time = res[res["position"] == 1].set_index(key)["race_time_s"].rename("winner_time_s")
    out = races.set_index(key).join([pole, p10, winner, gap, win_time])
    out["lap_km"] = out["race_fastest_lap_kph"] * out["race_fastest_lap_s"] / 3600
    return out.reset_index()


POLE_VS_RACE_LAP_MAX = 1.03  # a dry pole is always quicker than the race's fastest lap
POLE_VS_MEDIAN_MAX = 1.10  # catches weekends where qualifying *and* race were wet


def race_summaries(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per race for both series, with the derived competitiveness measures.

    Two quality flags are added:

    * ``wet_quali_suspect`` – neither API reliably reports qualifying weather, and a wet session
      inflates pole times by 10-25 %. A session is flagged when its pole lap is more than 3 %
      slower than the same race's fastest lap (in the dry, pole is always quicker), or more than
      10 % slower than the median pole for that series, circuit and layout. Flagged sessions are
      excluded from lap-time comparisons and from the qualifying-spread measure.
    * ``short_race`` – winner's race time below half the series median (e.g. the 2021 Belgian GP,
      run behind the safety car); excluded from the winning-margin measure.
    """
    df = pd.concat([f1_race_summary(t), mgp_race_summary(t)], ignore_index=True)
    df["venue"] = df.apply(venue_key, axis=1)
    df["circuit_key"] = df["venue"].fillna(df["circuit_id"].astype(str))
    df = df.sort_values("season")
    df["lap_km"] = df.groupby(["series", "circuit_key"])["lap_km"].transform(
        lambda s: s.ffill().bfill()
    )
    layout = df["lap_km"].round(2).fillna(-1)
    median_pole = df.groupby([df["series"], df["circuit_key"], layout])["pole_s"].transform(
        "median"
    )
    df["wet_quali_suspect"] = (df["pole_s"] > POLE_VS_RACE_LAP_MAX * df["race_fastest_lap_s"]) | (
        df["pole_s"] > POLE_VS_MEDIAN_MAX * median_pole
    )
    series_median_time = df.groupby("series")["winner_time_s"].transform("median")
    df["short_race"] = df["winner_time_s"] < 0.5 * series_median_time

    df["quali_spread_pct"] = ((df["p10_s"] / df["pole_s"] - 1) * 100).where(
        ~df["wet_quali_suspect"]
    )
    df["margin_pct"] = (df["margin_s"] / df["winner_time_s"] * 100).where(~df["short_race"])
    df["pole_kph"] = df["lap_km"] / df["pole_s"] * 3600
    return df.sort_values(["series", "season", "round"]).reset_index(drop=True)


def venue_key(row: pd.Series) -> str | None:
    for key, (_, f1_id, mgp_name) in VENUES.items():
        if (row["series"] == "F1" and row["circuit_id"] == f1_id) or (
            row["series"] == "MotoGP" and row["circuit_name"] == mgp_name
        ):
            return key
    return None


# --------------------------------------------------------------------------------------
# Shared venues
# --------------------------------------------------------------------------------------


def _fill_lap_km(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing derived lap lengths from the same series+venue's nearest season."""
    df = df.sort_values("season").copy()
    df["lap_km"] = df.groupby(["series", "venue"])["lap_km"].transform(lambda s: s.ffill().bfill())
    df["pole_kph"] = df["lap_km"] / df["pole_s"] * 3600
    return df


def venue_comparison(summary: pd.DataFrame, max_year_gap: int = 1) -> pd.DataFrame:
    """Pair each dry F1 qualifying at a shared venue with the same-season MotoGP one (or the
    nearest season within ``max_year_gap``)."""
    shared = _fill_lap_km(summary[summary["venue"].notna() & ~summary["wet_quali_suspect"]])
    # one race per series/venue/season (two races in a season -> keep the faster pole)
    shared = shared.sort_values("pole_s").drop_duplicates(["series", "venue", "season"])
    f1 = shared[shared["series"] == "F1"]
    mgp = shared[shared["series"] == "MotoGP"]
    rows = []
    cols = ["season", "pole_s", "race_fastest_lap_s", "lap_km", "pole_kph", "quali_spread_pct"]
    for _, f in f1.iterrows():
        cands = mgp[mgp["venue"] == f["venue"]].copy()
        if cands.empty:
            continue
        cands["gap"] = (cands["season"] - f["season"]).abs()
        m = cands.sort_values(["gap", "season"]).iloc[0]
        if m["gap"] > max_year_gap:
            continue
        row = {"venue": f["venue"], "venue_name": VENUES[f["venue"]][0], "same_year": m["gap"] == 0}
        row |= {f"f1_{c}": f[c] for c in cols}
        row |= {f"mgp_{c}": m[c] for c in cols}
        rows.append(row)
    out = pd.DataFrame(rows)
    out["same_layout"] = (out["mgp_lap_km"] / out["f1_lap_km"] - 1).abs() <= SAME_LAYOUT_TOLERANCE
    out["pole_ratio"] = out["mgp_pole_s"] / out["f1_pole_s"]
    out["pole_gap_s"] = out["mgp_pole_s"] - out["f1_pole_s"]
    out["speed_gap_kph"] = out["f1_pole_kph"] - out["mgp_pole_kph"]
    out["race_lap_ratio"] = out["mgp_race_fastest_lap_s"] / out["f1_race_fastest_lap_s"]
    return out.sort_values(["venue", "f1_season"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------
# Parity / competitiveness
# --------------------------------------------------------------------------------------


def gini(values) -> float:
    """Gini coefficient of a non-negative 1-D array (0 = perfect equality)."""
    x = np.sort(np.asarray(values, dtype=float))
    if x.size == 0 or x.sum() == 0:
        return float("nan")
    n = x.size
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum.sum() / cum[-1])) / n)


def season_parity(t: dict[str, pd.DataFrame], summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for series, res in (("F1", t["f1_results"]), ("MotoGP", t["mgp_results"])):
        for season, s in res.groupby("season"):
            n_races = s["round"].nunique()
            starts = s.groupby("competitor")["round"].nunique()
            regulars = starts[starts >= n_races / 2].index
            pts = s[s["competitor"].isin(regulars)].groupby("competitor")["points"].sum()
            winners = s.loc[s["position"] == 1, "competitor"]
            standings = s.groupby("competitor")["points"].sum().sort_values(ascending=False)
            sm = summary[(summary["series"] == series) & (summary["season"] == season)]
            rows.append(
                {
                    "series": series,
                    "season": season,
                    "races": n_races,
                    "distinct_winners": winners.nunique(),
                    "top_winner_share": winners.value_counts().iloc[0] / n_races,
                    "points_gini": gini(pts),
                    "title_margin_pct": (standings.iloc[0] - standings.iloc[1])
                    / standings.iloc[0]
                    * 100,
                    "median_quali_spread_pct": sm["quali_spread_pct"].median(),
                    "median_margin_pct": sm["margin_pct"].median(),
                }
            )
    return pd.DataFrame(rows)


def bootstrap_median_diff(
    a: pd.Series, b: pd.Series, n_boot: int = 5000, seed: int = 7
) -> tuple[float, float, float]:
    """Median(a) − median(b) with a 95 % percentile bootstrap interval."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a.dropna()), np.asarray(b.dropna())
    diffs = np.median(rng.choice(a, (n_boot, a.size)), axis=1) - np.median(
        rng.choice(b, (n_boot, b.size)), axis=1
    )
    return float(np.median(a) - np.median(b)), *np.percentile(diffs, [2.5, 97.5])


def compare_series(summary: pd.DataFrame, since: int | None = None) -> pd.DataFrame:
    """Bootstrap comparison of race-level competitiveness measures, F1 minus MotoGP."""
    s = summary if since is None else summary[summary["season"] >= since]
    rows = []
    for col, label in [
        ("quali_spread_pct", "Qualifying spread, pole to P10 (%)"),
        ("margin_pct", "Winning margin (% of race time)"),
    ]:
        f1, mgp = s.loc[s["series"] == "F1", col], s.loc[s["series"] == "MotoGP", col]
        diff, lo, hi = bootstrap_median_diff(f1, mgp)
        rows.append(
            {
                "measure": label,
                "f1_median": f1.median(),
                "motogp_median": mgp.median(),
                "diff_f1_minus_motogp": diff,
                "ci_low": lo,
                "ci_high": hi,
                "n_f1": f1.notna().sum(),
                "n_motogp": mgp.notna().sum(),
            }
        )
    return pd.DataFrame(rows)
