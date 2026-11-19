from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ClaimRecord(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    policy_id: Mapped[int] = mapped_column(Integer, index=True)
    claims_type: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_category: Mapped[str] = mapped_column(String(64))
    claimed_amount: Mapped[float] = mapped_column(Float)
    deductible_applied: Mapped[float] = mapped_column(Float, default=0.0)
    coverage_cap_applied: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_payout: Mapped[float] = mapped_column(Float, default=0.0)
    fraud_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
