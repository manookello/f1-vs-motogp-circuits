import numpy as np
import pandas as pd
import pytest

from f1_vs_motogp.analysis import bootstrap_median_diff, gini, venue_comparison
from f1_vs_motogp.data import lap_time_to_seconds


def test_lap_time_to_seconds():
    assert lap_time_to_seconds("1:32.478") == pytest.approx(92.478)
    assert lap_time_to_seconds("01:48.339") == pytest.approx(108.339)
    assert lap_time_to_seconds("") is None


def test_gini_bounds():
    assert gini([10, 10, 10, 10]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 100]) == pytest.approx(0.75)  # n=4 maximum is (n-1)/n
    assert np.isnan(gini([]))


def test_bootstrap_detects_clear_difference():
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(2.0, 0.2, 200))
    b = pd.Series(rng.normal(1.0, 0.2, 200))
    diff, lo, hi = bootstrap_median_diff(a, b, n_boot=500)
    assert 0.9 < diff < 1.1
    assert lo > 0.8 and hi < 1.2


def _summary_rows():
    rows = []
    for series, pole, km in (("F1", 92.0, 5.513), ("MotoGP", 121.0, 5.510)):
        for season in (2023, 2024):
            rows.append(
                {
                    "series": series,
                    "season": season,
                    "venue": "cota",
                    "wet_quali_suspect": False,
                    "pole_s": pole,
                    "race_fastest_lap_s": pole + 3,
                    "lap_km": km,
                    "pole_kph": km / pole * 3600,
                    "quali_spread_pct": 1.0,
                }
            )
    # a wet F1 session that must be ignored
    rows.append(
        {
            "series": "F1",
            "season": 2025,
            "venue": "cota",
            "wet_quali_suspect": True,
            "pole_s": 115.0,
            "race_fastest_lap_s": 96.0,
            "lap_km": 5.513,
            "pole_kph": 5.513 / 115 * 3600,
            "quali_spread_pct": 2.0,
        }
    )
    return pd.DataFrame(rows)


def test_venue_comparison_pairs_same_season_and_skips_wet():
    vc = venue_comparison(_summary_rows())
    assert sorted(vc["f1_season"]) == [2023, 2024]
    assert vc["same_year"].all()
    assert vc["same_layout"].all()
    assert vc["pole_ratio"].iloc[0] == pytest.approx(121 / 92)
