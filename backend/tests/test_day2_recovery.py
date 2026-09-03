"""
Comprehensive pytest tests for Vasooli Day 2: AI Recovery Engine
Tests cover:
- AI provider abstraction and mock mode
- Policy engine all guardrails
- Customer simulator reproducibility
- Action executor
- Promise extraction
- Batch recovery workflow
- Baseline comparison
"""

import pytest
from datetime import datetime, date, timedelta
from database import SessionLocal, init_db
from database.models import (
    Customer, Invoice, Case, Action, Promise, AuditLog, BatchRun, Base
)
from core.risk_scorer import RiskScorer
from core.policy_engine import PolicyEngine, PolicyCheckResult
from core.ai_orchestrator import AIOrchestrator
from ai.provider import AIProviderFactory, DiagnosisOutput, ActionProposal
from ai.mock_llm import MockLLM
from simulator.customer_simulator import CustomerSimulator, CustomerResponseType
from executor.action_executor import ActionExecutor
from config.constants import (
    RiskLevel, CaseStatus, ActionStatus, PromiseStatus, 
    AuditEventType, Actor, MAX_CONTACT_ATTEMPTS
)
from synthetic_data.generator import SyntheticDataGenerator
import uuid


@pytest.fixture
def db_session():
    """Create test database session"""
    # Use in-memory SQLite for tests
    import sqlalchemy
    engine = sqlalchemy.create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_customer(db_session):
    """Create a sample customer"""
    customer = Customer(
        id="CUST-TEST-001",
        name="Test Corp Inc",
        industry="Manufacturing",
        reliability_score=0.7,
        total_invoices=10,
        total_paid=500000.0,
    )
    db_session.add(customer)
    db_session.commit()
    return customer


@pytest.fixture
def sample_invoice(db_session, sample_customer):
    """Create a sample invoice"""
    invoice = Invoice(
        id="INV-TEST-001",
        customer_id=sample_customer.id,
        amount=100000.0,
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 2, 1),
        status="UNPAID",
        dispute_flag=False,
        delay_reason="cash-flow",
    )
    db_session.add(invoice)
    db_session.commit()
    return invoice


@pytest.fixture
def sample_case(db_session, sample_invoice, sample_customer):
    """Create a sample recovery case"""
    case = Case(
        id="CASE-TEST-001",
        invoice_id=sample_invoice.id,
        customer_id=sample_customer.id,
        risk_level=RiskLevel.MEDIUM,
        risk_score=50.0,
        escalation_stage=1,
        status=CaseStatus.ACTIVE,
    )
    db_session.add(case)
    db_session.commit()
    return case


# ========== AI PROVIDER TESTS ==========

def test_ai_provider_factory_mock_mode():
    """Test AIProviderFactory returns mock provider"""
    import os
    os.environ["AI_PROVIDER"] = "mock"
    AIProviderFactory.reset_provider()
    
    provider = AIProviderFactory.get_provider()
    assert isinstance(provider, MockLLM)
    assert provider is not None


def test_mock_llm_diagnoses_disputed_invoice():
    """Test MockLLM identifies disputed invoices"""
    mock_ai = MockLLM()
    
    diagnosis = mock_ai.diagnose(
        invoice_amount=100000,
        days_overdue=30,
        customer_name="Test Corp",
        reliability_score=0.5,
        payment_history="Late payments",
        delay_reason=None,
        dispute_status="DISPUTED",
        escalation_stage=1,
    )
    
    assert "dispute" in diagnosis.root_cause.lower()
    assert diagnosis.confidence > 0.9


def test_mock_llm_proposes_gentle_nudge_for_reliable_recent():
    """Test MockLLM proposes gentle nudge for reliable customer with recent overdue"""
    mock_ai = MockLLM()
    
    diagnosis = DiagnosisOutput(
        root_cause="Recent overdue",
        confidence=0.85,
        context="5 days late",
    )
    
    proposal = mock_ai.propose_action(
        diagnosis=diagnosis,
        invoice_amount=50000,
        days_overdue=5,
        customer_name="Reliable Corp",
        reliability_score=0.9,
        escalation_stage=1,
        previous_attempts=0,
    )
    
    assert proposal.proposed_action == "gentle_nudge"
    assert proposal.confidence > 0.7


def test_mock_llm_proposes_payment_link_for_stage_2_payment_method_issue():
    """Test MockLLM proposes payment link at stage 2 for payment method issues"""
    mock_ai = MockLLM()
    
    diagnosis = DiagnosisOutput(
        root_cause="Customer needs payment method",
        confidence=0.80,
        context="Multiple payment attempts failed",
    )
    
    proposal = mock_ai.propose_action(
        diagnosis=diagnosis,
        invoice_amount=75000,
        days_overdue=20,
        customer_name="Stressed Corp",
        reliability_score=0.4,
        escalation_stage=2,
        previous_attempts=1,
    )
    
    assert proposal.proposed_action == "payment_link"


def test_mock_llm_blocks_disputed_actions():
    """Test MockLLM blocks actions for disputed invoices"""
    mock_ai = MockLLM()
    
    proposal = mock_ai.propose_action(
        diagnosis=DiagnosisOutput(
            root_cause="Disputed invoice - quality issue",
            confidence=0.95,
            context="Customer disputes validity",
        ),
        invoice_amount=100000,
        days_overdue=45,
        customer_name="Disputing Corp",
        reliability_score=0.3,
        escalation_stage=2,
        previous_attempts=2,
    )
    
    assert proposal.proposed_action == "stop"


def test_mock_llm_extracts_promise_with_high_confidence():
    """Test MockLLM extracts promises from customer responses"""
    mock_ai = MockLLM()
    
    extraction = mock_ai.extract_promise(
        customer_response="Kal ₹50000 kar dunga.",
        invoice_amount=100000,
    )
    
    assert extraction.promised_amount > 0
    assert extraction.promised_date is not None
    assert extraction.confidence >= 0.4


def test_mock_llm_low_confidence_on_unclear_response():
    """Test MockLLM gives low confidence on unclear promises"""
    mock_ai = MockLLM()
    
    extraction = mock_ai.extract_promise(
        customer_response="Maybe we'll see.",
        invoice_amount=100000,
    )
    
    assert extraction.confidence < 0.5


# ========== POLICY ENGINE TESTS ==========

def test_policy_blocks_disputed_invoice(db_session, sample_case, sample_invoice, sample_customer):
    """Test policy engine blocks actions on disputed invoices"""
    sample_invoice.dispute_flag = True
    sample_invoice.dispute_reason = "Quality issue"
    db_session.commit()
    
    policy_engine = PolicyEngine(db_session)
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="gentle_nudge",
        ai_confidence=0.8,
    )
    
    assert result.approved is False
    assert result.final_action == "BLOCK"


def test_policy_stops_paid_invoice(db_session, sample_case, sample_invoice, sample_customer):
    """Test policy engine stops actions on paid invoices"""
    sample_invoice.status = "PAID"
    db_session.commit()
    
    policy_engine = PolicyEngine(db_session)
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="gentle_nudge",
        ai_confidence=0.8,
    )
    
    assert result.approved is False
    assert result.final_action == "STOP"


def test_policy_approves_valid_action(db_session, sample_case, sample_invoice, sample_customer):
    """Test policy engine approves valid actions"""
    policy_engine = PolicyEngine(db_session)
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="gentle_nudge",
        ai_confidence=0.8,
    )
    
    assert result.approved is True
    assert result.final_action == "gentle_nudge"


def test_policy_enforces_max_attempts(db_session, sample_case, sample_invoice, sample_customer):
    """Test policy engine enforces max contact attempts"""
    # Create MAX_CONTACT_ATTEMPTS actions
    for i in range(MAX_CONTACT_ATTEMPTS):
        action = Action(
            id=f"ACT-{i}",
            case_id=sample_case.id,
            action_type="gentle_nudge",
            status=ActionStatus.EXECUTED,
        )
        db_session.add(action)
    db_session.commit()
    
    policy_engine = PolicyEngine(db_session)
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="gentle_nudge",
        ai_confidence=0.8,
    )
    
    assert result.approved is False


def test_policy_escalation_stage_1_only_allows_certain_actions(db_session, sample_case, sample_invoice, sample_customer):
    """Test stage 1 action restrictions"""
    sample_case.escalation_stage = 1
    db_session.commit()
    
    policy_engine = PolicyEngine(db_session)
    
    # Should approve
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="gentle_nudge",
        ai_confidence=0.8,
    )
    assert result.approved is True
    
    # Should reject
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="human_escalation",
        ai_confidence=0.8,
    )
    assert result.approved is False


def test_policy_escalation_stage_3_allows_escalation(db_session, sample_case, sample_invoice, sample_customer):
    """Test stage 3 allows human escalation"""
    sample_case.escalation_stage = 3
    db_session.commit()
    
    policy_engine = PolicyEngine(db_session)
    result = policy_engine.validate_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        proposed_action="human_escalation",
        ai_confidence=0.8,
    )
    assert result.approved is True


# ========== CUSTOMER SIMULATOR TESTS ==========

def test_simulator_reproducible_with_same_seed():
    """Test customer simulator is reproducible with fixed seed"""
    sim1 = CustomerSimulator(seed=42)
    sim2 = CustomerSimulator(seed=42)
    
    response1 = sim1.simulate_response(
        action="gentle_nudge",
        customer_profile="Slow",
        invoice_amount=100000,
        days_overdue=30,
        escalation_stage=1,
        previous_attempts=0,
        reliability_score=0.5,
    )
    
    response2 = sim2.simulate_response(
        action="gentle_nudge",
        customer_profile="Slow",
        invoice_amount=100000,
        days_overdue=30,
        escalation_stage=1,
        previous_attempts=0,
        reliability_score=0.5,
    )
    
    assert response1[0] == response2[0]  # Same response type


def test_simulator_reliable_customer_pays():
    """Test reliable customers tend to pay"""
    paid_count = 0
    promise_count = 0
    
    # Test across multiple invoice amounts to get varied random states
    for amount in [50000, 75000, 100000, 125000, 150000]:
        simulator = CustomerSimulator(seed=42)
        
        response_type, _ = simulator.simulate_response(
            action="gentle_nudge",
            customer_profile="Reliable",
            invoice_amount=amount,
            days_overdue=10,
            escalation_stage=1,
            previous_attempts=0,
            reliability_score=0.9,
        )
        
        if response_type == CustomerResponseType.PAID:
            paid_count += 1
        elif response_type == CustomerResponseType.PROMISE_TO_PAY:
            promise_count += 1
    
    # Reliable customers should have high payment or promise rates
    assert (paid_count + promise_count) >= 2


def test_simulator_disputed_invoice_never_pays():
    """Test disputed profile never pays"""
    simulator = CustomerSimulator(seed=42)
    
    for i in range(3):
        response_type, _ = simulator.simulate_response(
            action="gentle_nudge",
            customer_profile="Disputed",
            invoice_amount=100000,
            days_overdue=30,
            escalation_stage=1,
            previous_attempts=0,
            reliability_score=0.0,
        )
        assert response_type == CustomerResponseType.DISPUTES


# ========== ACTION EXECUTOR TESTS ==========

def test_action_executor_blocks_disputed(db_session, sample_case, sample_invoice, sample_customer):
    """Test action executor blocks disputed invoices"""
    sample_invoice.dispute_flag = True
    db_session.commit()
    
    executor = ActionExecutor(db_session)
    action_response = executor.execute_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        action_type="gentle_nudge",
        ai_confidence=0.8,
        policy_approved=False,
        policy_reason="Disputed invoice",
    )
    
    assert action_response.status == ActionStatus.BLOCKED


def test_action_executor_simulates_response(db_session, sample_case, sample_invoice, sample_customer):
    """Test action executor simulates customer response"""
    executor = ActionExecutor(db_session)
    action_response = executor.execute_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        action_type="gentle_nudge",
        ai_confidence=0.8,
        policy_approved=True,
        policy_reason="Valid action",
    )
    
    assert action_response.status == ActionStatus.EXECUTED
    assert action_response.customer_response is not None


# ========== AI ORCHESTRATOR TESTS ==========

def test_orchestrator_runs_complete_workflow(db_session, sample_case, sample_invoice, sample_customer):
    """Test AI orchestrator runs complete recovery workflow"""
    from core.audit_logger import audit_logger
    audit_logger.set_session(db_session)
    
    orchestrator = AIOrchestrator(db_session)
    result = orchestrator.run_recovery_for_case(sample_case)
    
    assert result.get("success") is True
    assert "diagnosis" in result
    assert "proposed_action" in result
    assert "policy_result" in result


def test_orchestrator_skips_completed_cases(db_session, sample_case, sample_invoice, sample_customer):
    """Test orchestrator skips already-completed cases"""
    from core.audit_logger import audit_logger
    audit_logger.set_session(db_session)
    
    sample_case.status = CaseStatus.PAYMENT_RECEIVED
    db_session.commit()
    
    orchestrator = AIOrchestrator(db_session)
    result = orchestrator.run_recovery_for_case(sample_case)
    
    assert result.get("success") is False


# ========== INTEGRATION TESTS ==========

def test_batch_recovery_workflow(db_session):
    """Test complete batch recovery workflow"""
    from core.audit_logger import audit_logger
    audit_logger.set_session(db_session)
    
    # Generate synthetic data
    generator = SyntheticDataGenerator(seed=42)
    customers, invoice_tuples = generator.generate_batch(num_invoices=5)
    
    # Store data
    for customer in customers:
        db_session.add(customer)
    db_session.commit()
    
    for invoice, customer in invoice_tuples:
        db_session.add(invoice)
    db_session.commit()
    
    # Create cases
    for invoice, customer in invoice_tuples:
        invoice = db_session.query(Invoice).filter(Invoice.id == invoice.id).first()
        customer = db_session.query(Customer).filter(Customer.id == customer.id).first()
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        case = Case(
            id=f"CASE-{invoice.id}",
            invoice_id=invoice.id,
            customer_id=customer.id,
            risk_level=risk_level,
            risk_score=risk_score,
            escalation_stage=1,
            status=CaseStatus.ACTIVE,
        )
        db_session.add(case)
    db_session.commit()
    
    # Run recovery on all cases
    orchestrator = AIOrchestrator(db_session)
    cases = db_session.query(Case).filter(Case.status == CaseStatus.ACTIVE).all()
    
    results = []
    for case in cases:
        result = orchestrator.run_recovery_for_case(case)
        results.append(result)
    
    assert len(results) > 0
    assert any(r.get("success") for r in results)


def test_already_paid_near_miss_prevented(db_session, sample_case, sample_invoice, sample_customer):
    """Test already-paid invoice near-miss prevention before action execution"""
    from core.audit_logger import audit_logger
    audit_logger.set_session(db_session)

    # Mark invoice as paid before execution
    sample_invoice.status = "PAID"
    db_session.commit()

    executor = ActionExecutor(db_session)
    response = executor.execute_action(
        case=sample_case,
        invoice=sample_invoice,
        customer=sample_customer,
        action_type="gentle_nudge",
        ai_confidence=0.8,
        policy_approved=True,
        policy_reason="Approved",
    )

    # Action must be cancelled/blocked and not sent to simulator
    assert response.status == ActionStatus.BLOCKED
    assert sample_case.status == CaseStatus.PAYMENT_RECEIVED
    assert sample_case.revenue_recovered == sample_invoice.amount

    # Verify near_miss_prevented audit event was logged
    audit_events = db_session.query(AuditLog).filter(
        AuditLog.case_id == sample_case.id,
        AuditLog.event_type == AuditEventType.NEAR_MISS_PREVENTED,
    ).all()
    assert len(audit_events) >= 1
    assert "near miss" in audit_events[0].reason.lower()


def test_promise_lifecycle_kept_contributes_once(db_session, sample_case, sample_invoice):
    """Test promise KEPT contributes to recovered revenue exactly once and updates state"""
    promise = Promise(
        id="PROMISE-TEST-001",
        case_id=sample_case.id,
        promised_amount=75000.0,
        promised_date=date.today() + timedelta(days=3),
        extraction_confidence=0.85,
        status=PromiseStatus.MADE,
        promise_text="Will pay 75000 in 3 days",
    )
    db_session.add(promise)
    db_session.commit()

    from api.routes import update_promise_status
    # Update to KEPT
    res = update_promise_status(sample_case.id, promise.id, "KEPT", db_session)
    assert res["status"] == "KEPT"
    assert sample_case.status == CaseStatus.PAYMENT_RECEIVED
    assert sample_case.revenue_recovered == 75000.0
    assert sample_invoice.status == "PAID"

    # Calling again should not duplicate recovery or exceed amount
    res2 = update_promise_status(sample_case.id, promise.id, "KEPT", db_session)
    assert res2["status"] == "KEPT"
    assert sample_case.revenue_recovered == 75000.0


def test_promise_lifecycle_broken_escalates(db_session, sample_case):
    """Test broken promise causes stage escalation and status change"""
    promise = Promise(
        id="PROMISE-TEST-002",
        case_id=sample_case.id,
        promised_amount=50000.0,
        promised_date=date.today() - timedelta(days=1),
        extraction_confidence=0.8,
        status=PromiseStatus.MADE,
        promise_text="Will pay yesterday",
    )
    db_session.add(promise)
    sample_case.escalation_stage = 1
    db_session.commit()

    from api.routes import update_promise_status
    res = update_promise_status(sample_case.id, promise.id, "BROKEN", db_session)
    assert res["status"] == "BROKEN"
    assert sample_case.escalation_stage == 2
    assert sample_case.status == CaseStatus.ESCALATED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

