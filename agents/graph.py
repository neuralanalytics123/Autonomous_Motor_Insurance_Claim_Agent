from typing import Annotated, TypedDict
from langgraph.graph import END, START, StateGraph
from agents.policy_rules import VEHICLE_RISK_MULTIPLIER, get_peril_rule
from core.config import settings
from core.schemas import ClaimStatus
from data_loader.portfolio import RISK_LABELS
from rag.retriever import search_policy_clauses


def merge_logs(left: list[dict], right: list[dict]) -> list[dict]:
    return (left or []) + (right or [])


class ClaimState(TypedDict):
    claim_id: str
    policy_id: int
    customer_name: str
    customer_email: str
    customer_phone: str
    claims_type: str
    claimed_amount: float
    annual_premium: float
    type_risk: int
    area: int
    seniority_years: int
    policies_in_force: int
    lapse_count: int
    payment_mode: int
    n_claims_year: int
    n_claims_history: int
    r_claims_history: float
    vehicle_value: float
    vehicle_power_hp: int
    year_matriculation: int
    second_driver: int
    distribution_channel: int
    policy_found: bool
    policy_status_note: str
    policy_next_renewal: str
    policy_lapse_date: str
    incident_date: str
    reported_date: str
    payout_needed_date: str
    proof_files: list[str]
    description: str

    auto_approve_threshold: float
    fraud_score_threshold: float
    vehicle_category: str
    policy_clauses: list[dict]
    covered: bool
    policy_exclusions: list[str]
    deductible_applied: float
    coverage_cap_applied: float
    fraud_score: float
    fraud_flags: list[str]
    recommended_payout: float
    status: str
    requires_human_approval: bool
    rejection_reason: str
    settlement_summary: str
    audit_log: Annotated[list[dict], merge_logs]


def intake_node(state: ClaimState) -> dict:
    veh_cat = RISK_LABELS.get(state["type_risk"], "Passenger Car")
    proof_count = len(state.get("proof_files") or [])
    policy_src = state.get("policy_status_note") or f"Policy #{state['policy_id']}"
    return {
        "vehicle_category": veh_cat,
        "audit_log": [
            {
                "stage": "Claim Received",
                "detail": (
                    f"Received claim {state['claim_id']} under {policy_src} for a {veh_cat} "
                    f"({state['claims_type']}). Estimated repair/damage cost: ₹{state['claimed_amount']:,.2f}; "
                    f"current vehicle value: ₹{state['vehicle_value']:,.2f}; "
                    f"incident date: {state.get('incident_date') or 'Not given'}; "
                    f"payout needed by: {state.get('payout_needed_date') or 'Not given'}; "
                    f"supporting files attached: {proof_count}."
                ),
            }
        ],
    }


def policy_rag_node(state: ClaimState) -> dict:
    veh_cat = RISK_LABELS.get(state["type_risk"], "Passenger Car")
    rule = get_peril_rule(state["claims_type"])
    query = (
        f"{rule.clause_id} {state['claims_type']} {veh_cat} deductible exclusion cap "
        f"lapse seniority {state['description']}"
    )
    try:
        clauses = search_policy_clauses(query=query, top_k=3)
    except Exception:
        clauses = []

    matched_ids = [c.get("clause_id", "") for c in clauses]
    if rule.clause_id not in matched_ids:
        clauses.insert(
            0,
            {
                "clause_id": rule.clause_id,
                "source": "comprehensive_motor_policy_schedule.md",
                "text": rule.description,
                "score": 1.0,
            },
        )

    exclusions: list[str] = []
    if not state.get("policy_found", True):
        exclusions.append(f"Policy #{state['policy_id']} was not found in our active policy records.")

    if state["lapse_count"] > 0 and state["policies_in_force"] <= 0:
        exclusions.append("This policy is no longer active because a past renewal was missed.")

    if state["lapse_count"] >= 3 and state["claims_type"] not in {"travel assistance", "injuries"}:
        exclusions.append(
            "Three or more past missed renewals exclude standard claims (except roadside help and injury claims)."
        )

    covered = len(exclusions) == 0

    deductible = rule.base_deductible
    if state["seniority_years"] >= 5 and deductible > 0:
        deductible = round(deductible * 0.75, 2)

    veh_mult = VEHICLE_RISK_MULTIPLIER.get(state["type_risk"], 1.0)
    if rule.use_vehicle_value_cap:
        base_val = state["vehicle_value"] if state["vehicle_value"] > 0 else rule.default_cap
        cap = round(base_val * veh_mult, 2)
    else:
        cap = round(rule.default_cap * (veh_mult if state["claims_type"] == "negligence" else 1.0), 2)

    coverage_text = "Covered" if covered else "Not covered"
    return {
        "policy_clauses": clauses[:3],
        "covered": covered,
        "policy_exclusions": exclusions,
        "deductible_applied": deductible,
        "coverage_cap_applied": cap,
        "audit_log": [
            {
                "stage": "Policy & Cover Check",
                "detail": (
                    f"Checked rule {rule.clause_id}: {coverage_text}. "
                    f"Customer share (deductible): ₹{deductible:,.2f}; "
                    f"maximum payout limit: ₹{cap:,.2f}."
                ),
            }
        ],
    }


def actuarial_fraud_node(state: ClaimState) -> dict:
    reasons: list[str] = []
    score = 0.06

    premium = max(state["annual_premium"], 4500.0)
    if state["claimed_amount"] > premium * 8.0:
        reasons.append("Claim amount is much higher than 8 times the yearly policy payment")
        score += 0.25

    if state["vehicle_value"] > 0 and state["claimed_amount"] > state["vehicle_value"] * 0.90:
        reasons.append("Damage cost is over 90% of the vehicle's current value")
        score += 0.30

    if state["n_claims_year"] >= 4:
        reasons.append("4 or more claims already made this year")
        score += 0.22

    if state["r_claims_history"] > 2.0:
        reasons.append("Frequent past claims on this policy")
        score += 0.18

    if (
        state["seniority_years"] <= 1
        and state["claims_type"] in {"theft", "fire", "all risks", "negligence"}
        and state["claimed_amount"] > 270000.0
    ):
        reasons.append("Large claim on a policy that is less than a year old")
        score += 0.25

    if state["lapse_count"] > 0 and state["policies_in_force"] == 0:
        reasons.append("Claim submitted on an inactive policy")
        score += 0.20

    if len(state.get("proof_files") or []) == 0 and state["claimed_amount"] > 50000.0:
        reasons.append("No photos, bills, or supporting proof uploaded for a claim over ₹50,000")
        score += 0.15

    score = min(round(score, 2), 1.0)
    notes_text = ", ".join(reasons) if reasons else "No extra checks needed"
    return {
        "fraud_score": score,
        "fraud_flags": reasons,
        "audit_log": [
            {
                "stage": "Extra Verification Check",
                "detail": f"Verification score: {score:.2f} out of 1.00. Notes: {notes_text}.",
            }
        ],
    }


def adjudicate_node(state: ClaimState) -> dict:
    fraud_limit = state.get("fraud_score_threshold") or settings.fraud_score_threshold

    if not state.get("covered", True):
        reason = (
            " ; ".join(state.get("policy_exclusions", []))
            or "This claim is not covered under the current policy rules."
        )
        summary = f"Claim Rejected — We cannot approve a payout. Reason: {reason}"
        return {
            "recommended_payout": 0.0,
            "status": ClaimStatus.REJECTED.value,
            "requires_human_approval": False,
            "rejection_reason": reason,
            "settlement_summary": summary,
            "audit_log": [{"stage": "Final Decision", "detail": summary}],
        }

    if state["fraud_score"] >= fraud_limit:
        reason = (
            f"Extra review needed (score {state['fraud_score']:.2f} reached {fraud_limit:.2f}) because: "
            f"{', '.join(state.get('fraud_flags', [])) or 'unusual claim details'}."
        )
        summary = f"Waiting for Company Approval — Sent to the company team for extra checks. Reason: {reason}"
        return {
            "recommended_payout": 0.0,
            "status": ClaimStatus.ESCALATED.value,
            "requires_human_approval": True,
            "rejection_reason": reason,
            "settlement_summary": summary,
            "audit_log": [{"stage": "Final Decision", "detail": summary}],
        }

    capped_claim = min(state["claimed_amount"], state["coverage_cap_applied"])
    proposed_payout = max(0.0, round(capped_claim - state["deductible_applied"], 2))
    payout_note = f" (needed by {state['payout_needed_date']})" if state.get("payout_needed_date") else ""
    summary = (
        f"Waiting for Company Approval — Proposed payout is ₹{proposed_payout:,.2f}{payout_note}, "
        f"after ₹{state['deductible_applied']:,.2f} deductible and a ₹{state['coverage_cap_applied']:,.2f} coverage limit."
    )

    return {
        "recommended_payout": proposed_payout,
        "status": ClaimStatus.PENDING_REVIEW.value,
        "requires_human_approval": True,
        "rejection_reason": "",
        "settlement_summary": summary,
        "audit_log": [{"stage": "Final Decision", "detail": summary}],
    }


def build_claim_graph():
    builder = StateGraph(ClaimState)
    builder.add_node("intake", intake_node)
    builder.add_node("policy_rag", policy_rag_node)
    builder.add_node("actuarial_fraud", actuarial_fraud_node)
    builder.add_node("adjudicate", adjudicate_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "policy_rag")
    builder.add_edge("intake", "actuarial_fraud")
    builder.add_edge("policy_rag", "adjudicate")
    builder.add_edge("actuarial_fraud", "adjudicate")
    builder.add_edge("adjudicate", END)

    return builder.compile()


claim_graph = build_claim_graph()