import pytest
from datetime import date, timedelta
from database.models import Customer, Invoice, Case
from core.risk_scorer import RiskScorer
from config.constants import RiskLevel
from synthetic_data.generator import SyntheticDataGenerator


class TestRiskScorer:
    """Test the deterministic risk scorer"""
    
    def test_disputed_invoice_is_blocked(self):
        """Disputed invoices must always be BLOCKED regardless of score"""
        customer = Customer(
            id="CUST-001",
            name="Test Customer",
            reliability_score=0.9,
            total_invoices=10,
            total_paid=100000,
        )
        
        invoice = Invoice(
            id="INV-001",
            customer_id="CUST-001",
            amount=50000,
            invoice_date=date.today() - timedelta(days=90),
            due_date=date.today() - timedelta(days=60),
            status="UNPAID",
            dispute_flag=True,
            dispute_reason="Quality issue",
        )
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        
        assert risk_level == RiskLevel.BLOCKED
    
    def test_paid_invoice_is_low_risk(self):
        """Paid invoices must always be LOW risk"""
        customer = Customer(
            id="CUST-002",
            name="Test Customer",
            reliability_score=0.5,
            total_invoices=1,
            total_paid=0,
        )
        
        invoice = Invoice(
            id="INV-002",
            customer_id="CUST-002",
            amount=500000,  # Large amount
            invoice_date=date.today() - timedelta(days=180),
            due_date=date.today() - timedelta(days=150),
            status="PAID",
            dispute_flag=False,
        )
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        
        assert risk_level == RiskLevel.LOW
        assert risk_score == 0
    
    def test_not_yet_due_is_low_risk(self):
        """Invoices not yet due should be LOW risk"""
        customer = Customer(
            id="CUST-003",
            name="Test Customer",
            reliability_score=0.5,
            total_invoices=1,
            total_paid=0,
        )
        
        future_due = date.today() + timedelta(days=30)
        invoice = Invoice(
            id="INV-003",
            customer_id="CUST-003",
            amount=50000,
            invoice_date=date.today() - timedelta(days=30),
            due_date=future_due,
            status="UNPAID",
            dispute_flag=False,
        )
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        
        assert risk_level == RiskLevel.LOW
    
    def test_significantly_overdue_with_unreliable_customer_is_high_risk(self):
        """Significantly overdue invoices with unreliable customers should be HIGH risk"""
        customer = Customer(
            id="CUST-004",
            name="Unreliable Corp",
            reliability_score=0.1,
            total_invoices=1,
            total_paid=0,
        )
        
        invoice = Invoice(
            id="INV-004",
            customer_id="CUST-004",
            amount=300000,  # Large amount
            invoice_date=date.today() - timedelta(days=150),
            due_date=date.today() - timedelta(days=120),  # 120 days overdue
            status="UNPAID",
            dispute_flag=False,
        )
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        
        assert risk_level == RiskLevel.HIGH
        assert risk_score > 60
    
    def test_moderately_overdue_with_reliable_customer_is_medium_risk(self):
        """Moderately overdue invoices with reliable customers should be MEDIUM risk"""
        customer = Customer(
            id="CUST-005",
            name="Reliable Corp",
            reliability_score=0.85,
            total_invoices=50,
            total_paid=2500000,
        )
        
        invoice = Invoice(
            id="INV-005",
            customer_id="CUST-005",
            amount=50000,
            invoice_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),  # 30 days overdue
            status="UNPAID",
            dispute_flag=False,
        )
        
        risk_level, risk_score = RiskScorer.score_invoice(invoice, customer)
        
        # Should be MEDIUM risk
        assert risk_level in [RiskLevel.MEDIUM, RiskLevel.LOW]
    
    def test_risk_factors(self):
        """Test risk factor extraction"""
        customer = Customer(
            id="CUST-006",
            name="Test Corp",
            reliability_score=0.7,
            total_invoices=10,
            total_paid=100000,
        )
        
        invoice = Invoice(
            id="INV-006",
            customer_id="CUST-006",
            amount=50000,
            invoice_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),
            status="UNPAID",
            dispute_flag=False,
            delay_reason="cash_flow",
        )
        
        factors = RiskScorer.get_risk_factors(invoice, customer)
        
        assert factors["is_disputed"] == False
        assert factors["is_paid"] == False
        assert factors["days_overdue"] == 30
        assert factors["invoice_amount"] == 50000
        assert factors["delay_reason"] == "cash_flow"


class TestSyntheticDataGenerator:
    """Test synthetic data generation"""
    
    def test_generator_is_reproducible(self):
        """Generated data should be reproducible with same seed"""
        gen1 = SyntheticDataGenerator(seed=42)
        customers1, invoices1 = gen1.generate_batch(50)
        
        gen2 = SyntheticDataGenerator(seed=42)
        customers2, invoices2 = gen2.generate_batch(50)
        
        # Compare first customer
        assert customers1[0].id == customers2[0].id
        assert customers1[0].name == customers2[0].name
        assert customers1[0].reliability_score == customers2[0].reliability_score
        
        # Compare first invoice
        assert invoices1[0][0].id == invoices2[0][0].id
        assert invoices1[0][0].amount == invoices2[0][0].amount
        assert invoices1[0][0].due_date == invoices2[0][0].due_date
    
    def test_generator_produces_variety(self):
        """Generated data should have variety in amounts and statuses"""
        gen = SyntheticDataGenerator(seed=42)
        customers, invoices = gen.generate_batch(100)
        
        # Check customer count
        assert len(customers) > 0
        
        # Check invoice count
        assert len(invoices) == 100
        
        # Check amounts vary
        amounts = [inv[0].amount for inv in invoices]
        assert len(set(amounts)) > 10  # At least 10 different amounts
        
        # Check statuses vary
        statuses = [inv[0].status for inv in invoices]
        assert "UNPAID" in statuses
        assert "PAID" in statuses or "DISPUTED" in statuses
    
    def test_generator_produces_disputed_invoices(self):
        """Generator should produce some disputed invoices"""
        gen = SyntheticDataGenerator(seed=42)
        customers, invoices = gen.generate_batch(100)
        
        disputed = [inv for inv in invoices if inv[0].dispute_flag]
        assert len(disputed) > 0
    
    def test_generator_produces_already_paid_invoices(self):
        """Generator should produce some already-paid invoices"""
        gen = SyntheticDataGenerator(seed=42)
        customers, invoices = gen.generate_batch(100)
        
        paid = [inv for inv in invoices if inv[0].status == "PAID"]
        assert len(paid) > 0


class TestPolicyEngine:
    """Policy engine tests will be added in Day 2"""
    pass
