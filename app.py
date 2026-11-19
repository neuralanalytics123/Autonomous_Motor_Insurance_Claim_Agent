import datetime
import io
from pathlib import Path
import uuid
from dotenv import load_dotenv
import pandas as pd
import streamlit as st

load_dotenv()

from agents.policy_rules import PERIL_SCHEDULE
from core.schemas import ALL_9_CLAIM_TYPES, FRIENDLY_PERIL_LABELS, ClaimIntakeRequest, ClaimStatus
from data_loader.portfolio import RISK_LABELS, lookup_policy_record, parse_uploaded_claims_csv
from db.session import (
    evaluate_and_save_batch,
    evaluate_and_save_claim,
    human_decide_claim,
    list_saved_claims,
)
from notifications.company_notify import list_company_alerts
from rag.ingest import ingest_policies

PROOF_ROOT = Path("data/claim_proofs")

st.set_page_config(
    page_title="Motor Claim Request & Approval",
    page_icon="🛡️",
    layout="wide",
)


@st.cache_resource
def _init_policy_index() -> int:
    return ingest_policies()


_init_policy_index()

st.title("Motor Claim Request & Approval")
st.caption(
    "Request a motor insurance claim in Indian Rupees (₹), send approval requests and updates "
    "to the company by email, and review or approve claims in one place."
)

tab_claim, tab_hitl, tab_company, tab_rules, tab_csv, tab_history = st.tabs(
    [
        "Request a Claim",
        "Company Approval",
        "Company Emails",
        "Coverage & Rules",
        "Upload CSV Claims",
        "Claim History",
    ]
)

with tab_claim:
    st.subheader("Request a New Claim")

    p_col1, p_col2 = st.columns([1, 2])
    policy_id = int(
        p_col1.number_input(
            "Policy Number",
            min_value=1,
            value=1,
            step=1,
            help="Enter a policy number to check policy status and details.",
        )
    )
    policy_rec = lookup_policy_record(policy_id)
    if policy_rec:
        p_col2.success(policy_rec["status_note"])
    else:
        p_col2.warning(f"Policy #{policy_id} was not found in saved policies; using the values you enter below.")

    with st.form("real_world_claim_form"):
        st.markdown("#### 1. Your Contact Details")
        c1, c2, c3 = st.columns(3)
        customer_name = c1.text_input("Your Name", value="Imaya")
        customer_email = c2.text_input("Your Email", value="neuralrush82@gmail.com")
        customer_phone = c3.text_input("Phone Number", value="+91-9876543210")

        st.markdown("#### 2. Incident & Cost Details (₹)")
        col1, col2 = st.columns(2)
        claims_type = col1.selectbox(
            "What happened?",
            options=ALL_9_CLAIM_TYPES,
            format_func=lambda x: FRIENDLY_PERIL_LABELS.get(x, x),
        )
        default_risk = policy_rec["type_risk"] if policy_rec else 3
        risk_options = [1, 2, 3, 4]
        vehicle_type = col2.selectbox(
            "Vehicle Type",
            options=risk_options,
            index=risk_options.index(default_risk) if default_risk in risk_options else 2,
            format_func=lambda k: RISK_LABELS.get(k, "Passenger Car"),
        )

        col3, col4 = st.columns(2)
        damage_cost = col3.number_input(
            "Estimated Repair / Damage Cost (₹)",
            min_value=1.0,
            value=76500.0,
            step=1000.0,
            help="Estimated cost to repair or replace what was damaged, in Indian Rupees.",
        )
        default_val = policy_rec["vehicle_value_inr"] if policy_rec else 1350000.0
        material_value = col4.number_input(
            "Current Value of Vehicle / Item (₹)",
            min_value=0.0,
            value=float(default_val),
            step=25000.0,
            help="Approximate current value of the vehicle or item before the incident, in Indian Rupees.",
        )

        st.markdown("#### 3. Important Dates")
        d1, d2, d3 = st.columns(3)
        incident_date = d1.date_input("When did it happen?", value=datetime.date.today())
        reported_date = d2.date_input("When are you reporting it?", value=datetime.date.today())
        payout_needed_date = d3.date_input(
            "When do you need the money?",
            value=datetime.date.today() + datetime.timedelta(days=7),
        )

        st.markdown("#### 4. Supporting Proof (Photos, Bills, Reports)")
        uploaded_proofs = st.file_uploader(
            "Upload photos, repair quotes, police reports, or medical bills",
            type=["png", "jpg", "jpeg", "pdf", "csv", "txt"],
            accept_multiple_files=True,
        )

        with st.expander("Policy Details (Optional — Auto-filled from Policy Number)"):
            o1, o2, o3, o4 = st.columns(4)
            seniority_years = o1.number_input(
                "Years with the company",
                min_value=0,
                max_value=60,
                value=int(policy_rec["seniority_years"]) if policy_rec else 2,
            )
            policies_in_force = o2.number_input(
                "Active policies right now",
                min_value=0,
                max_value=20,
                value=int(policy_rec["policies_in_force"]) if policy_rec else 1,
            )
            lapse_count = o3.number_input(
                "Past missed renewals",
                min_value=0,
                max_value=20,
                value=int(policy_rec["lapse_count"]) if policy_rec else 0,
            )
            annual_premium = o4.number_input(
                "Yearly Policy Payment (₹)",
                min_value=0.0,
                value=float(policy_rec["annual_premium_inr"]) if policy_rec else 25200.0,
                step=500.0,
            )
            notes = st.text_area(
                "Tell us briefly what happened",
                value="I am requesting a claim for this incident.",
                height=75,
            )

        submit_btn = st.form_submit_button("Request Claim & Notify Company", type="primary")

    if submit_btn:
        generated_ref = f"CLM-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        saved_proof_paths: list[str] = []
        if uploaded_proofs:
            claim_proof_dir = PROOF_ROOT / generated_ref
            claim_proof_dir.mkdir(parents=True, exist_ok=True)
            for uf in uploaded_proofs:
                target_file = claim_proof_dir / Path(uf.name).name
                target_file.write_bytes(uf.getvalue())
                saved_proof_paths.append(str(target_file))

        req = ClaimIntakeRequest(
            claim_id=generated_ref,
            policy_id=policy_id,
            customer_name=customer_name.strip(),
            customer_email=customer_email.strip(),
            customer_phone=customer_phone.strip(),
            claims_type=claims_type,
            claimed_amount=float(damage_cost),
            annual_premium=float(annual_premium),
            vehicle_value=float(material_value),
            type_risk=int(vehicle_type),
            seniority_years=int(seniority_years),
            policies_in_force=int(policies_in_force),
            lapse_count=int(lapse_count),
            policy_found=bool(policy_rec),
            policy_status_note=policy_rec["status_note"] if policy_rec else f"Entered manually for Policy #{policy_id}",
            policy_next_renewal=policy_rec.get("next_renewal_date", "") if policy_rec else "",
            policy_lapse_date=policy_rec.get("lapse_date", "") if policy_rec else "",
            incident_date=incident_date.isoformat(),
            reported_date=reported_date.isoformat(),
            payout_needed_date=payout_needed_date.isoformat(),
            proof_files=saved_proof_paths,
            description=notes.strip(),
        )
        decision = evaluate_and_save_claim(req)
        latest_alerts = list_company_alerts(limit=1)
        latest_email_status = latest_alerts[0]["email_detail"] if latest_alerts else "Saved to company alerts."

        st.divider()
        st.subheader("Your Claim Request Status")
        st.success(
            f"You requested claim **{decision.claim_id}** under **Policy #{decision.policy_id}** "
            f"for **₹{decision.claimed_amount:,.2f}**."
        )
        st.caption(f"Company email update: {latest_email_status}")

        if decision.status == ClaimStatus.REJECTED:
            st.error("Not Approved — We cannot pay out this claim.")
            st.write(f"**Why it was not approved:** {decision.rejection_reason}")
            if decision.policy_exclusions:
                for exc in decision.policy_exclusions:
                    st.write(f"- {exc}")
        elif decision.status == ClaimStatus.ESCALATED:
            st.warning("Company Approval Requested — Needs extra checks before the company approves payout.")
            st.write(f"**Why approval is needed:** {decision.rejection_reason}")
        elif decision.status == ClaimStatus.PENDING_REVIEW:
            st.warning("Company Approval Requested — Sent to the company for approval.")
            st.write(decision.settlement_summary)
        else:
            st.success("Approved — This claim is approved and the company has been notified.")
            st.write(decision.settlement_summary)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Status", decision.status.value.replace("_", " ").title())
        m2.metric("Payout Amount", f"₹{decision.recommended_payout:,.2f}")
        m3.metric("Your Deductible", f"₹{decision.deductible_applied:,.2f}")
        m4.metric("Coverage Limit", f"₹{decision.coverage_cap_applied:,.2f}")

        st.write(
            f"**What Happened:** {FRIENDLY_PERIL_LABELS.get(claims_type, claims_type)}  |  "
            f"**Incident Date:** {incident_date.strftime('%d %b %Y')}  |  "
            f"**Reported:** {reported_date.strftime('%d %b %Y')}  |  "
            f"**Money Needed By:** {payout_needed_date.strftime('%d %b %Y')}"
        )
        if saved_proof_paths:
            st.write("**Uploaded Proof:** " + ", ".join(saved_proof_paths))

with tab_hitl:
    st.subheader("Claims Waiting for Company Approval")
    st.write(
        "Review claims where company approval is requested. Clicking Approve or Reject "
        "saves the decision and sends an email update to the company."
    )
    all_claims = list_saved_claims(limit=200)
    pending_claims = [
        c
        for c in all_claims
        if c.requires_human_approval or c.status in {ClaimStatus.PENDING_REVIEW, ClaimStatus.ESCALATED}
    ]

    if not pending_claims:
        st.info("No claims are waiting for company approval right now.")
    else:
        for item in pending_claims:
            with st.container(border=True):
                st.markdown(
                    f"**{item.claim_id}** (Policy #{item.policy_id}) — "
                    f"{FRIENDLY_PERIL_LABELS.get(item.claims_type, item.claims_type)} ({item.vehicle_category})"
                )
                st.write(
                    f"Customer: **{item.customer_name or 'Not given'}** ({item.customer_email or 'No email'}, {item.customer_phone or 'No phone'})  |  "
                    f"Damage Cost: **₹{item.claimed_amount:,.2f}**  |  "
                    f"Your Deductible: **₹{item.deductible_applied:,.2f}**  |  "
                    f"Coverage Limit: **₹{item.coverage_cap_applied:,.2f}**"
                )
                if item.proof_files:
                    st.write("Proof Files: " + ", ".join(item.proof_files))
                if item.rejection_reason:
                    st.write(f"Review Note / Reason: {item.rejection_reason}")
                note_key = f"note_{item.claim_id}"
                reviewer_note = st.text_input(
                    "Note for Company Record & Email",
                    key=note_key,
                    placeholder="Optional note explaining approval or rejection",
                )
                b1, b2 = st.columns(2)
                if b1.button("Approve & Email Company", key=f"approve_{item.claim_id}", type="primary"):
                    human_decide_claim(item.claim_id, approve=True, reviewer_note=reviewer_note)
                    st.rerun()
                if b2.button("Reject & Email Company", key=f"reject_{item.claim_id}"):
                    human_decide_claim(item.claim_id, approve=False, reviewer_note=reviewer_note)
                    st.rerun()

with tab_company:
    st.subheader("Company Emails & Notifications")
    st.write(
        "Emails are sent whenever a claim is requested (asking for company approval when needed) "
        "and whenever a claim is approved or rejected. Every alert is also saved in `company_claim_alerts.jsonl`."
    )
    alerts = list_company_alerts(limit=100)
    if not alerts:
        st.write("No company notifications sent yet.")
    else:
        summary_rows = [
            {
                "Time (UTC)": a.get("timestamp", ""),
                "Update Type": a.get("event", ""),
                "Sent To": a.get("recipient_email", ""),
                "Claim ID": a.get("claim_id", ""),
                "Policy #": a.get("policy_id", ""),
                "Status": a.get("status", ""),
                "Approval Asked?": "Yes" if a.get("approval_requested_from_company") else "No",
                "Damage (₹)": a.get("claimed_amount_inr", 0.0),
                "Payout (₹)": a.get("recommended_payout_inr", 0.0),
                "Email Status": a.get("email_status", ""),
                "Details": a.get("email_detail", ""),
            }
            for a in alerts
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        with st.expander("View Latest Email"):
            latest = alerts[0]
            st.write(f"**To:** {latest.get('recipient_email', '')}")
            st.write(f"**Subject:** {latest.get('email_subject', '')}")
            st.code(latest.get("email_body", ""), language="text")

with tab_rules:
    st.subheader("How Claims Are Checked & What Is Not Covered")
    st.write(
        "We check whether the policy is active, whether renewals were kept up to date, "
        "how much the item or vehicle is worth, and the limit for each type of claim in Indian Rupees (₹)."
    )

    st.markdown("### When a Claim Cannot Be Approved or Needs Extra Checks")
    st.markdown(
        "- **Policy Not Found:** The policy number does not match an active policy in our records.\n"
        "- **Inactive Policy:** A past renewal was missed and there is no active policy in place.\n"
        "- **Repeated Missed Renewals:** Three or more past missed renewals exclude standard claims (except roadside help and injury claims).\n"
        "- **Extra Checks Needed:** Claims with unusual patterns, very high damage compared to value, or missing proof above ₹50,000 are sent for company approval first.\n"
        "- **Deductible & Limit:** Any payout cannot go above the coverage limit or vehicle value, and your deductible is subtracted first."
    )

    st.markdown("### Claim Types & Standard Rules (in ₹)")
    rules_rows = []
    for key, rule in PERIL_SCHEDULE.items():
        cap_label = (
            "Up to Current Vehicle Value (adjusted by vehicle type)"
            if rule.use_vehicle_value_cap
            else f"Up to ₹{rule.default_cap:,.2f}"
        )
        rules_rows.append(
            {
                "What Happened": FRIENDLY_PERIL_LABELS.get(key, key),
                "Rule Code": rule.clause_id,
                "Standard Deductible": f"₹{rule.base_deductible:,.2f} (25% off after 5+ yrs)",
                "Maximum Limit": cap_label,
                "Company Approval": "Always required" if rule.mandatory_hitl else "Required before payout",
                "What It Covers": rule.description,
            }
        )
    st.dataframe(pd.DataFrame(rules_rows), use_container_width=True, hide_index=True)

with tab_csv:
    st.subheader("Upload a CSV File of Claims")
    st.write(
        "Upload a CSV file (separated by commas or semicolons) to check multiple claims at once. "
        "Include columns like `Claims_type` and `Cost_claims_by_type`."
    )
    uploaded_csv = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded_csv is not None and st.button("Check Uploaded Claims", type="primary"):
        with st.spinner("Checking claims..."):
            reqs = parse_uploaded_claims_csv(uploaded_csv.getvalue())
            decisions = evaluate_and_save_batch(reqs)
        st.success(f"Checked {len(decisions)} claims from {uploaded_csv.name}.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Claim ID": d.claim_id,
                        "Policy #": d.policy_id,
                        "What Happened": FRIENDLY_PERIL_LABELS.get(d.claims_type, d.claims_type),
                        "Damage Cost (₹)": round(d.claimed_amount, 2),
                        "Deductible (₹)": round(d.deductible_applied, 2),
                        "Payout (₹)": round(d.recommended_payout, 2),
                        "Status": d.status.value.replace("_", " ").title(),
                        "Notes": d.rejection_reason or d.settlement_summary,
                    }
                    for d in decisions
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

with tab_history:
    st.subheader("All Checked Claims & Step-by-Step History")
    rows = list_saved_claims(limit=200)
    if not rows:
        st.write("No claims checked yet. Submit a claim in the first tab to see it here.")
    else:
        hist_df = pd.DataFrame(
            [
                {
                    "Claim ID": r.claim_id,
                    "Policy #": r.policy_id,
                    "Customer": r.customer_name or "-",
                    "What Happened": FRIENDLY_PERIL_LABELS.get(r.claims_type, r.claims_type),
                    "Vehicle": r.vehicle_category,
                    "Damage Cost (₹)": round(r.claimed_amount, 2),
                    "Deductible (₹)": round(r.deductible_applied, 2),
                    "Payout (₹)": round(r.recommended_payout, 2),
                    "Status": r.status.value.replace("_", " ").title(),
                    "Incident Date": r.incident_date or "-",
                    "Money Needed By": r.payout_needed_date or "-",
                    "Proof Files": len(r.proof_files),
                    "Notes": r.rejection_reason or r.settlement_summary,
                }
                for r in rows
            ]
        )
        st.dataframe(hist_df, use_container_width=True, hide_index=True)

        selected_claim_id = st.selectbox(
            "See Step-by-Step Notes for Claim",
            options=[r.claim_id for r in rows],
        )
        chosen = next((r for r in rows if r.claim_id == selected_claim_id), None)
        if chosen and chosen.audit_log:
            st.json(chosen.audit_log)

        csv_bytes = hist_df.to_csv(index=False).encode("utf-8")
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            hist_df.to_excel(writer, index=False, sheet_name="ClaimDecisions")
        excel_buf.seek(0)

        c_a, c_b = st.columns(2)
        c_a.download_button(
            "Download as CSV",
            data=csv_bytes,
            file_name="claim_decisions.csv",
            mime="text/csv",
        )
        c_b.download_button(
            "Download as Excel",
            data=excel_buf.getvalue(),
            file_name="claim_decisions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )