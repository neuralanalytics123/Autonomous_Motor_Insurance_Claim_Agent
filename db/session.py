import asyncio
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from agents.graph import claim_graph
from core.config import settings
from core.schemas import ClaimDecisionResponse, ClaimIntakeRequest, ClaimStatus
from db.models import Base, ClaimRecord
from notifications.company_notify import notify_company_of_claim

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_DB_READY = False


async def _ensure_db_async() -> None:
    global _DB_READY
    if not _DB_READY:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _DB_READY = True


async def _evaluate_and_save_async(payload: ClaimIntakeRequest) -> ClaimDecisionResponse:
    await _ensure_db_async()
    initial_state = {
        **payload.model_dump(),
        "auto_approve_threshold": settings.auto_approve_threshold,
        "fraud_score_threshold": settings.fraud_score_threshold,
        "vehicle_category": "",
        "policy_clauses": [],
        "covered": True,
        "policy_exclusions": [],
        "deductible_applied": 0.0,
        "coverage_cap_applied": 25000.0,
        "fraud_score": 0.0,
        "fraud_flags": [],
        "recommended_payout": 0.0,
        "status": ClaimStatus.PENDING_REVIEW.value,
        "requires_human_approval": False,
        "rejection_reason": "",
        "settlement_summary": "",
        "audit_log": [],
    }
    result = await claim_graph.ainvoke(initial_state)
    cited = [c.get("clause_id", "CLAUSE") for c in result.get("policy_clauses", [])]

    decision = ClaimDecisionResponse(
        claim_id=payload.claim_id,
        policy_id=payload.policy_id,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        claims_type=payload.claims_type,
        vehicle_category=result["vehicle_category"],
        status=ClaimStatus(result["status"]),
        claimed_amount=payload.claimed_amount,
        deductible_applied=result["deductible_applied"],
        coverage_cap_applied=result["coverage_cap_applied"],
        recommended_payout=result["recommended_payout"],
        fraud_score=result["fraud_score"],
        fraud_flags=result["fraud_flags"],
        policy_exclusions=result["policy_exclusions"],
        cited_clauses=cited,
        requires_human_approval=result["requires_human_approval"],
        rejection_reason=result.get("rejection_reason", ""),
        incident_date=payload.incident_date,
        reported_date=payload.reported_date,
        payout_needed_date=payload.payout_needed_date,
        proof_files=payload.proof_files,
        settlement_summary=result["settlement_summary"],
        audit_log=result["audit_log"],
    )

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(ClaimRecord).where(ClaimRecord.claim_id == payload.claim_id))
        if existing:
            existing.status = decision.status.value
            existing.deductible_applied = decision.deductible_applied
            existing.coverage_cap_applied = decision.coverage_cap_applied
            existing.recommended_payout = decision.recommended_payout
            existing.fraud_score = decision.fraud_score
            existing.requires_human_approval = decision.requires_human_approval
            existing.decision_payload = decision.model_dump(mode="json")
        else:
            session.add(
                ClaimRecord(
                    claim_id=payload.claim_id,
                    policy_id=payload.policy_id,
                    claims_type=payload.claims_type,
                    vehicle_category=decision.vehicle_category,
                    claimed_amount=payload.claimed_amount,
                    deductible_applied=decision.deductible_applied,
                    coverage_cap_applied=decision.coverage_cap_applied,
                    recommended_payout=decision.recommended_payout,
                    fraud_score=decision.fraud_score,
                    status=decision.status.value,
                    requires_human_approval=decision.requires_human_approval,
                    decision_payload=decision.model_dump(mode="json"),
                    raw_description=payload.description,
                )
            )
        await session.commit()

    event_name = "CLAIM_APPROVED" if decision.status == ClaimStatus.APPROVED else "CLAIM_REQUESTED"
    notify_company_of_claim(decision, event_type=event_name)
    return decision


async def _human_decide_async(
    claim_id: str,
    approve: bool,
    reviewer_note: str = "",
) -> ClaimDecisionResponse | None:
    await _ensure_db_async()
    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
        if not record:
            return None

        current = ClaimDecisionResponse(**record.decision_payload)
        if approve:
            payout = max(
                0.0,
                round(min(current.claimed_amount, current.coverage_cap_applied) - current.deductible_applied, 2),
            )
            new_status = ClaimStatus.APPROVED
            note_suffix = f" Reviewer note: {reviewer_note.strip()}." if reviewer_note.strip() else ""
            summary = f"Approved payout of ₹{payout:,.2f}.{note_suffix}"
            updated = current.model_copy(
                update={
                    "status": new_status,
                    "recommended_payout": payout,
                    "requires_human_approval": False,
                    "rejection_reason": "",
                    "settlement_summary": summary,
                    "audit_log": [
                        *current.audit_log,
                        {"stage": "Company Approval", "detail": summary},
                    ],
                }
            )
            event_name = "CLAIM_APPROVED"
        else:
            reason = reviewer_note.strip() or "Rejected after company review."
            summary = f"Rejected after company review. Reason: {reason}"
            updated = current.model_copy(
                update={
                    "status": ClaimStatus.REJECTED,
                    "recommended_payout": 0.0,
                    "requires_human_approval": False,
                    "rejection_reason": reason,
                    "settlement_summary": summary,
                    "audit_log": [
                        *current.audit_log,
                        {"stage": "Company Decision", "detail": summary},
                    ],
                }
            )
            event_name = "CLAIM_REJECTED"

        record.status = updated.status.value
        record.recommended_payout = updated.recommended_payout
        record.requires_human_approval = updated.requires_human_approval
        record.decision_payload = updated.model_dump(mode="json")
        await session.commit()

    notify_company_of_claim(updated, event_type=event_name)
    return updated


async def _fetch_claims_async(limit: int = 200) -> list[ClaimDecisionResponse]:
    await _ensure_db_async()
    async with AsyncSessionLocal() as session:
        rows = (await session.scalars(select(ClaimRecord).order_by(desc(ClaimRecord.id)).limit(limit))).all()
        return [ClaimDecisionResponse(**r.decision_payload) for r in rows]


def _run_coro(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def evaluate_and_save_claim(payload: ClaimIntakeRequest) -> ClaimDecisionResponse:
    return _run_coro(_evaluate_and_save_async(payload))


def evaluate_and_save_batch(payloads: list[ClaimIntakeRequest]) -> list[ClaimDecisionResponse]:
    async def _batch():
        return [await _evaluate_and_save_async(item) for item in payloads]

    return _run_coro(_batch())


def human_decide_claim(claim_id: str, approve: bool, reviewer_note: str = "") -> ClaimDecisionResponse | None:
    return _run_coro(_human_decide_async(claim_id=claim_id, approve=approve, reviewer_note=reviewer_note))


def list_saved_claims(limit: int = 200) -> list[ClaimDecisionResponse]:
    return _run_coro(_fetch_claims_async(limit=limit))