import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.title("Secondary Market Relative Value Dashboard")
st.caption("Prototype: Issuer vs AA/AAA Benchmark")
st.sidebar.header("User Inputs")

# Issuer Universe Setup

ISSUER_FILE = "data/issuers.csv"

if not os.path.exists(ISSUER_FILE):
    os.makedirs("data", exist_ok=True)
    pd.DataFrame({"Issuer": [], "Sector": []}).to_csv(ISSUER_FILE, index=False)

issuer_df = pd.read_csv(ISSUER_FILE)

# Make sure required columns exist
if "Issuer" not in issuer_df.columns:
    issuer_df["Issuer"] = ""

if "Sector" not in issuer_df.columns:
    issuer_df["Sector"] = "Unclassified"

# Clean data
issuer_df["Issuer"] = issuer_df["Issuer"].astype(str).str.strip()
issuer_df["Sector"] = issuer_df["Sector"].astype(str).str.strip()

issuer_df = issuer_df[issuer_df["Issuer"] != ""]
issuer_df["Sector"] = issuer_df["Sector"].replace("", "Unclassified")

issuer_df = issuer_df.drop_duplicates(subset=["Issuer"], keep="first")
issuer_df = issuer_df.sort_values(["Sector", "Issuer"])

# Save cleaned version
issuer_df.to_csv(ISSUER_FILE, index=False)

# Select Sector First

sector_list = sorted(issuer_df["Sector"].dropna().unique().tolist())

selected_sector = st.sidebar.selectbox(
    "Select Sector",
    sector_list,
    index=None,
    placeholder="Search or select sector..."
)

# Other Inputs

maturity = st.sidebar.selectbox(
    "Maturity Bucket",
    ["10Y", "20Y", "30Y"]
)

time_window = st.sidebar.selectbox(
    "Time Window",
    ["1Y", "3Y", "5Y"]
)

if selected_sector is not None:
    filtered_issuers = (
        issuer_df[issuer_df["Sector"] == selected_sector]["Issuer"]
        .sort_values()
        .tolist()
    )
else:
    filtered_issuers = []

issuer = st.sidebar.selectbox(
    "Select Issuer",
    filtered_issuers,
    index=None,
    placeholder="Search issuer alphabetically..."
)

# =========================
# Add New Issuer + Sector
# =========================

st.sidebar.markdown("---")
st.sidebar.subheader("Add New Issuer")

new_issuer = st.sidebar.text_input(
    "New issuer name",
    placeholder="Example: Los Angeles County"
)

new_sector_choice = st.sidebar.selectbox(
    "Sector for new issuer",
    sector_list + ["Add new sector manually"],
    index=None,
    placeholder="Select sector..."
)

new_sector_manual = ""

if new_sector_choice == "Add new sector manually":
    new_sector_manual = st.sidebar.text_input(
        "New sector name",
        placeholder="Example: Healthcare"
    )

if st.sidebar.button("Add Issuer"):
    new_issuer_clean = new_issuer.strip()

    if new_sector_choice == "Add new sector manually":
        new_sector_clean = new_sector_manual.strip()
    else:
        new_sector_clean = new_sector_choice

    if new_issuer_clean == "":
        st.sidebar.warning("Please enter a valid issuer name.")

    elif not new_sector_clean:
        st.sidebar.warning("Please select or enter a sector.")

    elif new_issuer_clean in issuer_df["Issuer"].values:
        st.sidebar.info("This issuer already exists.")

    else:
        new_row = pd.DataFrame({
            "Issuer": [new_issuer_clean],
            "Sector": [new_sector_clean]
        })

        issuer_df = pd.concat([issuer_df, new_row], ignore_index=True)

        issuer_df["Issuer"] = issuer_df["Issuer"].astype(str).str.strip()
        issuer_df["Sector"] = issuer_df["Sector"].astype(str).str.strip()
        issuer_df = issuer_df[issuer_df["Issuer"] != ""]
        issuer_df["Sector"] = issuer_df["Sector"].replace("", "Unclassified")
        issuer_df = issuer_df.drop_duplicates(subset=["Issuer"], keep="first")
        issuer_df = issuer_df.sort_values(["Sector", "Issuer"])

        issuer_df.to_csv(ISSUER_FILE, index=False)

        st.sidebar.success(f"Added: {new_issuer_clean} → {new_sector_clean}")
        st.rerun()

# =========================
# Correct Existing Issuer Sector
# =========================

st.sidebar.markdown("---")
st.sidebar.subheader("Correct Issuer Sector")

issuer_to_edit = st.sidebar.selectbox(
    "Issuer to correct",
    issuer_df["Issuer"].sort_values().tolist(),
    index=None,
    placeholder="Search issuer to edit..."
)

if issuer_to_edit:
    current_sector = issuer_df.loc[
        issuer_df["Issuer"] == issuer_to_edit,
        "Sector"
    ].iloc[0]

    st.sidebar.caption(f"Current sector: {current_sector}")

    corrected_sector_choice = st.sidebar.selectbox(
        "Corrected sector",
        sector_list + ["Add new sector manually"],
        index=None,
        placeholder="Select corrected sector..."
    )

    corrected_sector_manual = ""

    if corrected_sector_choice == "Add new sector manually":
        corrected_sector_manual = st.sidebar.text_input(
            "New corrected sector name",
            placeholder="Example: Public Power"
        )

    if st.sidebar.button("Update Sector"):
        if corrected_sector_choice == "Add new sector manually":
            corrected_sector = corrected_sector_manual.strip()
        else:
            corrected_sector = corrected_sector_choice

        if not corrected_sector:
            st.sidebar.warning("Please select or enter a corrected sector.")

        else:
            issuer_df.loc[
                issuer_df["Issuer"] == issuer_to_edit,
                "Sector"
            ] = corrected_sector

            issuer_df = issuer_df.sort_values(["Sector", "Issuer"])
            issuer_df.to_csv(ISSUER_FILE, index=False)

            st.sidebar.success(
                f"Updated: {issuer_to_edit} → {corrected_sector}"
            )
            st.rerun()
# Stop if no issuer selected
if issuer is None:
    st.warning("Please select a sector and issuer to continue.")
    st.stop()

# Main Page
st.header("Executive Snapshot")
st.write(f"Selected Issuer: **{issuer}**")
st.write(f"Maturity Bucket: **{maturity}**")
st.write(f"Time Window: **{time_window}**")
st.header("Executive Snapshot")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Current Spread", "52 bps", "+7 bps")
col2.metric("AA Peer Avg", "42 bps", "+2 bps")
col3.metric("Vs AA Peers", "+10 bps")
col4.metric("Signal", "Cheapening")

st.header("Spread Trend")

data = pd.DataFrame({
    "Date": pd.date_range("2025-01-01", periods=12, freq="ME"),
    "LADWP Spread": [38, 40, 42, 41, 45, 47, 46, 48, 50, 49, 51, 52],
    "AA Peer Avg": [35, 36, 37, 37, 38, 39, 39, 40, 41, 41, 42, 42],
    "AAA Benchmark": [20, 21, 22, 22, 23, 24, 23, 24, 25, 25, 26, 26],
})

chart_data = data.melt(
    id_vars="Date",
    value_vars=["LADWP Spread", "AA Peer Avg", "AAA Benchmark"],
    var_name="Series",
    value_name="Spread"
)

fig = px.line(chart_data, x="Date", y="Spread", color="Series", markers=True)
st.plotly_chart(fig, use_container_width=True)

st.header("Relative Value Summary")

summary = pd.DataFrame({
    "Metric": ["Current Spread", "1M Change", "Vs AA Peer Avg", "Historical Percentile", "Liquidity Check"],
    "Value": ["52 bps", "+7 bps", "+10 bps", "78th percentile", "Moderate"]
})

st.dataframe(summary, use_container_width=True)

st.header("Signal Box")
st.info("LADWP is trading wider than AA peers, suggesting mild cheapening relative to comparable issuers.")
