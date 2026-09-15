from typing import Optional

from pydantic import BaseModel, Field


class BuildingContext(BaseModel):
    building_type: str = Field(
        ..., description="e.g., Commercial, Residential, Hospital"
    )
    number_of_floors: int = Field(..., gt=0)
    has_extinguishers: bool
    extinguisher_details: Optional[str] = None


class ComplianceRuleCheck(BaseModel):
    rule_clause: str = Field(..., description="e.g., Reg.5(2)(a)")
    status: str = Field(
        ...,
        description="COMPLIANT, NON_COMPLIANT, PARTIAL, or INSUFFICIENT_DATA",
    )
    finding: str
    recommendation: Optional[str] = None


class ComplianceResponse(BaseModel):
    overall_status: str = Field(..., description="COMPLIANT or NON_COMPLIANT")
    compliance_score: float = Field(..., ge=0.0, le=100.0)
    detailed_checks: list[ComplianceRuleCheck]
    summary: str


class AuditRequest(BaseModel):
    building_details: BuildingContext
