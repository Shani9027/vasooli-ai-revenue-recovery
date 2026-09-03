from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional
from database.models import Case, Invoice, Action, Promise, Customer
from config.constants import (
    MAX_CONTACT_ATTEMPTS,
    COOLDOWN_AFTER_PROMISE_DAYS,
    CONTACT_FREQUENCY_PER_DAY,
    PROMISE_CONFIDENCE_THRESHOLD,
)


class PolicyCheckResult:
    """Result of a policy check"""
    
    def __init__(
        self,
        approved: bool,
        final_action: str,
        reason: str,
        rule_checks: List[Dict[str, Any]],
    ):
        self.approved = approved
        self.final_action = final_action
        self.reason = reason
        self.rule_checks = rule_checks
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "final_action": self.final_action,
            "reason": self.reason,
            "rule_checks": self.rule_checks,
        }


class PolicyEngine:
    """
    Deterministic policy validation for all recovery actions.
    
    The policy engine enforces guardrails and can override/downgrade/block
    any AI-proposed action.
    
    All checks are deterministic and auditable.
    """
    
    def __init__(self, db_session):
        self.db_session = db_session
    
    def validate_action(
        self,
        case: Case,
        invoice: Invoice,
        customer: Customer,
        proposed_action: str,
        ai_confidence: Optional[float] = None,
    ) -> PolicyCheckResult:
        """
        Validate a proposed recovery action against all policy guardrails.
        
        Args:
            case: The recovery case
            invoice: The invoice
            customer: The customer
            proposed_action: The AI-proposed action
            ai_confidence: AI confidence in the proposal
        
        Returns:
            PolicyCheckResult with approval status and reasoning
        """
        
        rule_checks = []
        
        # Rule 1: Disputed invoice = automatic BLOCK
        if invoice.dispute_flag:
            rule_checks.append({
                "rule": "disputed_invoice",
                "passed": False,
                "input": {"dispute_flag": invoice.dispute_flag},
                "reason": f"Invoice {invoice.id} is disputed: {invoice.dispute_reason}"
            })
            return PolicyCheckResult(
                approved=False,
                final_action="BLOCK",
                reason="Disputed invoice - automation blocked",
                rule_checks=rule_checks,
            )
        else:
            rule_checks.append({
                "rule": "disputed_invoice",
                "passed": True,
                "input": {"dispute_flag": invoice.dispute_flag},
                "reason": "Invoice not disputed"
            })
        
        # Rule 2: Already paid = automatic STOP
        if invoice.status == "PAID":
            rule_checks.append({
                "rule": "already_paid",
                "passed": False,
                "input": {"invoice_status": invoice.status},
                "reason": f"Invoice {invoice.id} already paid"
            })
            return PolicyCheckResult(
                approved=False,
                final_action="STOP",
                reason="Invoice already paid - recovery complete",
                rule_checks=rule_checks,
            )
        else:
            rule_checks.append({
                "rule": "already_paid",
                "passed": True,
                "input": {"invoice_status": invoice.status},
                "reason": "Invoice is unpaid"
            })
        
        # Rule 3: Maximum contact attempts check
        max_attempts_passed = self._check_max_attempts(case, rule_checks)
        
        # Rule 4: Contact frequency check
        frequency_passed = self._check_contact_frequency(case, rule_checks)
        
        # Rule 5: Escalation stage check
        stage_passed = self._check_escalation_stage(
            case, proposed_action, rule_checks
        )
        
        # Rule 6: Cooldown after promise check
        cooldown_passed = self._check_cooldown_after_promise(case, rule_checks)
        
        # Rule 7: AI confidence threshold
        confidence_passed = self._check_confidence_threshold(
            proposed_action, ai_confidence, rule_checks
        )
        
        # Determine overall approval
        all_passed = all([
            max_attempts_passed,
            frequency_passed,
            stage_passed,
            cooldown_passed,
            confidence_passed,
        ])
        
        if all_passed:
            return PolicyCheckResult(
                approved=True,
                final_action=proposed_action,
                reason="All policy checks passed",
                rule_checks=rule_checks,
            )
        else:
            # Find which rules failed
            failed_rules = [r for r in rule_checks if not r.get("passed", True)]
            failed_names = [r["rule"] for r in failed_rules]
            
            return PolicyCheckResult(
                approved=False,
                final_action="BLOCK",
                reason=f"Policy check failed: {', '.join(failed_names)}",
                rule_checks=rule_checks,
            )
    
    def _check_max_attempts(self, case: Case, rule_checks: List) -> bool:
        """Check if maximum contact attempts reached"""
        try:
            action_count = self.db_session.query(Action).filter(
                Action.case_id == case.id,
                Action.status.in_(["EXECUTED", "APPROVED"])
            ).count()
            
            passed = action_count < MAX_CONTACT_ATTEMPTS
            rule_checks.append({
                "rule": "max_attempts",
                "passed": passed,
                "input": {
                    "current_attempts": action_count,
                    "max_allowed": MAX_CONTACT_ATTEMPTS
                },
                "reason": f"{action_count}/{MAX_CONTACT_ATTEMPTS} attempts used"
            })
            return passed
        except Exception as e:
            rule_checks.append({
                "rule": "max_attempts",
                "passed": True,
                "input": {},
                "reason": f"Error checking attempts: {e} (allowing)"
            })
            return True
    
    def _check_contact_frequency(self, case: Case, rule_checks: List) -> bool:
        """Check contact frequency (no more than X contacts per day)"""
        try:
            today = datetime.utcnow().date()
            today_start = datetime.combine(today, datetime.min.time())
            
            contact_count = self.db_session.query(Action).filter(
                Action.case_id == case.id,
                Action.created_at >= today_start,
                Action.status.in_(["EXECUTED", "APPROVED"])
            ).count()
            
            passed = contact_count < CONTACT_FREQUENCY_PER_DAY
            rule_checks.append({
                "rule": "contact_frequency",
                "passed": passed,
                "input": {
                    "contacts_today": contact_count,
                    "max_per_day": CONTACT_FREQUENCY_PER_DAY
                },
                "reason": f"{contact_count}/{CONTACT_FREQUENCY_PER_DAY} contacts today"
            })
            return passed
        except Exception as e:
            rule_checks.append({
                "rule": "contact_frequency",
                "passed": True,
                "input": {},
                "reason": f"Error checking frequency: {e} (allowing)"
            })
            return True
    
    def _check_escalation_stage(
        self,
        case: Case,
        proposed_action: str,
        rule_checks: List
    ) -> bool:
        """Check if proposed action is allowed at current escalation stage"""
        
        # Define allowed actions per stage
        stage_actions = {
            1: ["gentle_nudge", "payment_retry", "stop"],
            2: ["gentle_nudge", "firm_reminder", "payment_retry", "stop"],
            3: ["firm_reminder", "payment_link", "promise_to_pay", "human_escalation", "stop"],
            4: ["human_escalation", "stop"],
        }
        
        stage = case.escalation_stage
        allowed = stage_actions.get(stage, ["stop"])
        
        passed = proposed_action in allowed
        rule_checks.append({
            "rule": "escalation_stage",
            "passed": passed,
            "input": {
                "stage": stage,
                "proposed_action": proposed_action,
                "allowed_actions": allowed
            },
            "reason": f"Stage {stage}: action '{proposed_action}' {'is' if passed else 'is NOT'} allowed"
        })
        return passed
    
    def _check_cooldown_after_promise(self, case: Case, rule_checks: List) -> bool:
        """Check cooldown period after a promise is made"""
        try:
            # Get most recent promise for this case
            latest_promise = self.db_session.query(Promise).filter(
                Promise.case_id == case.id,
                Promise.status == "MADE"
            ).order_by(Promise.created_at.desc()).first()
            
            if latest_promise is None:
                rule_checks.append({
                    "rule": "cooldown_after_promise",
                    "passed": True,
                    "input": {"latest_promise": None},
                    "reason": "No active promise - no cooldown"
                })
                return True
            
            # Check if cooldown period has passed
            elapsed_days = (datetime.utcnow().date() - latest_promise.created_at.date()).days
            passed = elapsed_days >= COOLDOWN_AFTER_PROMISE_DAYS
            
            rule_checks.append({
                "rule": "cooldown_after_promise",
                "passed": passed,
                "input": {
                    "promise_created": latest_promise.created_at.isoformat(),
                    "elapsed_days": elapsed_days,
                    "required_days": COOLDOWN_AFTER_PROMISE_DAYS
                },
                "reason": f"Promise cooldown: {elapsed_days}/{COOLDOWN_AFTER_PROMISE_DAYS} days"
            })
            return passed
        except Exception as e:
            rule_checks.append({
                "rule": "cooldown_after_promise",
                "passed": True,
                "input": {},
                "reason": f"Error checking cooldown: {e} (allowing)"
            })
            return True
    
    def _check_confidence_threshold(
        self,
        proposed_action: str,
        ai_confidence: Optional[float],
        rule_checks: List
    ) -> bool:
        """
        Check AI confidence threshold.
        
        Low confidence actions are not blocked but flagged.
        For now, we allow them to proceed.
        """
        if ai_confidence is None:
            passed = True
            reason = "No AI confidence score"
        else:
            passed = ai_confidence >= PROMISE_CONFIDENCE_THRESHOLD
            reason = f"Confidence {ai_confidence:.2f}/{PROMISE_CONFIDENCE_THRESHOLD}"
        
        rule_checks.append({
            "rule": "confidence_threshold",
            "passed": passed,
            "input": {
                "confidence": ai_confidence,
                "threshold": PROMISE_CONFIDENCE_THRESHOLD
            },
            "reason": reason
        })
        return passed
