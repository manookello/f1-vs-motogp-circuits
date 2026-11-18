"""F1 vs MotoGP explorer.

Run with:  streamlit run app/streamlit_app.py
Reads only the processed files committed under data/processed/ (no API calls).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from f1_vs_motogp.config import DATA_PROCESSED, VENUES
from f1_vs_motogp.plots import SERIES_COLORS, venue_medians

st.set_page_config(page_title="F1 vs MotoGP", page_icon="🏁", layout="wide")


@st.cache_data
def load():
    summary = pd.read_parquet(DATA_PROCESSED / "race_summary.parquet")
    vc = pd.read_parquet(DATA_PROCESSED / "venue_comparison.parquet")
    parity = pd.read_csv(DATA_PROCESSED / "season_parity.csv")
    cmp = pd.read_csv(DATA_PROCESSED / "series_comparison.csv")
    return summary, vc, parity, cmp


def tidy(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    return fig


summary, vc, parity, cmp = load()

st.title("F1 vs MotoGP")
st.caption(
    "Two championships, eight shared circuits, 2014–2026: how much faster is the car, and "
    "which series is closer? Wet qualifying sessions are excluded from lap-time measures."
)

tab_track, tab_all, tab_parity = st.tabs(["Same track", "All shared venues", "Competitiveness"])

# ---------------------------------------------------------------------------------------
with tab_track:
    names = {k: v[0] for k, v in VENUES.items()}
    venue = st.selectbox("Circuit", list(names), format_func=names.get)
    d = summary[(summary["venue"] == venue) & ~summary["wet_quali_suspect"]]
    pairs = vc[vc["venue"] == venue]
    k1, k2, k3, k4 = st.columns(4)
    if not pairs.empty:
        k1.metric("F1 pole speed (median)", f"{pairs['f1_pole_kph'].median():.0f} km/h")
        k2.metric("MotoGP pole speed (median)", f"{pairs['mgp_pole_kph'].median():.0f} km/h")
        k3.metric("MotoGP pole slower by", f"{pairs['pole_gap_s'].median():.1f} s")
        k4.metric("Same layout in", f"{pairs['same_layout'].mean():.0%} of paired seasons")
    measure = st.radio("Lap", ["Pole lap", "Race fastest lap"], horizontal=True)
    col = "pole_s" if measure == "Pole lap" else "race_fastest_lap_s"
    fig = px.line(
        d.sort_values("season"),
        x="season",
        y=col,
        color="series",
        markers=True,
        color_discrete_map=SERIES_COLORS,
        hover_data={"race_name": True, "lap_km": ":.3f", col: ":.3f"},
        labels={col: f"{measure} (seconds)", "season": "", "series": ""},
        title=f"{names[venue]}: {measure.lower()} by season",
    )
    fig.update_traces(line_width=2, marker_size=8)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(tidy(fig), use_container_width=True)
    with st.expander("Table view"):
        st.dataframe(
            d[
                [
                    "series",
                    "season",
                    "race_name",
                    "lap_km",
                    "pole_s",
                    "race_fastest_lap_s",
                    "pole_kph",
                ]
            ]
            .sort_values(["season", "series"])
            .round(3),
            hide_index=True,
            use_container_width=True,
        )

# ---------------------------------------------------------------------------------------
with tab_all:
    med = venue_medians(vc).reset_index()
    long = med.melt(
        id_vars="venue_name", value_vars=["f1_kph", "mgp_kph"], var_name="series", value_name="kph"
    )
    long["series"] = long["series"].map({"f1_kph": "F1", "mgp_kph": "MotoGP"})
    fig = go.Figure()
    for _, r in med.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[r["mgp_kph"], r["f1_kph"]],
                y=[r["venue_name"]] * 2,
                mode="lines",
                line=dict(color="#c3c2b7", width=2),
                showlegend=False,
                hoverinfo="skip",
            )
        )
    for series, g in long.groupby("series"):
        fig.add_trace(
            go.Scatter(
                x=g["kph"],
                y=g["venue_name"],
                mode="markers",
                name=series,
                marker=dict(size=12, color=SERIES_COLORS[series]),
                hovertemplate="%{y}: %{x:.0f} km/h<extra>" + series + "</extra>",
            )
        )
    fig.update_layout(title="Median pole-lap average speed, dry sessions", xaxis_title="km/h")
    st.plotly_chart(tidy(fig, 460), use_container_width=True)
    st.dataframe(
        med.rename(columns={"venue_name": "venue"}).round(3),
        hide_index=True,
        use_container_width=True,
    )

# ---------------------------------------------------------------------------------------
with tab_parity:
    metrics = {
        "median_quali_spread_pct": "Qualifying spread, pole to P10 (%)",
        "median_margin_pct": "Winning margin (% of race time)",
        "distinct_winners": "Different race winners",
        "points_gini": "Points inequality (Gini)",
        "top_winner_share": "Share of wins by the top winner",
        "title_margin_pct": "Title margin (% of champion's points)",
    }
    metric = st.selectbox("Measure", list(metrics), format_func=metrics.get)
    fig = px.line(
        parity,
        x="season",
        y=metric,
        color="series",
        markers=True,
        color_discrete_map=SERIES_COLORS,
        labels={metric: metrics[metric], "season": "", "series": ""},
    )
    fig.update_traces(line_width=2, marker_size=8)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(tidy(fig), use_container_width=True)
    st.subheader("Race-level comparison with 95% bootstrap intervals")
    st.dataframe(cmp.round(3), hide_index=True, use_container_width=True)
    st.caption("diff = F1 median − MotoGP median; a positive value means MotoGP is closer.")
