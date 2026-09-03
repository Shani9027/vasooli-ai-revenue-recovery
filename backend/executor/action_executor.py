"""
Action executor for recovery workflow.
Executes actions and simulates customer responses.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, date
import uuid as uuid_lib
from sqlalchemy.orm import Session

from simulator.customer_simulator import CustomerSimulator, CustomerResponseType
from database.models import Customer, Invoice, Case, Action, Promise
from database.schema import ActionResponse
from core.audit_logger import audit_logger
from config.constants import (
    ActionStatus,
    ActionType,
    Actor,
    AuditEventType,
    CaseStatus,
    PromiseStatus,
)
from ai.provider import AIProviderFactory
from integrations.razorpay_client import RazorpayTestClient


class ActionExecutor:
    """Executes approved recovery actions"""

    def __init__(
        self,
        db: Session,
        simulator_seed: int = 42,
        razorpay_client: Optional[RazorpayTestClient] = None,
    ):
        self.db = db
        self.simulator = CustomerSimulator(seed=simulator_seed)
        self.ai_provider = AIProviderFactory.get_provider()
        self.razorpay_client = (
            razorpay_client if razorpay_client is not None else RazorpayTestClient()
        )

    def execute_action(
        self,
        case: Case,
        invoice: Invoice,
        customer: Customer,
        action_type: str,
        ai_confidence: float,
        policy_approved: bool,
        policy_reason: str,
    ) -> ActionResponse:
        """
        Execute recovery action and simulate customer response.
        Returns ActionResponse with result details.
        """

        # Freshly check payment status right before executing action (near-miss check)
        self.db.refresh(invoice)
        if invoice.status == "PAID" or case.status == CaseStatus.PAYMENT_RECEIVED:
            case.status = CaseStatus.PAYMENT_RECEIVED
            case.revenue_recovered = min(invoice.amount, case.revenue_recovered or invoice.amount)
            
            action = Action(
                id=f"ACTION-{uuid_lib.uuid4().hex[:12]}",
                case_id=case.id,
                action_type=action_type,
                status=ActionStatus.BLOCKED,
                ai_confidence=ai_confidence,
                policy_approved=False,
                customer_response="Action cancelled: Payment already received",
                response_type="near_miss_prevented",
            )
            self.db.add(action)
            self.db.add(case)
            self.db.commit()

            # Create near_miss_prevented audit event
            audit_logger.log_event(
                event_type=AuditEventType.NEAR_MISS_PREVENTED,
                actor=Actor.SYSTEM,
                case_id=case.id,
                input_data={
                    "invoice_id": invoice.id,
                    "invoice_status": invoice.status,
                    "action_type": action_type,
                    "amount": invoice.amount,
                },
                output_data={"status": "CANCELLED", "event": "near_miss_prevented"},
                passed=True,
                reason="Payment verified prior to action execution - near miss prevented",
            )

            return ActionResponse.model_validate(action)

        # Create action record with unique ID
        action = Action(
            id=f"ACTION-{uuid_lib.uuid4().hex[:12]}",
            case_id=case.id,
            action_type=action_type,
            status=ActionStatus.EXECUTED if policy_approved else ActionStatus.BLOCKED,
            ai_confidence=ai_confidence,
            policy_approved=policy_approved,
        )

        if not policy_approved:
            action.status = ActionStatus.BLOCKED
            
            # Update case status according to why policy blocked it
            if invoice.dispute_flag or "dispute" in policy_reason.lower():
                case.status = CaseStatus.STOPPED
                invoice.status = "DISPUTED"
            elif invoice.status == "PAID" or "already paid" in policy_reason.lower():
                case.status = CaseStatus.PAYMENT_RECEIVED
                case.revenue_recovered = min(invoice.amount, case.revenue_recovered or invoice.amount)
            elif "max_attempts" in policy_reason.lower() or "attempt" in policy_reason.lower():
                case.status = CaseStatus.ESCALATED
            elif "confidence" in policy_reason.lower():
                case.status = CaseStatus.HUMAN_REVIEW
            else:
                case.status = CaseStatus.STOPPED

            self.db.add(action)
            self.db.add(case)
            self.db.commit()

            # Log blocked action
            audit_logger.log_event(
                event_type=AuditEventType.ACTION_EXECUTED,
                actor=Actor.SYSTEM,
                case_id=case.id,
                input_data={
                    "action": action_type,
                    "ai_confidence": ai_confidence,
                },
                output_data={"status": "BLOCKED", "reason": policy_reason, "case_status": case.status},
                passed=False,
                reason=policy_reason,
            )

            return ActionResponse.model_validate(action)

        # Check if action is a payment retry / payment link and Razorpay test mode is configured
        is_payment_action = action_type in [
            ActionType.PAYMENT_RETRY,
            ActionType.PAYMENT_LINK,
            "payment_retry",
            "payment_link",
        ]

        if is_payment_action and self.razorpay_client and self.razorpay_client.is_configured():
            try:
                rzp_result = self.razorpay_client.create_payment_retry(
                    invoice_id=invoice.id,
                    amount=invoice.amount,
                    customer_id=customer.id,
                    customer_name=customer.name,
                )
            except Exception as rzp_err:
                rzp_result = {"success": False, "error": str(rzp_err)}

            audit_logger.set_session(self.db)

            if rzp_result.get("success"):
                transaction_id = rzp_result.get("transaction_id")
                invoice.status = "PAID"
                case.status = CaseStatus.PAYMENT_RECEIVED
                case.revenue_recovered = invoice.amount
                action.status = ActionStatus.EXECUTED
                action.response_type = CustomerResponseType.PAID.value
                action.customer_response = (
                    f"Payment processed via Razorpay Test Mode (Order #{transaction_id})"
                )

                self.db.add(action)
                self.db.add(case)
                self.db.add(invoice)
                self.db.commit()

                # Audit event for action execution via razorpay_test
                audit_logger.log_event(
                    event_type=AuditEventType.ACTION_EXECUTED,
                    actor=Actor.RAZORPAY_TEST,
                    case_id=case.id,
                    input_data={
                        "action": action_type,
                        "provider": "razorpay_test",
                        "invoice_id": invoice.id,
                        "amount": invoice.amount,
                    },
                    output_data={
                        "provider": "razorpay_test",
                        "status": "SUCCESS",
                        "transaction_id": transaction_id,
                        "revenue_recovered": invoice.amount,
                    },
                    passed=True,
                    reason=f"Payment recovered via Razorpay Test Mode (Order #{transaction_id})",
                    metadata={"provider": "razorpay_test", "transaction_id": transaction_id},
                )

                # Audit event for payment received via razorpay_test
                audit_logger.log_event(
                    event_type=AuditEventType.PAYMENT_RECEIVED,
                    actor=Actor.RAZORPAY_TEST,
                    case_id=case.id,
                    input_data={"action": action_type, "provider": "razorpay_test"},
                    output_data={
                        "recovered": invoice.amount,
                        "provider": "razorpay_test",
                        "transaction_id": transaction_id,
                    },
                    passed=True,
                    reason="Payment received via Razorpay Test Mode",
                    metadata={"provider": "razorpay_test", "transaction_id": transaction_id},
                )

                return ActionResponse.model_validate(action)
            else:
                # Razorpay test attempt failed - log audit trail and fall back to simulator
                audit_logger.log_event(
                    event_type=AuditEventType.ACTION_EXECUTED,
                    actor=Actor.RAZORPAY_TEST,
                    case_id=case.id,
                    input_data={
                        "action": action_type,
                        "provider": "razorpay_test",
                        "invoice_id": invoice.id,
                        "amount": invoice.amount,
                    },
                    output_data={
                        "provider": "razorpay_test",
                        "status": "FAILED",
                        "error": rzp_result.get("error"),
                    },
                    passed=False,
                    reason=f"Razorpay Test Mode attempt failed: {rzp_result.get('error')}. Falling back to simulator.",
                    metadata={"provider": "razorpay_test", "fallback": "simulator"},
                )

        # Action approved - simulate customer response (simulator fallback / demo mode)
        customer_profile = self._get_customer_profile(customer)

        response_type, response_text = self.simulator.simulate_response(
            action=action_type,
            customer_profile=customer_profile,
            invoice_amount=invoice.amount,
            days_overdue=(datetime.now().date() - invoice.due_date).days
            if invoice.due_date
            else 0,
            escalation_stage=case.escalation_stage,
            previous_attempts=self.db.query(Action)
            .filter(Action.case_id == case.id)
            .count(),
            reliability_score=customer.reliability_score,
        )

        action.customer_response = response_text
        action.response_type = response_type.value

        # Process response
        promise = None
        case_updated = False
        payment_transaction_id = None

        if response_type == CustomerResponseType.PAID:
            # Payment received
            invoice.status = "PAID"
            case.status = CaseStatus.PAYMENT_RECEIVED
            case.revenue_recovered = invoice.amount
            action.status = ActionStatus.EXECUTED
            case_updated = True

            # If Razorpay test client is configured, process and record via Razorpay Test Mode
            if self.razorpay_client and self.razorpay_client.is_configured():
                try:
                    rzp_result = self.razorpay_client.create_payment_retry(
                        invoice_id=invoice.id,
                        amount=invoice.amount,
                        customer_id=customer.id,
                        customer_name=customer.name,
                    )
                except Exception as rzp_err:
                    rzp_result = {"success": False, "error": str(rzp_err)}

                if rzp_result.get("success"):
                    payment_transaction_id = rzp_result.get("transaction_id")
                    action.customer_response = (
                        f"Payment processed via Razorpay Test Mode (Order #{payment_transaction_id})"
                    )

                    audit_logger.log_event(
                        event_type=AuditEventType.PAYMENT_RECEIVED,
                        actor=Actor.RAZORPAY_TEST,
                        case_id=case.id,
                        input_data={"action": action_type, "provider": "razorpay_test"},
                        output_data={
                            "recovered": invoice.amount,
                            "provider": "razorpay_test",
                            "transaction_id": payment_transaction_id,
                        },
                        passed=True,
                        reason=f"Payment received via Razorpay Test Mode (Order #{payment_transaction_id})",
                        metadata={"provider": "razorpay_test", "transaction_id": payment_transaction_id},
                    )

            if not payment_transaction_id:
                # Simulator fallback if Razorpay unconfigured or API fails
                audit_logger.log_event(
                    event_type=AuditEventType.PAYMENT_RECEIVED,
                    actor=Actor.SIMULATOR,
                    case_id=case.id,
                    input_data={"action": action_type, "provider": "simulator"},
                    output_data={"recovered": invoice.amount, "provider": "simulator"},
                    passed=True,
                    reason="Payment received",
                    metadata={"provider": "simulator"},
                )

        elif response_type == CustomerResponseType.PROMISE_TO_PAY:
            # Extract promise
            promise_output = self.ai_provider.extract_promise(
                customer_response=response_text,
                invoice_amount=invoice.amount,
            )

            if promise_output.confidence >= 0.6:
                # High confidence - create promise with proper date object
                p_date = promise_output.promised_date
                if isinstance(p_date, str):
                    try:
                        p_date = date.fromisoformat(p_date[:10])
                    except Exception:
                        p_date = (datetime.now() + timedelta(days=7)).date()
                elif isinstance(p_date, datetime):
                    p_date = p_date.date()
                elif p_date is None:
                    p_date = (datetime.now() + timedelta(days=7)).date()

                promise = Promise(
                    id=f"PROMISE-{uuid_lib.uuid4().hex[:12]}",
                    case_id=case.id,
                    action_id=action.id,
                    promised_amount=promise_output.promised_amount,
                    promised_date=p_date,
                    extraction_confidence=promise_output.confidence,
                    status=PromiseStatus.MADE,
                    promise_text=response_text,
                    customer_response_text=response_text,
                )
                self.db.add(promise)
                action.status = ActionStatus.EXECUTED

                audit_logger.log_event(
                    event_type=AuditEventType.PROMISE_EXTRACTED,
                    actor=Actor.SIMULATOR,
                    case_id=case.id,
                    input_data={"response": response_text},
                    output_data={
                        "promised_amount": promise_output.promised_amount,
                        "promised_date": promise_output.promised_date,
                        "confidence": promise_output.confidence,
                    },
                    passed=True,
                    reason="Promise extracted with high confidence",
                )
            else:
                # Low confidence - escalate to human review
                case.status = CaseStatus.HUMAN_REVIEW
                action.status = ActionStatus.EXECUTED
                case_updated = True

                audit_logger.log_event(
                    event_type=AuditEventType.ACTION_EXECUTED,
                    actor=Actor.SIMULATOR,
                    case_id=case.id,
                    input_data={"response": response_text},
                    output_data={"status": "HUMAN_REVIEW"},
                    passed=True,
                    reason=f"Promise extracted but low confidence: {promise_output.confidence:.2f}",
                )

        elif response_type == CustomerResponseType.PARTIAL_PAYMENT:
            # Partial payment recorded
            partial_amount = invoice.amount / 2
            case.revenue_recovered = (case.revenue_recovered or 0) + partial_amount
            action.status = ActionStatus.EXECUTED

            # If Razorpay test client is configured, process partial payment in Test Mode
            if self.razorpay_client and self.razorpay_client.is_configured():
                try:
                    rzp_result = self.razorpay_client.create_payment_retry(
                        invoice_id=invoice.id,
                        amount=partial_amount,
                        customer_id=customer.id,
                        customer_name=customer.name,
                    )
                except Exception as rzp_err:
                    rzp_result = {"success": False, "error": str(rzp_err)}

                if rzp_result.get("success"):
                    payment_transaction_id = rzp_result.get("transaction_id")
                    audit_logger.log_event(
                        event_type=AuditEventType.PAYMENT_RECEIVED,
                        actor=Actor.RAZORPAY_TEST,
                        case_id=case.id,
                        input_data={"action": action_type, "provider": "razorpay_test"},
                        output_data={
                            "partial_recovery": partial_amount,
                            "provider": "razorpay_test",
                            "transaction_id": payment_transaction_id,
                        },
                        passed=True,
                        reason=f"Partial payment received via Razorpay Test Mode (Order #{payment_transaction_id})",
                        metadata={"provider": "razorpay_test", "transaction_id": payment_transaction_id},
                    )

            if not payment_transaction_id:
                audit_logger.log_event(
                    event_type=AuditEventType.PAYMENT_RECEIVED,
                    actor=Actor.SIMULATOR,
                    case_id=case.id,
                    input_data={"action": action_type, "provider": "simulator"},
                    output_data={"partial_recovery": partial_amount, "provider": "simulator"},
                    passed=True,
                    reason="Partial payment received",
                    metadata={"provider": "simulator"},
                )

        elif response_type == CustomerResponseType.DISPUTES:
            # Case disputed - stop recovery
            case.status = CaseStatus.STOPPED
            invoice.status = "DISPUTED"
            case_updated = True
            action.status = ActionStatus.FAILED

            audit_logger.log_event(
                event_type=AuditEventType.ACTION_EXECUTED,
                actor=Actor.SIMULATOR,
                case_id=case.id,
                input_data={"response": response_text},
                output_data={"status": "DISPUTED"},
                passed=False,
                reason="Customer disputes invoice",
            )

        elif response_type == CustomerResponseType.NO_RESPONSE:
            # No response - attempt next escalation
            action.status = ActionStatus.EXECUTED
            case.escalation_stage = min(case.escalation_stage + 1, 4)

        else:
            # Other response types - continue to next action
            action.status = ActionStatus.EXECUTED

        # Persist all changes
        self.db.add(action)
        if promise:
            self.db.add(promise)
        self.db.add(case)
        self.db.add(invoice)
        self.db.commit()

        # Log action execution
        if action.status == ActionStatus.EXECUTED:
            exec_actor = Actor.RAZORPAY_TEST if payment_transaction_id else Actor.SIMULATOR
            exec_provider = "razorpay_test" if payment_transaction_id else "simulator"
            extra_meta = {"transaction_id": payment_transaction_id} if payment_transaction_id else {}
            audit_logger.log_event(
                event_type=AuditEventType.ACTION_EXECUTED,
                actor=exec_actor,
                case_id=case.id,
                input_data={"action": action_type, "provider": exec_provider},
                output_data={
                    "provider": exec_provider,
                    "response": response_type.value,
                    "text": action.customer_response or response_text,
                    "revenue_recovered": case.revenue_recovered,
                    **extra_meta,
                },
                passed=True,
                reason=f"Action executed: {action_type}"
                + (f" (Order #{payment_transaction_id})" if payment_transaction_id else ""),
                metadata={"provider": exec_provider, **extra_meta},
            )

        return ActionResponse.model_validate(action)

    def _get_customer_profile(self, customer: Customer) -> str:
        """Determine customer profile based on reliability score and history"""
        score = customer.reliability_score

        if score >= 0.8:
            return "Reliable"
        elif score >= 0.6:
            return "Stable"
        elif score >= 0.4:
            return "Slow"
        elif score >= 0.2:
            return "StressPay"
        else:
            return "NonResp"
