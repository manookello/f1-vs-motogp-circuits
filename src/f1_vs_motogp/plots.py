"""Charts for the notebooks, README and app (same visual system as the companion projects).

Series colours are fixed everywhere: F1 = slot 1 (blue), MotoGP = slot 2 (orange).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

from f1_vs_motogp.config import FIGURES, VENUES

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
OTHER = "#c3c2b7"
SERIES_COLORS = {"F1": PALETTE[0], "MotoGP": PALETTE[1]}


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "figure.dpi": 110,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 12,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 12,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "lines.linewidth": 2,
            "lines.solid_capstyle": "round",
            "legend.frameon": False,
            "axes.prop_cycle": mpl.cycler(color=PALETTE),
        }
    )


def save(fig: plt.Figure, name: str, folder: Path = FIGURES) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path)
    return path


def _subtitle(ax: plt.Axes, text: str) -> None:
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK_2, fontsize=9, va="bottom")


def venue_medians(vc: pd.DataFrame) -> pd.DataFrame:
    return (
        vc.groupby("venue_name")
        .agg(
            f1_kph=("f1_pole_kph", "median"),
            mgp_kph=("mgp_pole_kph", "median"),
            ratio=("pole_ratio", "median"),
            gap_s=("pole_gap_s", "median"),
            seasons=("f1_season", "nunique"),
            same_layout=("same_layout", "mean"),
        )
        .sort_values("f1_kph")
    )


def pole_speed_dumbbell(vc: pd.DataFrame) -> plt.Figure:
    med = venue_medians(vc)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    y = range(len(med))
    ax.hlines(y, med["mgp_kph"], med["f1_kph"], color=AXIS, linewidth=2, zorder=1)
    ax.scatter(
        med["mgp_kph"],
        y,
        s=70,
        color=SERIES_COLORS["MotoGP"],
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
        label="MotoGP pole",
    )
    ax.scatter(
        med["f1_kph"],
        y,
        s=70,
        color=SERIES_COLORS["F1"],
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
        label="F1 pole",
    )
    for yi, (_, r) in zip(y, med.iterrows(), strict=True):
        ax.text(
            r["f1_kph"] + 2,
            yi,
            f"+{r['f1_kph'] - r['mgp_kph']:.0f} km/h",
            va="center",
            fontsize=9,
            color=INK_2,
        )
    ax.set_yticks(list(y), med.index)
    ax.set_xlim(med["mgp_kph"].min() - 8, med["f1_kph"].max() + 22)
    ax.set_xlabel("Average speed over the pole lap (km/h)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=9)
    gap = med["f1_kph"] - med["mgp_kph"]
    ax.set_title(f"Same track, {gap.min():.0f}-{gap.max():.0f} km/h faster on four wheels", pad=22)
    _subtitle(ax, "Median pole-lap average speed at shared venues, dry sessions, 2014-2026")
    return fig


def pole_ratio_trend(
    vc: pd.DataFrame, venues: tuple[str, ...] = ("cota", "silverstone", "red_bull_ring")
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4))
    for color, venue in zip(PALETTE, venues, strict=False):
        d = vc[(vc["venue"] == venue) & vc["same_layout"]].sort_values("f1_season")
        if d.empty:
            continue
        pct = (d["pole_ratio"] - 1) * 100
        ax.plot(
            d["f1_season"],
            pct,
            color=color,
            marker="o",
            markersize=6,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            label=VENUES[venue][0],
        )
    ax.set_xlim(2013.5, 2026.5)
    ax.set_xticks(range(2014, 2027, 2))
    ax.set_ylabel("MotoGP pole slower than F1 pole (%)")
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("The gap follows the rulebooks", pad=22)
    _subtitle(ax, "MotoGP pole lap vs F1 pole lap, same layout, dry sessions")
    return fig


def ratio_vs_speed(vc: pd.DataFrame) -> plt.Figure:
    med = venue_medians(vc)
    fig, ax = plt.subplots(figsize=(6.5, 4.4))
    ax.scatter(
        med["f1_kph"],
        (med["ratio"] - 1) * 100,
        s=70,
        color=PALETTE[0],
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
    )
    for name, r in med.iterrows():
        ax.annotate(
            name,
            (r["f1_kph"], (r["ratio"] - 1) * 100),
            xytext=(7, -3),
            textcoords="offset points",
            fontsize=8.5,
            color=INK_2,
        )
    ax.set_xlabel("F1 pole-lap average speed (km/h)")
    ax.set_ylabel("MotoGP pole slower than F1 (%)")
    ax.set_xlim(med["f1_kph"].min() - 5, med["f1_kph"].max() + 25)
    ax.set_title("Faster, flowing tracks favour the car", pad=22)
    _subtitle(ax, "Each dot is a shared venue (median over paired dry seasons)")
    return fig


def parity_panels(parity: pd.DataFrame) -> plt.Figure:
    panels = [
        ("median_quali_spread_pct", "Qualifying spread, pole to P10 (%)"),
        ("median_margin_pct", "Winning margin (% of race time)"),
        ("distinct_winners", "Different race winners"),
        ("points_gini", "Points inequality (Gini)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4), sharex=True)
    for ax, (col, title) in zip(axes.flat, panels, strict=True):
        for series in ("F1", "MotoGP"):
            d = parity[parity["series"] == series]
            ax.plot(
                d["season"],
                d[col],
                color=SERIES_COLORS[series],
                marker="o",
                markersize=5,
                markeredgecolor=SURFACE,
                markeredgewidth=1.2,
                label=series,
            )
        ax.set_title(title, fontsize=10)
        ax.set_ylim(bottom=0)
    axes[0, 0].legend(loc="lower left", fontsize=9)
    for ax in axes[1]:
        ax.set_xticks(range(2014, 2027, 2))
    fig.suptitle(
        "Which championship is closer? Lower = closer, except 'different winners'",
        x=0.01,
        ha="left",
        fontsize=12,
        fontweight="semibold",
    )
    fig.tight_layout()
    return fig


def bootstrap_forest(cmp: pd.DataFrame) -> plt.Figure:
    """Median difference F1 − MotoGP with 95 % bootstrap CIs (one row per measure/period)."""
    cmp = cmp.iloc[::-1].reset_index(drop=True)
    labels = cmp["measure"] + "\n" + cmp["period"]
    fig, ax = plt.subplots(figsize=(8, 0.75 * len(cmp) + 1.2))
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.hlines(range(len(cmp)), cmp["ci_low"], cmp["ci_high"], color=PALETTE[0], linewidth=2)
    ax.scatter(
        cmp["diff_f1_minus_motogp"],
        range(len(cmp)),
        s=60,
        color=PALETTE[0],
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
    )
    ax.set_yticks(range(len(cmp)), labels, fontsize=9)
    ax.set_xlabel("F1 minus MotoGP, percentage points (positive = MotoGP closer)")
    ax.grid(axis="y", visible=False)
    ax.set_title("MotoGP is closer on both measures", pad=22)
    _subtitle(ax, "Difference in race medians with 95% bootstrap confidence intervals")
    return fig
