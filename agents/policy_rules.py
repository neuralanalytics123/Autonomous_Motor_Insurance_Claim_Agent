from dataclasses import dataclass


@dataclass(frozen=True)
class PerilRule:
    clause_id: str
    base_deductible: float
    default_cap: float
    use_vehicle_value_cap: bool
    mandatory_hitl: bool
    description: str


PERIL_SCHEDULE: dict[str, PerilRule] = {
    "travel assistance": PerilRule(
        clause_id="COV-01-ASSIST",
        base_deductible=0.0,
        default_cap=135000.0,
        use_vehicle_value_cap=False,
        mandatory_hitl=False,
        description="Roadside recovery, towing, breakdown assistance, and trip continuity.",
    ),
    "complaint": PerilRule(
        clause_id="COV-02-COMPLAINT",
        base_deductible=4500.0,
        default_cap=450000.0,
        use_vehicle_value_cap=False,
        mandatory_hitl=False,
        description="Service dispute, billing/administrative redress, or minor service failure settlement.",
    ),
    "broken windows": PerilRule(
        clause_id="COV-03-GLASS",
        base_deductible=5400.0,
        default_cap=270000.0,
        use_vehicle_value_cap=False,
        mandatory_hitl=False,
        description="Windshield, side, and rear glazing repair/replacement with loyalty deductible relief.",
    ),
    "negligence": PerilRule(
        clause_id="COV-04-NEGLIGENCE",
        base_deductible=22500.0,
        default_cap=13500000.0,
        use_vehicle_value_cap=False,
        mandatory_hitl=False,
        description="Third-party liability and at-fault incident indemnity subject to policy sub-limits.",
    ),
    "all risks": PerilRule(
        clause_id="COV-05-ALL-RISKS",
        base_deductible=27000.0,
        default_cap=2250000.0,
        use_vehicle_value_cap=True,
        mandatory_hitl=False,
        description="Comprehensive physical loss/damage capped at insured vehicle market value.",
    ),
    "theft": PerilRule(
        clause_id="COV-06-THEFT",
        base_deductible=22500.0,
        default_cap=2250000.0,
        use_vehicle_value_cap=True,
        mandatory_hitl=True,
        description="Total or partial vehicle theft/attempted theft; requires human/specialist review.",
    ),
    "injuries": PerilRule(
        clause_id="COV-07-INJURIES",
        base_deductible=0.0,
        default_cap=4500000.0,
        use_vehicle_value_cap=False,
        mandatory_hitl=True,
        description="Bodily injury medical & liability settlement; requires human review.",
    ),
    "fire": PerilRule(
        clause_id="COV-08-FIRE",
        base_deductible=22500.0,
        default_cap=2250000.0,
        use_vehicle_value_cap=True,
        mandatory_hitl=True,
        description="Accidental fire, explosion, or lightning damage; requires human review.",
    ),
    "other": PerilRule(
        clause_id="COV-09-OTHER",
        base_deductible=13500.0,
        default_cap=1350000.0,
        use_vehicle_value_cap=True,
        mandatory_hitl=False,
        description="Miscellaneous covered motor perils evaluated under general policy terms.",
    ),
}

VEHICLE_RISK_MULTIPLIER: dict[int, float] = {
    1: 1.15,
    2: 1.10,
    3: 1.00,
    4: 1.20,
}


def get_peril_rule(claims_type: str) -> PerilRule:
    key = claims_type.strip().lower()
    return PERIL_SCHEDULE.get(key, PERIL_SCHEDULE["other"])