import os
import glob
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# Page Setup
# ============================================================

st.set_page_config(
    page_title="Secondary Market Relative Value Dashboard",
    layout="wide"
)

st.title("Secondary Market Relative Value Dashboard")
st.caption("Issuer / Bond / Trade History Dashboard")


# ============================================================
# File Paths
# ============================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BONDS_FILE_CANDIDATES = [
    DATA_DIR / "Bonds.csv",
    DATA_DIR / "bonds.csv",
]

ISSUER_FILE = DATA_DIR / "issuers.csv"

MMD_FILE_CANDIDATES = [
    DATA_DIR / "mmd.csv",
    DATA_DIR / "mmd_curve.csv",
]

TRADE_FILE_PATTERNS = [
    str(DATA_DIR / "trades" / "*.xlsx"),
    str(DATA_DIR / "trades" / "*.xls"),
    str(DATA_DIR / "trades" / "*.csv"),
    str(DATA_DIR / "*_Trade.xlsx"),
    str(DATA_DIR / "*_Trades.xlsx"),
    str(DATA_DIR / "*_trade.xlsx"),
    str(DATA_DIR / "*_trades.xlsx"),
    str(DATA_DIR / "*Trade*.xlsx"),
    str(DATA_DIR / "*Trade*.csv"),
]


# ============================================================
# Utility Functions
# ============================================================

def find_first_existing(paths):
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None


def clean_colname(col):
    return (
        str(col)
        .strip()
        .lower()
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def clean_money_series(s):
    return (
        s.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    )


def clean_numeric(s):
    return pd.to_numeric(clean_money_series(s), errors="coerce")


def clean_cusip(s):
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": pd.NA, "": pd.NA})
    )


def normalize_text(s):
    if pd.isna(s):
        return pd.NA
    return str(s).strip()


def save_issuers(issuers_df):
    issuers_df = issuers_df.copy()

    needed = ["issuer", "sector", "primary_type", "notes"]
    for col in needed:
        if col not in issuers_df.columns:
            issuers_df[col] = pd.NA

    issuers_df["issuer"] = issuers_df["issuer"].astype(str).str.strip()
    issuers_df["sector"] = issuers_df["sector"].astype(str).str.strip()

    issuers_df = issuers_df[issuers_df["issuer"].notna()]
    issuers_df = issuers_df[issuers_df["issuer"] != ""]
    issuers_df = issuers_df.drop_duplicates(subset=["issuer"], keep="last")
    issuers_df = issuers_df.sort_values(["sector", "issuer"])

    issuers_df[needed].to_csv(ISSUER_FILE, index=False)


def standardize_bonds(df):
    df = df.copy()
    df.columns = [clean_colname(c) for c in df.columns]

    rename_map = {
        "cusip": "cusip",
        "cusip9": "cusip",
        "issuer": "issuer",
        "secondary_credit": "secondary_credit",
        "maturity": "maturity",
        "maturity_date": "maturity",
        "par_amount": "par_amount",
        "outstanding_amount": "outstanding_amount",
        "coupon": "coupon",
        "call_date": "call_date",
        "call_price": "call_price",
        "fed_tax": "fed_tax",
        "tax_status": "fed_tax",
        "amt": "amt",
        "series": "series",
        "election": "election",
        "type": "type",
        "lien": "lien",
        "term": "term",
        "sector": "sector",
        "primary_type": "primary_type",
    }

    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})

    required_cols = [
        "issuer", "type", "lien", "election", "series", "cusip",
        "secondary_credit", "term", "maturity", "par_amount",
        "outstanding_amount", "coupon", "call_date", "call_price",
        "fed_tax", "amt", "sector", "primary_type"
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = pd.NA

    df["cusip"] = clean_cusip(df["cusip"])
    df["issuer"] = df["issuer"].astype(str).str.strip()
    df["sector"] = df["sector"].astype(str).str.strip().replace({"nan": pd.NA, "": pd.NA})
    df["primary_type"] = df["primary_type"].astype(str).str.strip().replace({"nan": pd.NA, "": pd.NA})

    df["series"] = df["series"].astype(str).str.strip().replace({"nan": pd.NA})
    df["secondary_credit"] = df["secondary_credit"].astype(str).str.strip().replace({"nan": pd.NA})
    df["term"] = df["term"].astype(str).str.strip().replace({"nan": pd.NA})

    df["maturity"] = pd.to_datetime(df["maturity"], errors="coerce")
    df["call_date"] = pd.to_datetime(df["call_date"], errors="coerce")

    df["par_amount"] = clean_numeric(df["par_amount"])
    df["outstanding_amount"] = clean_numeric(df["outstanding_amount"])
    df["coupon"] = clean_numeric(df["coupon"])
    df["call_price"] = clean_numeric(df["call_price"])

    df = df[df["cusip"].notna()].copy()
    df = df[df["maturity"].notna()].copy()

    today = pd.Timestamp.today().normalize()
    df["years_to_maturity"] = (df["maturity"] - today).dt.days / 365.25

    return df[required_cols + ["years_to_maturity"]]


def read_trade_file(path):
    path = Path(path)

    if path.suffix.lower() in [".xlsx", ".xls"]:
        try:
            return pd.read_excel(path, sheet_name="ag-grid", dtype={"CUSIP9": str})
        except Exception:
            return pd.read_excel(path, dtype={"CUSIP9": str})

    return pd.read_csv(path, dtype={"CUSIP9": str, "cusip": str})


def infer_issuer_from_filename(path):
    stem = Path(path).stem
    stem = re.sub(r"[_\-\s]*(Trade|Trades|trade|trades)\s*$", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem


def standardize_trades(df, source_file=None):
    df = df.copy()
    df.columns = [clean_colname(c) for c in df.columns]

    rename_map = {
        "trade_date_time": "trade_datetime",
        "cusip9": "cusip",
        "description": "description",
        "maturity_date": "maturity",
        "trade_date": "trade_date",
        "settlement_date": "settlement_date",
        "coupon": "coupon",
        "yield": "yield",
        "price": "price",
        "trade_amount": "trade_amount",
        "calculation_date": "calculation_date",
        "calculation_price": "calculation_price",
        "index": "index",
        "index_rate": "index_rate",
        "spread": "spread",
        "trade_type": "trade_type",
        "ratings_m_s_f": "ratings_m_s_f",
    }

    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})

    required_cols = [
        "trade_datetime", "cusip", "description", "maturity", "trade_date",
        "settlement_date", "coupon", "yield", "price", "trade_amount",
        "calculation_date", "calculation_price", "index", "index_rate",
        "spread", "trade_type", "ratings_m_s_f"
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = pd.NA

    df["cusip"] = clean_cusip(df["cusip"])

    for col in ["trade_datetime", "maturity", "trade_date", "settlement_date", "calculation_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ["coupon", "yield", "price", "trade_amount", "calculation_price", "index_rate", "spread"]:
        df[col] = clean_numeric(df[col])

    df["source_file"] = Path(source_file).name if source_file else pd.NA
    df["source_issuer_guess"] = infer_issuer_from_filename(source_file) if source_file else pd.NA

    df = df[df["cusip"].notna()].copy()
    df = df[df["trade_date"].notna()].copy()

    return df[required_cols + ["source_file", "source_issuer_guess"]]


@st.cache_data(show_spinner=False)
def load_bonds():
    bonds_file = find_first_existing(BONDS_FILE_CANDIDATES)
    if bonds_file is None:
        return pd.DataFrame(), None

    raw = pd.read_csv(bonds_file, dtype={"Cusip": str, "CUSIP": str, "cusip": str})
    return standardize_bonds(raw), bonds_file


@st.cache_data(show_spinner=False)
def load_trades():
    files = []
    for pattern in TRADE_FILE_PATTERNS:
        files.extend(glob.glob(pattern))

    seen = set()
    unique_files = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    trade_frames = []
    failed_files = []

    for f in unique_files:
        try:
            raw = read_trade_file(f)
            trade_frames.append(standardize_trades(raw, source_file=f))
        except Exception as e:
            failed_files.append((Path(f).name, str(e)))

    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    return trades, unique_files, failed_files


@st.cache_data(show_spinner=False)
def load_issuers_from_csv():
    if not ISSUER_FILE.exists():
        return pd.DataFrame(columns=["issuer", "sector", "primary_type", "notes"])

    df = pd.read_csv(ISSUER_FILE)
    df.columns = [clean_colname(c) for c in df.columns]

    for col in ["issuer", "sector", "primary_type", "notes"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["issuer"] = df["issuer"].astype(str).str.strip()
    df["sector"] = df["sector"].astype(str).str.strip().replace({"nan": "Unassigned", "": "Unassigned"})
    df["primary_type"] = df["primary_type"].astype(str).str.strip().replace({"nan": pd.NA})
    df["notes"] = df["notes"].astype(str).str.strip().replace({"nan": pd.NA})

    df = df[df["issuer"] != ""].copy()
    df = df.drop_duplicates(subset=["issuer"], keep="last")

    return df[["issuer", "sector", "primary_type", "notes"]]


def build_issuer_master(bonds_df, issuers_csv_df):
    from_bonds = (
        bonds_df[["issuer", "sector", "primary_type"]]
        .drop_duplicates(subset=["issuer"])
        .copy()
    )

    from_bonds["sector"] = from_bonds["sector"].fillna("Unassigned")
    from_bonds["primary_type"] = from_bonds["primary_type"].fillna(pd.NA)
    from_bonds["notes"] = pd.NA

    combined = pd.concat([from_bonds, issuers_csv_df], ignore_index=True)

    combined["issuer"] = combined["issuer"].astype(str).str.strip()
    combined["sector"] = combined["sector"].astype(str).str.strip().replace({"nan": "Unassigned", "": "Unassigned"})

    combined = combined[combined["issuer"] != ""]
    combined = combined.drop_duplicates(subset=["issuer"], keep="last")
    combined = combined.sort_values(["sector", "issuer"])

    return combined[["issuer", "sector", "primary_type", "notes"]]


@st.cache_data(show_spinner=False)
def load_mmd():
    mmd_file = find_first_existing(MMD_FILE_CANDIDATES)
    if mmd_file is None:
        return pd.DataFrame(), None

    df = pd.read_csv(mmd_file)
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("-Yr", "Y", regex=False)
        .str.replace("Yr", "Y", regex=False)
        .str.replace("-YR", "Y", regex=False)
        .str.replace("YR", "Y", regex=False)
        .str.replace("-", "", regex=False)
    )

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    return df, mmd_file


def assign_maturity_bucket(years):
    if pd.isna(years):
        return pd.NA
    if years <= 7:
        return "Short"
    if years <= 15:
        return "10Y"
    if years <= 25:
        return "20Y"
    return "30Y"


# ============================================================
# Reload Button
# ============================================================

with st.sidebar:
    st.header("Data Control")

    if st.button("Reload Data"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# Load Data
# ============================================================

bonds_df, bonds_file = load_bonds()
trades_df, trade_files, failed_trade_files = load_trades()
issuers_csv_df = load_issuers_from_csv()
issuer_master = build_issuer_master(bonds_df, issuers_csv_df)
mmd_df, mmd_file = load_mmd()

if bonds_df.empty:
    st.error("No bonds file found. Please add data/Bonds.csv or data/bonds.csv.")
    st.stop()

# 如果 issuers.csv 不存在，自动创建
if not ISSUER_FILE.exists():
    save_issuers(issuer_master)
    st.cache_data.clear()
    st.rerun()

# 把 sector 信息 merge 回 bonds
bonds_df = bonds_df.drop(columns=["sector", "primary_type"], errors="ignore").merge(
    issuer_master[["issuer", "sector", "primary_type"]],
    on="issuer",
    how="left"
)

bonds_df["sector"] = bonds_df["sector"].fillna("Unassigned")


# ============================================================
# Merge Trades with Bonds
# ============================================================

if not trades_df.empty:
    market_df = trades_df.merge(
        bonds_df,
        on="cusip",
        how="left",
        suffixes=("_trade", "_bond")
    )

    if "issuer" not in market_df.columns:
        market_df["issuer"] = market_df["source_issuer_guess"]
    else:
        market_df["issuer"] = market_df["issuer"].fillna(market_df["source_issuer_guess"])

    market_df["sector"] = market_df["sector"].fillna("Unassigned")

    market_df["years_to_maturity_at_trade"] = (
        market_df["maturity_bond"].fillna(market_df["maturity_trade"]) - market_df["trade_date"]
    ).dt.days / 365.25

    market_df["maturity_bucket"] = market_df["years_to_maturity_at_trade"].apply(assign_maturity_bucket)
else:
    market_df = pd.DataFrame()


# ============================================================
# Sidebar: Issuer Tools
# ============================================================

st.sidebar.markdown("---")
st.sidebar.header("Issuer Tools")

sector_options = sorted(issuer_master["sector"].dropna().unique().tolist())

selected_sector = st.sidebar.selectbox(
    "1. Select Sector",
    sector_options,
    index=0 if sector_options else None
)

issuers_in_sector = (
    issuer_master[issuer_master["sector"] == selected_sector]["issuer"]
    .dropna()
    .sort_values()
    .tolist()
)

selected_issuer = st.sidebar.selectbox(
    "2. Select Issuer",
    issuers_in_sector,
    index=0 if issuers_in_sector else None
)

maturity_bucket = st.sidebar.selectbox(
    "Maturity Bucket",
    ["All", "Short", "10Y", "20Y", "30Y"]
)

time_window = st.sidebar.selectbox(
    "Time Window",
    ["All", "1Y", "3Y", "5Y"]
)

show_raw_tables = st.sidebar.checkbox("Show raw tables", value=False)


# ============================================================
# Add Issuer
# ============================================================

with st.sidebar.expander("Add New Issuer"):
    with st.form("add_issuer_form"):
        new_issuer = st.text_input("Issuer Name")
        new_sector = st.text_input("Sector")
        new_primary_type = st.text_input("Primary Type / Optional")
        new_notes = st.text_area("Notes / Optional")

        submitted = st.form_submit_button("Add Issuer")

        if submitted:
            if not new_issuer.strip():
                st.warning("Issuer name cannot be empty.")
            else:
                new_row = pd.DataFrame([{
                    "issuer": new_issuer.strip(),
                    "sector": new_sector.strip() if new_sector.strip() else "Unassigned",
                    "primary_type": new_primary_type.strip() if new_primary_type.strip() else pd.NA,
                    "notes": new_notes.strip() if new_notes.strip() else pd.NA,
                }])

                updated = pd.concat([issuer_master, new_row], ignore_index=True)
                save_issuers(updated)

                st.success("Issuer added and saved to issuers.csv.")
                st.cache_data.clear()
                st.rerun()


# ============================================================
# Correct Issuer
# ============================================================

with st.sidebar.expander("Correct Existing Issuer"):
    issuer_to_correct = st.selectbox(
        "Issuer to Correct",
        sorted(issuer_master["issuer"].dropna().unique().tolist()),
        key="issuer_to_correct"
    )

    current_row = issuer_master[issuer_master["issuer"] == issuer_to_correct].iloc[0]

    with st.form("correct_issuer_form"):
        corrected_issuer = st.text_input("Corrected Issuer Name", value=current_row["issuer"])
        corrected_sector = st.text_input("Corrected Sector", value=current_row["sector"])
        corrected_primary_type = st.text_input(
            "Corrected Primary Type",
            value="" if pd.isna(current_row["primary_type"]) else str(current_row["primary_type"])
        )
        corrected_notes = st.text_area(
            "Notes",
            value="" if pd.isna(current_row["notes"]) else str(current_row["notes"])
        )

        corrected_submit = st.form_submit_button("Save Correction")

        if corrected_submit:
            updated = issuer_master.copy()

            mask = updated["issuer"] == issuer_to_correct
            updated.loc[mask, "issuer"] = corrected_issuer.strip()
            updated.loc[mask, "sector"] = corrected_sector.strip() if corrected_sector.strip() else "Unassigned"
            updated.loc[mask, "primary_type"] = corrected_primary_type.strip() if corrected_primary_type.strip() else pd.NA
            updated.loc[mask, "notes"] = corrected_notes.strip() if corrected_notes.strip() else pd.NA

            save_issuers(updated)

            st.success("Correction saved to issuers.csv.")
            st.cache_data.clear()
            st.rerun()


# ============================================================
# Sidebar File Info
# ============================================================

st.sidebar.markdown("---")
st.sidebar.caption(f"Bonds file: {bonds_file.name if bonds_file else 'None'}")
st.sidebar.caption(f"Issuer file: {ISSUER_FILE.name}")
st.sidebar.caption(f"Trade files loaded: {len(trade_files)}")

if failed_trade_files:
    with st.sidebar.expander("Failed trade files"):
        for name, err in failed_trade_files:
            st.write(f"{name}: {err}")


# ============================================================
# Filter Data
# ============================================================

if selected_issuer:
    issuer_bonds = bonds_df[bonds_df["issuer"] == selected_issuer].copy()
else:
    issuer_bonds = pd.DataFrame()

if not market_df.empty and selected_issuer:
    issuer_trades = market_df[market_df["issuer"] == selected_issuer].copy()
else:
    issuer_trades = pd.DataFrame()

if not issuer_trades.empty and maturity_bucket != "All":
    issuer_trades = issuer_trades[issuer_trades["maturity_bucket"] == maturity_bucket].copy()

if not issuer_trades.empty and time_window != "All":
    latest_date = issuer_trades["trade_date"].max()

    if time_window == "1Y":
        start_date = latest_date - pd.DateOffset(years=1)
    elif time_window == "3Y":
        start_date = latest_date - pd.DateOffset(years=3)
    else:
        start_date = latest_date - pd.DateOffset(years=5)

    issuer_trades = issuer_trades[issuer_trades["trade_date"] >= start_date].copy()


# ============================================================
# Executive Snapshot
# ============================================================

st.header("Executive Snapshot")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Sector", selected_sector if selected_sector else "None")
col2.metric("Issuer", selected_issuer if selected_issuer else "None")
col3.metric("Bonds in Master", f"{len(issuer_bonds):,}")

if not issuer_trades.empty:
    col4.metric("Trades Loaded", f"{len(issuer_trades):,}")
    col5.metric("Latest Trade Date", issuer_trades["trade_date"].max().strftime("%Y-%m-%d"))
else:
    col4.metric("Trades Loaded", "0")
    col5.metric("Liquidity Status", "No trade data")


# ============================================================
# Bond Master Section
# ============================================================

st.header("Bond Master")

bond_display_cols = [
    "issuer", "sector", "primary_type", "election", "series", "cusip",
    "secondary_credit", "term", "maturity", "par_amount",
    "outstanding_amount", "coupon", "call_date", "call_price",
    "fed_tax", "amt"
]

bond_display_cols = [c for c in bond_display_cols if c in issuer_bonds.columns]

if issuer_bonds.empty:
    st.info("No bonds found for this issuer.")
else:
    st.dataframe(
        issuer_bonds[bond_display_cols].sort_values(["maturity", "cusip"]),
        use_container_width=True
    )


# ============================================================
# Trade History Section
# ============================================================

st.header("Trade History")

if issuer_trades.empty:
    st.warning(
        "No trade rows found for this issuer and filter. "
        "This is normal in muni data. The bond master can still be used for security selection and peer analysis."
    )
else:
    trade_display_cols = [
        "trade_datetime", "cusip", "description", "maturity_trade",
        "maturity_bond", "maturity_bucket", "coupon_trade", "yield",
        "price", "trade_amount", "spread", "trade_type", "ratings_m_s_f"
    ]

    trade_display_cols = [c for c in trade_display_cols if c in issuer_trades.columns]

    st.dataframe(
        issuer_trades[trade_display_cols].sort_values("trade_datetime", ascending=False),
        use_container_width=True
    )

# ============================================================
# Yield Trend Comparison
# ============================================================

st.subheader("Yield Trend / Relative Value Comparison")

if market_df.empty:
    st.info("No trade data available for yield comparison.")
else:
    compare_issuers = st.multiselect(
        "Compare Issuers",
        options=sorted(market_df["issuer"].dropna().unique().tolist()),
        default=[selected_issuer] if selected_issuer else []
    )

    compare_bucket = st.selectbox(
        "Comparison Maturity Bucket",
        ["All", "Short", "10Y", "20Y", "30Y"],
        index=0
    )

    date_min = market_df["trade_date"].min().date()
    date_max = market_df["trade_date"].max().date()

    selected_dates = st.date_input(
        "Select Trade Date Range",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max
    )

    show_mmd = st.checkbox("Compare with MMD", value=True)

    chart_df = market_df[
        market_df["issuer"].isin(compare_issuers)
    ].copy()

    if compare_bucket != "All":
        chart_df = chart_df[chart_df["maturity_bucket"] == compare_bucket].copy()

    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
        chart_df = chart_df[
            (chart_df["trade_date"].dt.date >= start_date) &
            (chart_df["trade_date"].dt.date <= end_date)
        ].copy()

    if chart_df.empty:
        st.warning("No trade data found for the selected comparison filters.")
    else:
        issuer_yield_daily = (
            chart_df
            .groupby(["trade_date", "issuer"], as_index=False)
            .agg(
                avg_yield=("yield", "mean"),
                trade_count=("yield", "count"),
                total_trade_amount=("trade_amount", "sum")
            )
        )

        fig = px.line(
            issuer_yield_daily.sort_values("trade_date"),
            x="trade_date",
            y="avg_yield",
            color="issuer",
            markers=True,
            hover_data=["trade_count", "total_trade_amount"],
            title="Average Trade Yield by Issuer"
        )

        # Optional MMD comparison
        if show_mmd and not mmd_df.empty:
            mmd_plot = mmd_df.copy()

            date_col = "Date" if "Date" in mmd_plot.columns else "date"
            if date_col in mmd_plot.columns:
                mmd_plot[date_col] = pd.to_datetime(mmd_plot[date_col], errors="coerce")

                if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                    mmd_plot = mmd_plot[
                        (mmd_plot[date_col].dt.date >= start_date) &
                        (mmd_plot[date_col].dt.date <= end_date)
                    ]

                mmd_bucket_map = {
                    "Short": "5Y",
                    "10Y": "10Y",
                    "20Y": "20Y",
                    "30Y": "30Y",
                    "All": "10Y"
                }

                mmd_col = mmd_bucket_map.get(compare_bucket, "10Y")

                if mmd_col in mmd_plot.columns:
                    fig.add_scatter(
                        x=mmd_plot[date_col],
                        y=mmd_plot[mmd_col],
                        mode="lines",
                        name=f"MMD {mmd_col}",
                        line=dict(dash="dash")
                    )
                else:
                    st.info(f"MMD column '{mmd_col}' not found in mmd.csv.")

        fig.update_layout(
            xaxis_title="Trade Date",
            yaxis_title="Yield (%)",
            legend_title="Issuer / Benchmark",
            hovermode="x unified"
        )

        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Trading Frequency by CUSIP")

freq_fig = px.bar(
    liq.sort_values("trade_count", ascending=False).head(25),
    x="cusip",
    y="trade_count",
    color="liquidity_tier",
    hover_data=[
        "recent_90d_trades",
        "avg_trades_per_month",
        "days_since_last_trade",
        "total_trade_amount"
    ],
    title="Top 25 Most Frequently Traded CUSIPs"
)

freq_fig.update_layout(
    xaxis_title="CUSIP",
    yaxis_title="Trade Count",
    legend_title="Liquidity Tier"
)

st.plotly_chart(freq_fig, use_container_width=True)


st.subheader("Recent Activity vs Total Volume")

volume_fig = px.scatter(
    liq,
    x="days_since_last_trade",
    y="total_trade_amount",
    size="trade_count",
    color="liquidity_tier",
    hover_data=[
        "cusip",
        "recent_90d_trades",
        "avg_days_between_trades",
        "avg_yield",
        "maturity"
    ],
    title="Liquidity Map: Recency vs Trading Volume"
)

volume_fig.update_layout(
    xaxis_title="Days Since Last Trade",
    yaxis_title="Total Trade Amount",
    legend_title="Liquidity Tier"
)

st.plotly_chart(volume_fig, use_container_width=True)

# ============================================================
# Liquidity Visualizations
# ============================================================

if not liq.empty:

    # --------------------------------------------------------
    # Trading Frequency
    # --------------------------------------------------------

    st.subheader("Trading Frequency by CUSIP")

    freq_fig = px.bar(
        liq.sort_values("trade_count", ascending=False).head(25),
        x="cusip",
        y="trade_count",
        color="liquidity_tier",
        hover_data=[
            "recent_90d_trades",
            "avg_trades_per_month",
            "avg_days_between_trades",
            "days_since_last_trade",
            "total_trade_amount",
            "avg_trade_amount",
            "avg_yield",
            "maturity"
        ],
        title="Top 25 Most Frequently Traded CUSIPs"
    )

    freq_fig.update_layout(
        xaxis_title="CUSIP",
        yaxis_title="Trade Count",
        legend_title="Liquidity Tier",
        xaxis_tickangle=-45
    )

    st.plotly_chart(freq_fig, use_container_width=True)


    # --------------------------------------------------------
    # Liquidity Map
    # --------------------------------------------------------

    st.subheader("Recent Activity vs Total Volume")

    volume_fig = px.scatter(
        liq,
        x="days_since_last_trade",
        y="total_trade_amount",
        size="trade_count",
        color="liquidity_tier",
        hover_data=[
            "cusip",
            "recent_90d_trades",
            "avg_days_between_trades",
            "avg_yield",
            "yield_range",
            "avg_trade_amount",
            "turnover_ratio",
            "maturity"
        ],
        title="Liquidity Map: Recency vs Trading Volume"
    )

    volume_fig.update_layout(
        xaxis_title="Days Since Last Trade",
        yaxis_title="Total Trade Amount",
        legend_title="Liquidity Tier"
    )

    st.plotly_chart(volume_fig, use_container_width=True)


    # --------------------------------------------------------
    # Trade Recency Histogram
    # --------------------------------------------------------

    st.subheader("Trade Recency Distribution")

    recency_fig = px.histogram(
        liq,
        x="days_since_last_trade",
        nbins=30,
        color="liquidity_tier",
        title="Distribution of Days Since Last Trade"
    )

    recency_fig.update_layout(
        xaxis_title="Days Since Last Trade",
        yaxis_title="Number of CUSIPs"
    )

    st.plotly_chart(recency_fig, use_container_width=True)


    # --------------------------------------------------------
    # Yield Stability
    # --------------------------------------------------------

    st.subheader("Yield Stability vs Liquidity")

    stability_fig = px.scatter(
        liq,
        x="yield_range",
        y="trade_count",
        size="total_trade_amount",
        color="liquidity_tier",
        hover_data=[
            "cusip",
            "avg_yield",
            "days_since_last_trade",
            "avg_trade_amount"
        ],
        title="Yield Volatility vs Trading Frequency"
    )

    stability_fig.update_layout(
        xaxis_title="Yield Range",
        yaxis_title="Trade Count"
    )

    st.plotly_chart(stability_fig, use_container_width=True)


# ============================================================
# Raw Tables
# ============================================================

if show_raw_tables:
    st.header("Raw Loaded Data")

    st.subheader("Issuer Master")
    st.dataframe(issuer_master, use_container_width=True)

    st.subheader("All Bonds")
    st.dataframe(bonds_df, use_container_width=True)

    st.subheader("All Trades")
    if market_df.empty:
        st.info("No trade files loaded.")
    else:
        st.dataframe(market_df, use_container_width=True)

    st.subheader("MMD")
    if mmd_df.empty:
        st.info("No MMD file loaded.")
    else:
        st.dataframe(mmd_df, use_container_width=True)
