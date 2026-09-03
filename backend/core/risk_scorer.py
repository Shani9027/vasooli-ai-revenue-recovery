from datetime import datetime, date
from config.constants import RiskLevel, LOW_RISK_SCORE, MEDIUM_RISK_SCORE, HIGH_RISK_SCORE
from database.models import Invoice, Customer


class RiskScorer:
    """
    Deterministic risk scoring for overdue invoices.
    
    Rules:
    1. Any disputed invoice → BLOCKED (regardless of score)
    2. Already paid → LOW (score = 0)
    3. Else: score = f(days_overdue, amount, customer_reliability, history)
    
    Scoring formula:
    - Base score from days overdue: 0-40 points
    - Amount factor: 0-30 points
    - Customer reliability: -15 to +15 points adjustment
    - Previous recovery success: 0-15 points
    
    Risk levels:
    - 0-30: LOW
    - 31-60: MEDIUM
    - 61-100: HIGH
    - DISPUTED: BLOCKED
    """
    
    @staticmethod
    def score_invoice(invoice: Invoice, customer: Customer) -> tuple:
        """
        Score an invoice for revenue-at-risk.
        
        Returns: (risk_level, risk_score)
        """
        
        # Rule 1: Disputed invoices are always BLOCKED
        if invoice.dispute_flag:
            return RiskLevel.BLOCKED, 0
        
        # Rule 2: Already paid invoices are LOW risk
        if invoice.status == "PAID":
            return RiskLevel.LOW, 0
        
        # Calculate days overdue
        today = date.today()
        days_overdue = (today - invoice.due_date).days
        
        # If not yet due, mark as LOW
        if days_overdue <= 0:
            return RiskLevel.LOW, 0
        
        # Calculate base risk score (0-100)
        score = 0
        
        # 1. Days overdue component (0-40 points)
        if days_overdue <= 7:
            days_score = 5
        elif days_overdue <= 30:
            days_score = 15
        elif days_overdue <= 60:
            days_score = 25
        elif days_overdue <= 90:
            days_score = 35
        else:
            days_score = 40  # 90+ days
        
        score += days_score
        
        # 2. Invoice amount component (0-30 points)
        # Higher amounts = higher risk
        if invoice.amount < 25000:
            amount_score = 5
        elif invoice.amount < 100000:
            amount_score = 15
        elif invoice.amount < 250000:
            amount_score = 25
        else:
            amount_score = 30
        
        score += amount_score
        
        # 3. Customer reliability adjustment (-15 to +15 points)
        # More reliable customers = lower score
        reliability_adjustment = (0.5 - customer.reliability_score) * 30
        score += reliability_adjustment
        
        # 4. Payment history adjustment (0-15 points)
        # Customers with good payment history = lower score
        if customer.total_invoices > 0:
            payment_ratio = customer.total_paid / (customer.total_paid + 10000)
            if payment_ratio > 0.9:
                history_adjustment = -15
            elif payment_ratio > 0.7:
                history_adjustment = -10
            elif payment_ratio > 0.5:
                history_adjustment = -5
            else:
                history_adjustment = 0
        else:
            history_adjustment = 0
        
        score += history_adjustment
        
        # Clamp score to 0-100
        score = max(0, min(100, score))
        
        # Determine risk level
        if score <= LOW_RISK_SCORE:
            risk_level = RiskLevel.LOW
        elif score <= MEDIUM_RISK_SCORE:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.HIGH
        
        return risk_level, score
    
    @staticmethod
    def get_risk_factors(invoice: Invoice, customer: Customer) -> dict:
        """
        Get detailed breakdown of risk factors for an invoice.
        Useful for debugging and audit trail.
        """
        today = date.today()
        days_overdue = (today - invoice.due_date).days
        
        factors = {
            "is_disputed": invoice.dispute_flag,
            "is_paid": invoice.status == "PAID",
            "days_overdue": days_overdue,
            "invoice_amount": invoice.amount,
            "customer_reliability": customer.reliability_score,
            "customer_total_invoices": customer.total_invoices,
            "customer_total_paid": customer.total_paid,
            "delay_reason": invoice.delay_reason,
        }
        
        return factors
