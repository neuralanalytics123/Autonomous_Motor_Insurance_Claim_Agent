from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

ALL_9_CLAIM_TYPES = [
    "travel assistance",
    "complaint",
    "broken windows",
    "negligence",
    "all risks",
    "theft",
    "injuries",
    "fire",
    "other",
]

FRIENDLY_PERIL_LABELS = {
    "travel assistance": "Roadside & Travel Help",
    "complaint": "Service Complaint",
    "broken windows": "Broken Glass & Windscreen",
    "negligence": "Driver Fault / Liability",
    "all risks": "All-Risks Vehicle Damage",
    "theft": "Vehicle Theft",
    "injuries": "Personal Injury",
    "fire": "Fire Damage",
    "other": "Other Motor Claim",
}


class ClaimStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"


class ClaimIntakeRequest(BaseModel):
    claim_id: str = Field(default="AUTO-CLAIM", min_length=2)
    policy_id: int = Field(default=1, ge=1)
    customer_name: str = Field(default="")
    customer_email: str = Field(default="")
    customer_phone: str = Field(default="")
    claims_type: str = Field(..., min_length=2)
    claimed_amount: float = Field(..., gt=0)
    annual_premium: float = Field(default=25000.0, ge=0)
    type_risk: int = Field(default=3, ge=1, le=4)
    area: int = Field(default=1, ge=0, le=1)
    seniority_years: int = Field(default=1, ge=0)
    policies_in_force: int = Field(default=1, ge=0)
    lapse_count: int = Field(default=0, ge=0)
    payment_mode: int = Field(default=0, ge=0, le=1)
    n_claims_year: int = Field(default=0, ge=0)
    n_claims_history: int = Field(default=0, ge=0)
    r_claims_history: float = Field(default=0.0, ge=0.0)
    vehicle_value: float = Field(default=1350000.0, ge=0.0)
    vehicle_power_hp: int = Field(default=100, ge=0)
    year_matriculation: int = Field(default=2018, ge=1950)
    second_driver: int = Field(default=0, ge=0, le=1)
    distribution_channel: int = Field(default=0, ge=0, le=1)
    policy_found: bool = Field(default=True)
    policy_status_note: str = Field(default="")
    policy_next_renewal: str = Field(default="")
    policy_lapse_date: str = Field(default="")
    incident_date: str = Field(default="")
    reported_date: str = Field(default="")
    payout_needed_date: str = Field(default="")
    proof_files: list[str] = Field(default_factory=list)
    description: str = Field(default="")


class ClaimDecisionResponse(BaseModel):
    claim_id: str
    policy_id: int
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    claims_type: str
    vehicle_category: str
    status: ClaimStatus
    claimed_amount: float
    deductible_applied: float
    coverage_cap_applied: float
    recommended_payout: float
    fraud_score: float
    fraud_flags: list[str] = Field(default_factory=list)
    policy_exclusions: list[str] = Field(default_factory=list)
    cited_clauses: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    rejection_reason: str = ""
    incident_date: str = ""
    reported_date: str = ""
    payout_needed_date: str = ""
    proof_files: list[str] = Field(default_factory=list)
    settlement_summary: str = ""
    audit_log: list[dict[str, Any]] = Field(default_factory=list)