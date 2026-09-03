from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Date, Text, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Customer(Base):
    """B2B Customer entity"""
    __tablename__ = "customers"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100))
    reliability_score = Column(Float, default=0.5)  # 0.0-1.0 for simulator
    total_invoices = Column(Integer, default=0)
    total_paid = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    invoices = relationship("Invoice", back_populates="customer")
    cases = relationship("Case", back_populates="customer")
    
    def __repr__(self):
        return f"<Customer {self.id}: {self.name}>"


class Invoice(Base):
    """B2B Invoice entity"""
    __tablename__ = "invoices"
    
    id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default="UNPAID")  # UNPAID, PAID, DISPUTED, RECOVERED
    dispute_flag = Column(Boolean, default=False)
    dispute_reason = Column(Text)
    delay_reason = Column(String(255))  # technical, mandate, cash-flow, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index("idx_invoice_customer_id", "customer_id"),
        Index("idx_invoice_status", "status"),
        Index("idx_invoice_due_date", "due_date"),
    )
    
    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    case = relationship("Case", uselist=False, back_populates="invoice")
    
    def __repr__(self):
        return f"<Invoice {self.id}: {self.amount}>"


class Case(Base):
    """Revenue recovery case (per invoice)"""
    __tablename__ = "cases"
    
    id = Column(String(50), primary_key=True)
    invoice_id = Column(String(50), ForeignKey("invoices.id"), nullable=False, unique=True)
    customer_id = Column(String(50), ForeignKey("customers.id"), nullable=False)
    risk_level = Column(String(20))  # LOW, MEDIUM, HIGH, BLOCKED
    risk_score = Column(Float)  # 0-100
    escalation_stage = Column(Integer, default=1)  # 1, 2, 3, 4
    status = Column(String(20), default="ACTIVE")  # ACTIVE, PAYMENT_RECEIVED, ESCALATED, STOPPED, HUMAN_REVIEW
    revenue_recovered = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index("idx_invoice_id", "invoice_id"),
        Index("idx_customer_id", "customer_id"),
        Index("idx_status", "status"),
        Index("idx_risk_level", "risk_level"),
    )
    
    # Relationships
    invoice = relationship("Invoice", back_populates="case")
    customer = relationship("Customer", back_populates="cases")
    actions = relationship("Action", back_populates="case")
    promises = relationship("Promise", back_populates="case")
    
    def __repr__(self):
        return f"<Case {self.id}: {self.risk_level}>"


class Action(Base):
    """Recovery action taken on a case"""
    __tablename__ = "actions"
    
    id = Column(String(50), primary_key=True)
    case_id = Column(String(50), ForeignKey("cases.id"), nullable=False)
    action_type = Column(String(50))  # gentle_nudge, firm_reminder, etc.
    status = Column(String(20), default="PROPOSED")  # PROPOSED, APPROVED, EXECUTED, FAILED, BLOCKED
    ai_confidence = Column(Float)  # LLM confidence score
    policy_approved = Column(Boolean)
    customer_response = Column(Text)  # Free text response
    response_type = Column(String(50))  # payment, promise, dispute, no_response, ignore
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime)
    
    # Indexes
    __table_args__ = (
        Index("idx_action_case_id", "case_id"),
        Index("idx_action_action_type", "action_type"),
        Index("idx_action_status", "status"),
    )
    
    # Relationships
    case = relationship("Case", back_populates="actions")
    promises = relationship("Promise", back_populates="action")
    
    def __repr__(self):
        return f"<Action {self.id}: {self.action_type}>"


class Promise(Base):
    """Promise-to-Pay commitment"""
    __tablename__ = "promises"
    
    id = Column(String(50), primary_key=True)
    case_id = Column(String(50), ForeignKey("cases.id"), nullable=False)
    action_id = Column(String(50), ForeignKey("actions.id"))
    promised_amount = Column(Float)
    promised_date = Column(Date)
    extraction_confidence = Column(Float)  # LLM extraction confidence
    status = Column(String(20), default="MADE")  # MADE, KEPT, BROKEN, RENEGOTIATED
    promise_text = Column(Text)  # Exact quote from customer
    customer_response_text = Column(Text)  # Full response
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)  # When KEPT or BROKEN
    
    # Indexes
    __table_args__ = (
        Index("idx_promise_case_id", "case_id"),
        Index("idx_promise_status", "status"),
        Index("idx_promise_promised_date", "promised_date"),
    )
    
    # Relationships
    case = relationship("Case", back_populates="promises")
    action = relationship("Action", back_populates="promises")
    
    def __repr__(self):
        return f"<Promise {self.id}: {self.status}>"


class AuditLog(Base):
    """Immutable audit trail"""
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    case_id = Column(String(50))
    event_type = Column(String(50), nullable=False)  # RISK_SCORE, DIAGNOSIS, etc.
    actor = Column(String(50), nullable=False)  # SYSTEM, LLM, POLICY_ENGINE, etc.
    input_data = Column(JSON)
    output_data = Column(JSON)
    passed = Column(Boolean)
    reason = Column(Text)
    metadata_info = Column(JSON)
    
    # Indexes
    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_case_id", "case_id"),
        Index("idx_audit_event_type", "event_type"),
    )
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.event_type}>"


class BatchRun(Base):
    """Batch processing run metadata"""
    __tablename__ = "batch_runs"
    
    id = Column(String(50), primary_key=True)
    run_type = Column(String(20))  # BASELINE, VASOOLI
    status = Column(String(20), default="IN_PROGRESS")  # IN_PROGRESS, COMPLETED, FAILED
    total_invoices = Column(Integer, default=0)
    revenue_at_risk = Column(Float, default=0.0)
    revenue_recovered = Column(Float, default=0.0)
    recovery_rate = Column(Float, default=0.0)
    escalated_count = Column(Integer, default=0)
    stopped_count = Column(Integer, default=0)
    promise_count = Column(Integer, default=0)
    promise_kept = Column(Integer, default=0)
    promise_broken = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Indexes
    __table_args__ = (
        Index("idx_batch_run_type", "run_type"),
        Index("idx_batch_status", "status"),
    )
    
    def __repr__(self):
        return f"<BatchRun {self.id}: {self.run_type}>"


class CaseSnapshot(Base):
    """Initial snapshot of a case for fair evaluation comparison"""
    __tablename__ = "case_snapshots"
    
    id = Column(String(50), primary_key=True)
    batch_id = Column(String(50), nullable=False)
    case_id = Column(String(50), nullable=False)
    invoice_id = Column(String(50), nullable=False)
    customer_id = Column(String(50), nullable=False)
    customer_name = Column(String(255))
    customer_reliability = Column(Float, default=0.5)
    invoice_amount = Column(Float, nullable=False)
    invoice_date = Column(Date, nullable=False)
    invoice_due_date = Column(Date, nullable=False)
    invoice_status = Column(String(20), nullable=False)
    dispute_flag = Column(Boolean, default=False)
    dispute_reason = Column(Text)
    delay_reason = Column(String(255))
    risk_level = Column(String(20))
    risk_score = Column(Float)
    initial_status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_snapshot_batch_id", "batch_id"),
        Index("idx_snapshot_case_id", "case_id"),
        Index("idx_snapshot_invoice_id", "invoice_id"),
    )
    
    def __repr__(self):
        return f"<CaseSnapshot {self.id}: {self.batch_id} - {self.case_id}>"

