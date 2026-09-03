from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List, Any


# Customer Schemas
class CustomerCreate(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
    reliability_score: float = 0.5
    total_invoices: int = 0
    total_paid: float = 0.0


class CustomerResponse(BaseModel):
    id: str
    name: str
    industry: Optional[str]
    reliability_score: float
    total_invoices: int
    total_paid: float
    created_at: datetime
    
    class Config:
        from_attributes = True


# Invoice Schemas
class InvoiceCreate(BaseModel):
    id: str
    customer_id: str
    amount: float
    invoice_date: date
    due_date: date
    dispute_flag: bool = False
    dispute_reason: Optional[str] = None
    delay_reason: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: str
    customer_id: str
    amount: float
    invoice_date: date
    due_date: date
    status: str
    dispute_flag: bool
    dispute_reason: Optional[str]
    delay_reason: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Case Schemas
class CaseCreate(BaseModel):
    id: str
    invoice_id: str
    customer_id: str
    risk_level: str
    risk_score: float
    escalation_stage: int = 1


class CaseResponse(BaseModel):
    id: str
    invoice_id: str
    customer_id: str
    risk_level: str
    risk_score: float
    escalation_stage: int
    status: str
    revenue_recovered: float
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Action Schemas
class ActionCreate(BaseModel):
    id: str
    case_id: str
    action_type: str
    status: str = "PROPOSED"
    ai_confidence: Optional[float] = None
    policy_approved: Optional[bool] = None


class ActionResponse(BaseModel):
    id: str
    case_id: str
    action_type: str
    status: str
    ai_confidence: Optional[float]
    policy_approved: Optional[bool]
    customer_response: Optional[str]
    response_type: Optional[str]
    created_at: datetime
    executed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Promise Schemas
class PromiseCreate(BaseModel):
    id: str
    case_id: str
    action_id: Optional[str] = None
    promised_amount: Optional[float] = None
    promised_date: Optional[date] = None
    extraction_confidence: float = 0.5
    promise_text: str
    customer_response_text: Optional[str] = None


class PromiseResponse(BaseModel):
    id: str
    case_id: str
    action_id: Optional[str]
    promised_amount: Optional[float]
    promised_date: Optional[date]
    extraction_confidence: float
    status: str
    promise_text: str
    customer_response_text: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Audit Log Schemas
class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    case_id: Optional[str]
    event_type: str
    actor: str
    input_data: Optional[dict]
    output_data: Optional[dict]
    passed: Optional[bool]
    reason: Optional[str]
    metadata_info: Optional[dict]
    
    class Config:
        from_attributes = True


# Batch Run Schemas
class BatchRunResponse(BaseModel):
    id: str
    run_type: str
    status: str
    total_invoices: int
    revenue_at_risk: float
    revenue_recovered: float
    recovery_rate: float
    escalated_count: int
    stopped_count: int
    promise_count: int
    promise_kept: int
    promise_broken: int
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Batch Management Schemas
class BatchCreateRequest(BaseModel):
    num_invoices: int = 100
    run_type: str = "VASOOLI"


class BatchCreateResponse(BaseModel):
    batch_id: str
    status: str
    total_invoices: int
    revenue_at_risk: float
    message: str


# Metrics Summary
class MetricsSummary(BaseModel):
    total_invoices: int
    revenue_at_risk: float
    revenue_recovered: float
    recovery_rate: float
    escalated_count: int
    stopped_count: int
    promise_count: int
    promise_kept: int
    promise_broken: int
    average_time_to_recovery: Optional[float]
    cases_by_risk_level: dict
    cases_by_status: dict


# Policy Check Result
class PolicyCheckResult(BaseModel):
    approved: bool
    final_action: str
    reason: str
    rule_checks: List[dict]
