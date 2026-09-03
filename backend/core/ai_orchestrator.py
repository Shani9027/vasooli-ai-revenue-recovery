"""
AI Orchestrator for Vasooli recovery workflow.
Coordinates diagnosis, action proposal, policy validation, and execution.
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from database.models import Customer, Invoice, Case
from core.risk_scorer import RiskScorer
from core.policy_engine import PolicyEngine
from core.audit_logger import audit_logger
from ai.provider import AIProviderFactory
from executor.action_executor import ActionExecutor
from config.constants import Actor, AuditEventType, CaseStatus


class AIOrchestrator:
    """Coordinates the complete recovery workflow"""

    def __init__(self, db: Session, simulator_seed: int = 42):
        self.db = db
        self.policy_engine = PolicyEngine(db)
        self.action_executor = ActionExecutor(db, simulator_seed=simulator_seed)
        self.ai_provider = AIProviderFactory.get_provider()

    def run_recovery_for_case(self, case: Case) -> Dict[str, Any]:
        """
        Run complete recovery workflow for a single case.

        Workflow:
        1. Fetch invoice and customer
        2. Analyze with AI (diagnosis)
        3. Get AI action proposal
        4. Validate through policy engine
        5. Execute approved action
        6. Update case state
        7. Log all events

        Returns: Dictionary with workflow result
        """

        invoice = self.db.query(Invoice).filter(Invoice.id == case.invoice_id).first()
        customer = (
            self.db.query(Customer).filter(Customer.id == case.customer_id).first()
        )

        if not invoice or not customer:
            return {
                "case_id": case.id,
                "success": False,
                "error": "Invoice or customer not found",
            }

        # Skip if case already completed
        if case.status in [CaseStatus.PAYMENT_RECEIVED, CaseStatus.STOPPED]:
            return {
                "case_id": case.id,
                "success": False,
                "reason": f"Case already {case.status}",
            }

        try:
            # Step 1: Get customer payment history summary
            payment_history_str = self._get_payment_history_summary(customer)

            # Step 2: AI Diagnosis
            diagnosis = self.ai_provider.diagnose(
                invoice_amount=invoice.amount,
                days_overdue=(datetime.now().date() - invoice.due_date).days
                if invoice.due_date
                else 0,
                customer_name=customer.name,
                reliability_score=customer.reliability_score,
                payment_history=payment_history_str,
                delay_reason=invoice.delay_reason,
                dispute_status="DISPUTED" if invoice.dispute_flag else "OK",
                escalation_stage=case.escalation_stage,
            )

            # Log diagnosis
            audit_logger.log_event(
                event_type=AuditEventType.DIAGNOSIS,
                actor=Actor.LLM,
                case_id=case.id,
                input_data={
                    "invoice_amount": invoice.amount,
                    "days_overdue": (datetime.now().date() - invoice.due_date).days
                    if invoice.due_date
                    else 0,
                    "customer": customer.name,
                    "reliability": customer.reliability_score,
                },
                output_data={
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                passed=True,
                reason="Diagnosis complete",
            )

            # Step 3: AI Action Proposal
            action_proposal = self.ai_provider.propose_action(
                diagnosis=diagnosis,
                invoice_amount=invoice.amount,
                days_overdue=(datetime.now().date() - invoice.due_date).days
                if invoice.due_date
                else 0,
                customer_name=customer.name,
                reliability_score=customer.reliability_score,
                escalation_stage=case.escalation_stage,
                previous_attempts=self.db.query(
                    __import__("database.models", fromlist=["Action"]).Action
                )
                .filter(
                    __import__("database.models", fromlist=["Action"]).Action.case_id
                    == case.id
                )
                .count(),
            )

            # Log action proposal
            audit_logger.log_event(
                event_type=AuditEventType.ACTION_PROPOSAL,
                actor=Actor.LLM,
                case_id=case.id,
                input_data={"diagnosis": diagnosis.root_cause},
                output_data={
                    "proposed_action": action_proposal.proposed_action,
                    "confidence": action_proposal.confidence,
                    "reasoning": action_proposal.reasoning,
                },
                passed=True,
                reason="Action proposed",
            )

            # Step 4: Policy Engine Validation
            policy_result = self.policy_engine.validate_action(
                case=case,
                invoice=invoice,
                customer=customer,
                proposed_action=action_proposal.proposed_action,
                ai_confidence=action_proposal.confidence,
            )

            # Log policy check
            audit_logger.log_event(
                event_type=AuditEventType.POLICY_CHECK,
                actor=Actor.POLICY_ENGINE,
                case_id=case.id,
                input_data={
                    "proposed_action": action_proposal.proposed_action,
                    "ai_confidence": action_proposal.confidence,
                },
                output_data=policy_result.to_dict(),
                passed=policy_result.approved,
                reason=policy_result.reason,
            )

            # Step 5: Execute Action
            action_result = self.action_executor.execute_action(
                case=case,
                invoice=invoice,
                customer=customer,
                action_type=action_proposal.proposed_action,
                ai_confidence=action_proposal.confidence,
                policy_approved=policy_result.approved,
                policy_reason=policy_result.reason,
            )

            return {
                "case_id": case.id,
                "success": (action_result.status == "EXECUTED"),
                "invoice_id": invoice.id,
                "diagnosis": {
                    "root_cause": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                },
                "proposed_action": action_proposal.proposed_action,
                "policy_result": policy_result.to_dict(),
                "action_executed": action_result.action_type,
                "customer_response": action_result.customer_response,
                "revenue_recovered": case.revenue_recovered,
            }

        except Exception as e:
            # Log error
            audit_logger.log_event(
                event_type=AuditEventType.ACTION_EXECUTED,
                actor=Actor.SYSTEM,
                case_id=case.id,
                input_data={},
                output_data={"error": str(e)},
                passed=False,
                reason=f"Workflow error: {str(e)[:200]}",
            )

            return {
                "case_id": case.id,
                "success": False,
                "error": str(e)[:200],
            }

    def _get_payment_history_summary(self, customer: Customer) -> str:
        """Get payment history summary for AI context"""
        total_invoices = customer.total_invoices or 0
        total_paid = customer.total_paid or 0

        if total_invoices == 0:
            return "No payment history"

        payment_rate = total_paid / total_invoices
        score = customer.reliability_score

        if score >= 0.8:
            return f"Reliable payer ({payment_rate:.0%} on-time)"
        elif score >= 0.6:
            return f"Mostly reliable ({payment_rate:.0%} on-time)"
        elif score >= 0.4:
            return f"Inconsistent payment ({payment_rate:.0%} on-time)"
        else:
            return f"High-risk customer ({payment_rate:.0%} on-time)"
