from core.schemas import ALL_9_CLAIM_TYPES, ClaimIntakeRequest
from db.session import evaluate_and_save_claim


def test_all_9_perils_flow():
    for idx, peril in enumerate(ALL_9_CLAIM_TYPES, start=1):
        req = ClaimIntakeRequest(
            claim_id=f"CLM-APP-{idx}",
            policy_id=700 + idx,
            claims_type=peril,
            claimed_amount=350.0,
            seniority_years=6,
            policies_in_force=1,
            lapse_count=0,
            vehicle_value=17000.0,
            description=f"Check {peril}",
        )
        res = evaluate_and_save_claim(req)
        assert res.claim_id == f"CLM-APP-{idx}"
        assert res.recommended_payout >= 0.0
