from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="MOTEL Data Explorer", layout="wide")

st.title("MOTEL Technology Data Explorer")
st.caption("Methodology for Open Technology Data in Energy Models")

data_path = Path(__file__).parent / "data" / "sample_technologies.csv"
df = pd.read_csv(data_path)

st.markdown("[Project documentation (GitHub Pages)](https://YOUR-ORG.github.io/motel-db/)")

st.subheader("Technology Parameters")
st.dataframe(df, use_container_width=True)

category_filter = st.multiselect(
    "Filter by category",
    options=sorted(df["category"].unique().tolist()),
    default=sorted(df["category"].unique().tolist()),
)

filtered = df[df["category"].isin(category_filter)]

left, right = st.columns(2)

with left:
    st.markdown("### CAPEX vs Efficiency")
    scatter = (
        alt.Chart(filtered)
        .mark_circle(size=120)
        .encode(
            x=alt.X("capex_chf_per_kw:Q", title="CAPEX (CHF/kW)"),
            y=alt.Y("efficiency:Q", title="Efficiency"),
            color="category:N",
            tooltip=["technology", "category", "capex_chf_per_kw", "efficiency"],
        )
        .interactive()
    )
    st.altair_chart(scatter, use_container_width=True)

with right:
    st.markdown("### Lifetime by Technology")
    bars = (
        alt.Chart(filtered)
        .mark_bar()
        .encode(
            x=alt.X("technology:N", sort="-y", title="Technology"),
            y=alt.Y("lifetime_years:Q", title="Lifetime (years)"),
            color="category:N",
            tooltip=["technology", "lifetime_years", "category"],
        )
    )
    st.altair_chart(bars, use_container_width=True)
