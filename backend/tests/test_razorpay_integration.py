"""
Unit tests for Razorpay Test Mode integration in Vasooli.

Tests verify:
- client initializes from environment
- missing credentials fail safely
- successful Razorpay response is handled
- Razorpay failure is handled and secrets are not leaked
- audit event is generated with required fields
- simulator fallback works seamlessly when credentials missing or API fails
"""

from unittest.mock import MagicMock, patch
import pytest
from datetime import date

from database.models import Customer, Invoice, Case, Action, Base
from config.constants import RiskLevel, CaseStatus, ActionStatus, Actor
from core.audit_logger import audit_logger
from integrations.razorpay_client import RazorpayTestClient
from executor.action_executor import ActionExecutor


@pytest.fixture
def db_session():
    """Create in-memory test database session"""
    import sqlalchemy

    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_entities(db_session):
    """Create standard customer, invoice, and case for testing"""
    customer = Customer(
        id="CUST-RZP-001",
        name="Acme Logistics",
        industry="Logistics",
        reliability_score=0.8,
        total_invoices=5,
        total_paid=250000.0,
    )
    invoice = Invoice(
        id="INV-RZP-001",
        customer_id=customer.id,
        amount=50000.0,
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 2, 1),
        status="UNPAID",
        dispute_flag=False,
    )
    case = Case(
        id="CASE-RZP-001",
        invoice_id=invoice.id,
        customer_id=customer.id,
        risk_level=RiskLevel.MEDIUM,
        risk_score=45.0,
        escalation_stage=1,
        status=CaseStatus.ACTIVE,
    )
    db_session.add(customer)
    db_session.add(invoice)
    db_session.add(case)
    db_session.commit()
    return customer, invoice, case


# 1. Client initialization from environment
def test_client_initializes_from_environment(monkeypatch):
    """Verify RazorpayTestClient initializes properly from environment"""
    test_key = "rzp_test_demo123456"
    test_secret = "secret_demo_987654"

    monkeypatch.setenv("RAZORPAY_KEY_ID", test_key)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", test_secret)

    client = RazorpayTestClient()
    assert client.is_configured() is True
    assert client.key_id == test_key

    info = client.get_public_info()
    assert info["is_configured"] is True
    assert info["provider"] == "razorpay_test"
    assert info["mode"] == "test"
    # Verify secret is never exposed in public info
    assert "secret" not in str(info).lower()


# 2. Missing credentials fail safely
def test_missing_and_placeholder_credentials_fail_safely():
    """Verify unconfigured or placeholder credentials fail safely without crashing"""
    # Empty credentials
    client_empty = RazorpayTestClient(key_id="", key_secret="")
    assert client_empty.is_configured() is False
    res = client_empty.create_payment_retry(
        invoice_id="INV-001", amount=1000.0, customer_id="CUST-001"
    )
    assert res["success"] is False
    assert res["provider"] == "razorpay_test"
    assert "not configured" in res["error"].lower()

    # Placeholder credentials (as found in template files)
    client_placeholder = RazorpayTestClient(
        key_id="your_test_key_id", key_secret="your_test_key_secret"
    )
    assert client_placeholder.is_configured() is False
    res_ph = client_placeholder.create_payment_retry(
        invoice_id="INV-001", amount=1000.0, customer_id="CUST-001"
    )
    assert res_ph["success"] is False


# 3. Successful Razorpay response is handled
def test_successful_razorpay_response_handled(db_session, sample_entities):
    """Verify successful Razorpay Test Mode response updates invoice, case, and action"""
    customer, invoice, case = sample_entities
    audit_logger.set_session(db_session)

    test_key = "rzp_test_realformat123"
    test_secret = "secret_realformat456"
    client = RazorpayTestClient(key_id=test_key, key_secret=test_secret)

    # Mock the internal Razorpay SDK client order create response
    mock_order = {
        "id": "order_test_ABC123XYZ",
        "status": "created",
        "amount": 5000000,
        "currency": "INR",
        "receipt": "rec_INVRZP001",
        "created_at": 1740000000,
    }
    client._client = MagicMock()
    client._client.order.create.return_value = mock_order

    executor = ActionExecutor(db_session, razorpay_client=client)

    action_response = executor.execute_action(
        case=case,
        invoice=invoice,
        customer=customer,
        action_type="payment_retry",
        ai_confidence=0.85,
        policy_approved=True,
        policy_reason="Policy passed",
    )

    # Verify action execution and case update
    assert action_response.status == ActionStatus.EXECUTED
    assert "order_test_ABC123XYZ" in action_response.customer_response
    assert "Razorpay Test Mode" in action_response.customer_response
    assert invoice.status == "PAID"
    assert case.status == CaseStatus.PAYMENT_RECEIVED
    assert case.revenue_recovered == 50000.0


# 4. Razorpay failure is handled and secrets are never leaked
def test_razorpay_failure_handled_and_secrets_protected(db_session, sample_entities):
    """Verify Razorpay API failure is caught safely and does not leak secret in error"""
    test_secret = "super_confidential_secret_789"
    client = RazorpayTestClient(
        key_id="rzp_test_dummykey",
        key_secret=test_secret,
    )

    # Mock order.create raising an exception with the secret in the message
    client._client = MagicMock()
    client._client.order.create.side_effect = Exception(
        f"API Error 401 with secret {test_secret}"
    )

    result = client.create_payment_retry(
        invoice_id="INV-ERR-001",
        amount=25000.0,
        customer_id="CUST-001",
    )

    assert result["success"] is False
    assert result["provider"] == "razorpay_test"
    assert result["transaction_id"] is None
    # Verify secret is redacted and not present in error
    assert test_secret not in result["error"]
    assert "[REDACTED]" in result["error"]


# 5. Audit event is generated for Razorpay test attempt
def test_audit_event_generated_for_razorpay(db_session, sample_entities):
    """Verify audit log entry contains provider, action, timestamp, transaction ID without secrets"""
    customer, invoice, case = sample_entities
    audit_logger.set_session(db_session)

    test_key = "rzp_test_audit123"
    test_secret = "secret_audit456"
    client = RazorpayTestClient(key_id=test_key, key_secret=test_secret)

    order_id = "order_audit_555777"
    client._client = MagicMock()
    client._client.order.create.return_value = {
        "id": order_id,
        "status": "created",
        "amount": 5000000,
        "currency": "INR",
        "created_at": 1740000000,
    }

    executor = ActionExecutor(db_session, razorpay_client=client)
    executor.execute_action(
        case=case,
        invoice=invoice,
        customer=customer,
        action_type="payment_retry",
        ai_confidence=0.9,
        policy_approved=True,
        policy_reason="Passed",
    )

    trail = audit_logger.get_case_audit_trail(case.id)
    assert len(trail) > 0

    # Find the razorpay_test audit events
    rzp_events = [e for e in trail if e.get("actor") == Actor.RAZORPAY_TEST]
    assert len(rzp_events) >= 1

    event = rzp_events[0]
    assert event["input_data"]["provider"] == "razorpay_test"
    assert event["input_data"]["action"] == "payment_retry"
    assert event["output_data"]["transaction_id"] == order_id
    assert event["passed"] is True
    assert event["timestamp"] is not None

    # Verify secret is NOT anywhere in the audit trail
    for log_entry in trail:
        assert test_secret not in str(log_entry)


# 6. Simulator fallback works seamlessly when credentials unconfigured or API fails
def test_simulator_fallback_when_credentials_unconfigured(db_session, sample_entities):
    """Verify executor falls back to simulator when Razorpay credentials are not configured"""
    customer, invoice, case = sample_entities
    audit_logger.set_session(db_session)

    # Unconfigured client
    client = RazorpayTestClient(key_id="", key_secret="")
    executor = ActionExecutor(db_session, simulator_seed=42, razorpay_client=client)

    action_response = executor.execute_action(
        case=case,
        invoice=invoice,
        customer=customer,
        action_type="payment_retry",
        ai_confidence=0.8,
        policy_approved=True,
        policy_reason="Approved",
    )

    # Action must execute via simulator fallback
    assert action_response.status == ActionStatus.EXECUTED
    assert action_response.customer_response is not None
    # Must NOT falsely report a Razorpay order
    assert "order_test_" not in action_response.customer_response

    # Verify audit event records provider as simulator
    trail = audit_logger.get_case_audit_trail(case.id)
    sim_events = [
        e for e in trail if e.get("input_data", {}).get("provider") == "simulator"
    ]
    assert len(sim_events) > 0


def test_simulator_fallback_when_razorpay_api_fails(db_session, sample_entities):
    """Verify executor gracefully falls back to simulator when Razorpay API call fails"""
    customer, invoice, case = sample_entities
    audit_logger.set_session(db_session)

    client = RazorpayTestClient(key_id="rzp_test_valid", key_secret="secret_valid")
    client._client = MagicMock()
    # Razorpay API fails with network timeout
    client._client.order.create.side_effect = Exception("Gateway Timeout")

    executor = ActionExecutor(db_session, simulator_seed=42, razorpay_client=client)

    action_response = executor.execute_action(
        case=case,
        invoice=invoice,
        customer=customer,
        action_type="payment_retry",
        ai_confidence=0.8,
        policy_approved=True,
        policy_reason="Approved",
    )

    # Verify fallback completed action
    assert action_response.status == ActionStatus.EXECUTED
    assert action_response.customer_response is not None
    assert "order_test_" not in action_response.customer_response

    # Verify audit trail captured both the failed razorpay attempt and the simulator fallback
    trail = audit_logger.get_case_audit_trail(case.id)
    failed_rzp = [
        e
        for e in trail
        if e.get("actor") == Actor.RAZORPAY_TEST and e.get("passed") is False
    ]
    assert len(failed_rzp) == 1
    assert failed_rzp[0]["output_data"]["status"] == "FAILED"

    sim_events = [
        e for e in trail if e.get("input_data", {}).get("provider") == "simulator"
    ]
    assert len(sim_events) > 0
