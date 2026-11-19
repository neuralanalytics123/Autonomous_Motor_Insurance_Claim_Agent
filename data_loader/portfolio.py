from functools import lru_cache
from pathlib import Path
import io
import pandas as pd
from core.schemas import ALL_9_CLAIM_TYPES, ClaimIntakeRequest

RAW_DIR = Path("data/raw")
MAIN_CSV = RAW_DIR / "Motor vehicle insurance data.csv"
SAMPLE_CLAIMS_CSV = RAW_DIR / "sample type claim.csv"
INR_SCALE_FACTOR = 90.0

RISK_LABELS = {
    1: "Motorbike",
    2: "Van",
    3: "Passenger Car",
    4: "Agricultural Vehicle",
}


@lru_cache(maxsize=1)
def load_portfolio_df() -> pd.DataFrame:
    df = pd.read_csv(MAIN_CSV, sep=";", low_memory=False)
    for col, default in [
        ("Cost_claims_year", 0.0),
        ("Premium", 280.0),
        ("Value_vehicle", 14000.0),
        ("R_Claims_history", 0.0),
        ("Power", 95),
        ("Year_matriculation", 2015),
        ("Seniority", 1),
        ("Policies_in_force", 1),
        ("Lapse", 0),
        ("Payment", 0),
        ("N_claims_year", 0),
        ("N_claims_history", 0),
        ("Type_risk", 3),
        ("Area", 1),
        ("Second_driver", 0),
        ("Distribution_channel", 0),
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
    for int_col in [
        "ID",
        "Type_risk",
        "Area",
        "Seniority",
        "Policies_in_force",
        "Lapse",
        "Payment",
        "N_claims_year",
        "N_claims_history",
        "Power",
        "Year_matriculation",
        "Second_driver",
        "Distribution_channel",
    ]:
        if int_col in df.columns:
            df[int_col] = df[int_col].astype(int)
    return df


@lru_cache(maxsize=1)
def load_typed_claims_df() -> pd.DataFrame:
    df = pd.read_csv(SAMPLE_CLAIMS_CSV, sep=";")
    df["Cost_claims_year"] = pd.to_numeric(df["Cost_claims_year"], errors="coerce").fillna(0.0)
    df["Cost_claims_by_type"] = pd.to_numeric(df["Cost_claims_by_type"], errors="coerce").fillna(0.0)
    df["Claims_type"] = df["Claims_type"].fillna("other").astype(str).str.strip().str.lower()
    return df


@lru_cache(maxsize=1)
def load_enriched_claims_df() -> pd.DataFrame:
    portfolio = load_portfolio_df()
    latest_policy = (
        portfolio.sort_values(by=["ID", "Cost_claims_year"], ascending=[True, False])
        .drop_duplicates(subset=["ID"], keep="first")
    )
    typed = load_typed_claims_df().reset_index().rename(columns={"index": "row_idx"})
    return typed.merge(latest_policy, on="ID", how="left", suffixes=("_claim", "_policy"))


def lookup_policy_record(policy_id: int) -> dict | None:
    df = load_portfolio_df()
    matches = df[df["ID"] == int(policy_id)]
    if matches.empty:
        return None
    row = matches.iloc[-1]
    lapse_count = int(row.get("Lapse", 0))
    policies_in_force = int(row.get("Policies_in_force", 0))
    date_lapse = str(row.get("Date_lapse", "") or "").strip()
    if pd.isna(row.get("Date_lapse")):
        date_lapse = ""
    date_next_renewal = str(row.get("Date_next_renewal", "") or "").strip()
    if pd.isna(row.get("Date_next_renewal")):
        date_next_renewal = ""

    is_active = policies_in_force > 0 and not (lapse_count > 0 and policies_in_force <= 0)
    status_note = (
        f"Active policy (#{int(policy_id)}) — {policies_in_force} in force, {lapse_count} past lapse(s)."
        if is_active
        else f"Policy (#{int(policy_id)}) inactive/lapsed — {policies_in_force} in force, {lapse_count} past lapse(s)."
    )

    return {
        "policy_id": int(policy_id),
        "found": True,
        "is_active": is_active,
        "status_note": status_note,
        "type_risk": int(row.get("Type_risk", 3)),
        "area": int(row.get("Area", 1)),
        "seniority_years": int(row.get("Seniority", 1)),
        "policies_in_force": policies_in_force,
        "lapse_count": lapse_count,
        "payment_mode": int(row.get("Payment", 0)),
        "n_claims_year": int(row.get("N_claims_year", 0)),
        "n_claims_history": int(row.get("N_claims_history", 0)),
        "r_claims_history": round(float(row.get("R_Claims_history", 0.0)), 4),
        "annual_premium_inr": round(float(row.get("Premium", 280.0)) * INR_SCALE_FACTOR, 2),
        "vehicle_value_inr": round(float(row.get("Value_vehicle", 14000.0)) * INR_SCALE_FACTOR, 2),
        "vehicle_power_hp": int(row.get("Power", 95)),
        "year_matriculation": int(row.get("Year_matriculation", 2015)),
        "second_driver": int(row.get("Second_driver", 0)),
        "distribution_channel": int(row.get("Distribution_channel", 0)),
        "next_renewal_date": date_next_renewal,
        "lapse_date": date_lapse,
    }


def row_to_claim_request(row: pd.Series) -> ClaimIntakeRequest:
    policy_id = int(row.get("ID", 1))
    row_idx = int(row.get("row_idx", 0))
    raw_type = str(row.get("Claims_type", "other")).strip().lower()
    claims_type = raw_type if raw_type in ALL_9_CLAIM_TYPES else "other"

    raw_amt = row.get("Cost_claims_by_type")
    if pd.isna(raw_amt):
        raw_amt = row.get("Cost_claims_year_claim")
    if pd.isna(raw_amt):
        raw_amt = row.get("Cost_claims_year")
    amount_inr = max(round(float(raw_amt if pd.notna(raw_amt) else 150.0) * INR_SCALE_FACTOR, 2), 1.0)

    type_risk = int(row["Type_risk"]) if pd.notna(row.get("Type_risk")) else 3
    area = int(row["Area"]) if pd.notna(row.get("Area")) else 1
    seniority = int(row["Seniority"]) if pd.notna(row.get("Seniority")) else 1
    policies_in_force = int(row["Policies_in_force"]) if pd.notna(row.get("Policies_in_force")) else 1
    lapse = int(row["Lapse"]) if pd.notna(row.get("Lapse")) else 0
    payment_mode = int(row["Payment"]) if pd.notna(row.get("Payment")) else 0
    n_claims_year = int(row["N_claims_year"]) if pd.notna(row.get("N_claims_year")) else 1
    n_claims_hist = int(row["N_claims_history"]) if pd.notna(row.get("N_claims_history")) else 1
    r_claims_hist = float(row["R_Claims_history"]) if pd.notna(row.get("R_Claims_history")) else 0.25
    premium_inr = float(row["Premium"]) * INR_SCALE_FACTOR if pd.notna(row.get("Premium")) else 25200.0
    veh_val_inr = float(row["Value_vehicle"]) * INR_SCALE_FACTOR if pd.notna(row.get("Value_vehicle")) else 1260000.0
    power = int(row["Power"]) if pd.notna(row.get("Power")) else 95
    yr_mat = int(row["Year_matriculation"]) if pd.notna(row.get("Year_matriculation")) else 2015
    second_driver = int(row["Second_driver"]) if pd.notna(row.get("Second_driver")) else 0
    channel = int(row["Distribution_channel"]) if pd.notna(row.get("Distribution_channel")) else 0

    veh_label = RISK_LABELS.get(type_risk, "Passenger Car")
    area_label = "Urban" if area == 1 else "Rural"
    desc = (
        f"Motor claim ({claims_type}) on Policy #{policy_id} for {veh_label} "
        f"({power} HP, Reg {yr_mat}, Market Value ₹{veh_val_inr:,.2f}) in {area_label} area."
    )

    return ClaimIntakeRequest(
        claim_id=f"CLM-{policy_id}-{row_idx + 1}",
        policy_id=policy_id,
        claims_type=claims_type,
        claimed_amount=amount_inr,
        annual_premium=round(premium_inr, 2),
        type_risk=type_risk,
        area=area,
        seniority_years=seniority,
        policies_in_force=policies_in_force,
        lapse_count=lapse,
        payment_mode=payment_mode,
        n_claims_year=n_claims_year,
        n_claims_history=n_claims_hist,
        r_claims_history=round(r_claims_hist, 4),
        vehicle_value=round(veh_val_inr, 2),
        vehicle_power_hp=power,
        year_matriculation=yr_mat,
        second_driver=second_driver,
        distribution_channel=channel,
        policy_found=True,
        policy_status_note=f"Portfolio Policy #{policy_id} loaded.",
        description=desc,
    )


def get_sample_claim_requests(limit: int = 25, claims_type: str | None = None) -> list[ClaimIntakeRequest]:
    df = load_enriched_claims_df()
    if claims_type and claims_type.lower() != "all":
        df = df[df["Claims_type"] == claims_type.lower()]
    return [row_to_claim_request(row) for _, row in df.head(limit).iterrows()]


def parse_uploaded_claims_csv(raw_bytes: bytes) -> list[ClaimIntakeRequest]:
    text = raw_bytes.decode("utf-8", errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ";"
    sep = ";" if first_line.count(";") >= first_line.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep)
    df = df.reset_index().rename(columns={"index": "row_idx"})
    if "ID" not in df.columns and "policy_id" in df.columns:
        df["ID"] = df["policy_id"]
    if "ID" not in df.columns:
        df["ID"] = range(1000, 1000 + len(df))
    if "Claims_type" not in df.columns and "claims_type" in df.columns:
        df["Claims_type"] = df["claims_type"]
    if "Claims_type" not in df.columns:
        df["Claims_type"] = "all risks"
    if "Cost_claims_by_type" not in df.columns and "claimed_amount" in df.columns:
        df["Cost_claims_by_type"] = df["claimed_amount"]
    return [row_to_claim_request(row) for _, row in df.head(500).iterrows()]


def get_portfolio_stats() -> dict:
    portfolio = load_portfolio_df()
    typed = load_typed_claims_df()
    type_counts = typed["Claims_type"].value_counts().to_dict()
    veh_counts = {
        RISK_LABELS.get(int(k), str(k)): int(v)
        for k, v in portfolio["Type_risk"].value_counts().to_dict().items()
    }
    return {
        "total_portfolio_rows": int(len(portfolio)),
        "active_claim_rows": int((portfolio["Cost_claims_year"] > 0).sum()),
        "sample_typed_claims": int(len(typed)),
        "claims_type_breakdown": {str(k): int(v) for k, v in type_counts.items()},
        "vehicle_type_breakdown": veh_counts,
    }