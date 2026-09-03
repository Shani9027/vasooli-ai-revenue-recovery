"""
Mock LLM provider for development and testing without API keys.
Deterministic responses based on invoice context.
"""

from typing import Optional, Dict, Any
from ai.provider import (
    AIProvider,
    DiagnosisOutput,
    ActionProposal,
    PromiseExtraction,
)
from config.constants import ActionType
import random


class MockLLM(AIProvider):
    """Mock LLM that returns deterministic responses based on context"""

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)

    def diagnose(
        self,
        invoice_amount: float,
        days_overdue: int,
        customer_name: str,
        reliability_score: float,
        payment_history: str,
        delay_reason: Optional[str],
        dispute_status: str,
        escalation_stage: int,
    ) -> DiagnosisOutput:
        """
        Diagnose root cause with deterministic logic.
        """
        if dispute_status == "DISPUTED":
            return DiagnosisOutput(
                root_cause="Customer disputes invoice validity",
                confidence=0.95,
                context="Dispute flag set on invoice",
            )

        if days_overdue < 7:
            return DiagnosisOutput(
                root_cause="Recent overdue - possible transient payment issue",
                confidence=0.85,
                context="Invoice recently became overdue",
            )

        if days_overdue < 30:
            return DiagnosisOutput(
                root_cause="Cash-flow timing issue or payment method problem",
                confidence=0.80,
                context=f"Overdue by {days_overdue} days",
            )

        if "quality" in (delay_reason or "").lower():
            return DiagnosisOutput(
                root_cause="Quality-related payment hold",
                confidence=0.75,
                context=f"Delay reason: {delay_reason}",
            )

        if reliability_score < 0.4:
            return DiagnosisOutput(
                root_cause="Customer has history of payment delays",
                confidence=0.85,
                context=f"Low reliability score: {reliability_score}",
            )

        if days_overdue > 90:
            return DiagnosisOutput(
                root_cause="Chronic non-payment or company insolvency",
                confidence=0.80,
                context=f"Significantly overdue by {days_overdue} days",
            )

        return DiagnosisOutput(
            root_cause="Standard cash-flow or administrative delay",
            confidence=0.70,
            context="Generic overdue pattern",
        )

    def propose_action(
        self,
        diagnosis: DiagnosisOutput,
        invoice_amount: float,
        days_overdue: int,
        customer_name: str,
        reliability_score: float,
        escalation_stage: int,
        previous_attempts: int,
    ) -> ActionProposal:
        """
        Propose recovery action based on diagnosis and escalation stage.
        Deterministic strategy.
        """

        # Disputed invoices → stop
        if "dispute" in diagnosis.root_cause.lower():
            return ActionProposal(
                proposed_action=ActionType.STOP,
                reasoning="Cannot recover disputed invoice",
                confidence=0.95,
            )

        # Escalation stage logic
        if escalation_stage == 1:
            # Stage 1: gentle approaches
            if days_overdue < 15 and reliability_score > 0.7:
                return ActionProposal(
                    proposed_action=ActionType.GENTLE_NUDGE,
                    reasoning="Reliable customer, recent overdue - gentle reminder should work",
                    confidence=0.85,
                )
            elif "transient" in diagnosis.root_cause.lower():
                return ActionProposal(
                    proposed_action=ActionType.PAYMENT_RETRY,
                    reasoning="Likely transient payment issue - retry payment",
                    confidence=0.80,
                )
            else:
                return ActionProposal(
                    proposed_action=ActionType.GENTLE_NUDGE,
                    reasoning="Start with gentle approach at stage 1",
                    confidence=0.75,
                )

        elif escalation_stage == 2:
            # Stage 2: firmer approaches
            if "payment method" in diagnosis.root_cause.lower():
                return ActionProposal(
                    proposed_action=ActionType.PAYMENT_LINK,
                    reasoning="Customer needs easy payment method",
                    confidence=0.85,
                )
            elif "cash-flow" in diagnosis.root_cause.lower():
                return ActionProposal(
                    proposed_action=ActionType.PROMISE_TO_PAY,
                    reasoning="Likely needs time - extract commitment",
                    confidence=0.80,
                )
            else:
                return ActionProposal(
                    proposed_action=ActionType.FIRM_REMINDER,
                    reasoning="Escalate to firmer communication",
                    confidence=0.75,
                )

        elif escalation_stage == 3:
            # Stage 3: escalation
            if previous_attempts >= 2:
                return ActionProposal(
                    proposed_action=ActionType.HUMAN_ESCALATION,
                    reasoning="Multiple attempts failed - needs human intervention",
                    confidence=0.85,
                )
            else:
                return ActionProposal(
                    proposed_action=ActionType.FIRM_REMINDER,
                    reasoning="Last chance for automated recovery",
                    confidence=0.75,
                )

        else:
            # Stage 4: stop or human escalation
            return ActionProposal(
                proposed_action=ActionType.STOP,
                reasoning="Max automation reached",
                confidence=0.90,
            )

    def extract_promise(
        self,
        customer_response: str,
        invoice_amount: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> PromiseExtraction:
        """
        Extract promise details from customer response text.
        Mock implementation uses simple pattern matching.
        """
        response_lower = customer_response.lower()

        # Look for amount patterns (₹20000, 20000, 2 lakh, etc.)
        promised_amount = None
        promised_date = None
        confidence = 0.0

        # Simple extraction: look for numbers
        import re

        # Match patterns like "₹20000", "20000", "20k"
        amount_matches = re.findall(r"₹?(\d+)(?:k|000)?", customer_response)
        if amount_matches:
            # Use the first match as promised amount
            first_match = amount_matches[0]
            if "k" in customer_response.lower():
                promised_amount = int(first_match) * 1000
            else:
                promised_amount = int(first_match)
            confidence += 0.3

        # Look for date patterns
        date_patterns = [
            r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})",  # DD-MM-YYYY
            r"(kal|tomorrow|next week|next monday|by end of week|by friday)",
        ]

        for pattern in date_patterns:
            if re.search(pattern, customer_response, re.IGNORECASE):
                # Rough date estimation (for mock)
                if "kal" in response_lower or "tomorrow" in response_lower:
                    from datetime import datetime, timedelta

                    promised_date = (
                        datetime.now() + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                else:
                    from datetime import datetime, timedelta

                    promised_date = (
                        datetime.now() + timedelta(days=7)
                    ).strftime("%Y-%m-%d")
                confidence += 0.4
                break

        # Check for commitment language
        commitment_phrases = ["will pay", "pay", "promise", "kar dunga", "dunga"]
        if any(phrase in response_lower for phrase in commitment_phrases):
            confidence += 0.3

        # Default confidence if we found commitment but no details
        if confidence == 0.3 and "kal" in response_lower:
            confidence = 0.65

        # If we couldn't extract details, low confidence
        if not promised_amount or not promised_date:
            confidence = min(confidence, 0.40)
            promised_amount = promised_amount or invoice_amount / 2
            if not promised_date:
                from datetime import datetime, timedelta

                promised_date = (datetime.now() + timedelta(days=7)).strftime(
                    "%Y-%m-%d"
                )

        return PromiseExtraction(
            promised_amount=float(promised_amount),
            promised_date=promised_date,
            confidence=min(confidence, 0.95),
            extracted_text=customer_response,
        )
