"""
Deterministic customer response simulator for Vasooli.
Simulates customer reactions to recovery actions.
"""

from typing import Optional, Tuple
from enum import Enum
import random
from datetime import datetime, timedelta


class CustomerResponseType(str, Enum):
    """Types of customer responses"""
    PAID = "paid"
    PROMISE_TO_PAY = "promise_to_pay"
    PARTIAL_PAYMENT = "partial_payment"
    NO_RESPONSE = "no_response"
    ASKS_FOR_MORE_TIME = "asks_for_more_time"
    DISPUTES = "disputes"
    PAYMENT_FAILED = "payment_failed"


class CustomerSimulator:
    """
    Deterministic customer simulator.
    Responses based on customer profile and action type.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)

    def simulate_response(
        self,
        action: str,
        customer_profile: str,  # Reliable, Slow, StressPay, NonResp, Stable
        invoice_amount: float,
        days_overdue: int,
        escalation_stage: int,
        previous_attempts: int,
        reliability_score: float,
    ) -> Tuple[CustomerResponseType, str]:
        """
        Simulate customer response to action.
        Returns: (response_type, response_text)
        """

        # Deterministic seed per case (invoice_amount + escalation_stage)
        case_seed = int(invoice_amount * 1000) + escalation_stage * 100
        random.seed((self.seed + case_seed) % (2**31))

        # Disputed invoices never pay
        if customer_profile == "Disputed":
            return (
                CustomerResponseType.DISPUTES,
                "This invoice has a quality issue. We don't acknowledge this debt.",
            )

        # Stage 4 (max attempts): give up
        if escalation_stage >= 4:
            return (
                CustomerResponseType.NO_RESPONSE,
                "(No further response - case escalated)",
            )

        # Response probabilities based on profile
        profiles = {
            "Reliable": {
                "paid": 0.70,
                "promise": 0.15,
                "partial": 0.05,
                "no_response": 0.05,
                "ask_time": 0.03,
                "dispute": 0.02,
            },
            "Slow": {
                "paid": 0.30,
                "promise": 0.35,
                "partial": 0.15,
                "no_response": 0.12,
                "ask_time": 0.05,
                "dispute": 0.03,
            },
            "StressPay": {
                "paid": 0.20,
                "promise": 0.40,
                "partial": 0.20,
                "no_response": 0.12,
                "ask_time": 0.06,
                "dispute": 0.02,
            },
            "NonResp": {
                "paid": 0.05,
                "promise": 0.10,
                "partial": 0.05,
                "no_response": 0.60,
                "ask_time": 0.10,
                "dispute": 0.10,
            },
            "Stable": {
                "paid": 0.85,
                "promise": 0.08,
                "partial": 0.03,
                "no_response": 0.02,
                "ask_time": 0.01,
                "dispute": 0.01,
            },
        }

        probs = profiles.get(customer_profile, profiles["Slow"])

        # Adjust probabilities based on action
        if action == "gentle_nudge":
            probs["promise"] += 0.1
        elif action == "firm_reminder":
            probs["paid"] += 0.1
        elif action == "payment_retry":
            probs["paid"] += 0.15
        elif action == "payment_link":
            probs["paid"] += 0.2
        elif action == "promise_to_pay":
            probs["promise"] += 0.3
        elif action == "human_escalation":
            probs["paid"] += 0.05

        # Adjust for escalation stage
        if escalation_stage >= 2:
            probs["paid"] += 0.1
            probs["no_response"] -= 0.1

        # Random choice
        rand = random.random()
        cumulative = 0.0

        for response_type, prob in [
            ("paid", probs.get("paid", 0.3)),
            ("promise", probs.get("promise", 0.3)),
            ("partial", probs.get("partial", 0.1)),
            ("ask_time", probs.get("ask_time", 0.05)),
            ("payment_failed", probs.get("payment_failed", 0.05)),
            ("dispute", probs.get("dispute", 0.05)),
            ("no_response", probs.get("no_response", 0.15)),
        ]:
            cumulative += prob
            if rand <= cumulative:
                return self._generate_response_text(
                    response_type,
                    customer_profile,
                    invoice_amount,
                    escalation_stage,
                    action,
                )

        # Default fallback
        return (
            CustomerResponseType.NO_RESPONSE,
            "No response received",
        )

    def _generate_response_text(
        self,
        response_type: str,
        profile: str,
        amount: float,
        escalation: int,
        action: str,
    ) -> Tuple[CustomerResponseType, str]:
        """Generate realistic response text based on type and profile"""

        responses = {
            "paid": [
                "Payment sent today. Reference #PAY001",
                "Done! Check bank on Monday.",
                "Paid via NEFT this morning.",
                "₹{amount} paid now.",
                "Invoice settled.",
            ],
            "promise": [
                "Kal ₹{amount} kar dunga.",
                "By end of week sure.",
                "Next Monday payment hoga.",
                "₹{amount} Friday ko aayega.",
                "This week will pay ₹{amount}.",
                "Promise: ₹{amount} by {date}",
            ],
            "partial": [
                "Can pay ₹{half_amount} now, rest later.",
                "₹{half_amount} in 2 days, ₹{half_amount} next week.",
                f"Partial payment of ₹{{partial_amount}} sent.",
            ],
            "ask_time": [
                "Need 2 more weeks, cash-flow issue.",
                "Can we defer to 15th?",
                "Need a few days more.",
                "Money on the 10th for sure.",
            ],
            "no_response": [
                "(No response)",
                "(Customer not reachable)",
                "(Message not delivered)",
            ],
            "dispute": [
                "This invoice is wrong. Quality issue.",
                "We don't owe this amount.",
                "Disputed - see email for details.",
            ],
            "payment_failed": [
                "Payment failed - account issue.",
                "Card declined, trying wire transfer.",
                "Technical issue with payment.",
            ],
        }

        template = random.choice(responses.get(response_type, ["No response"]))

        # Replace placeholders
        half = amount / 2
        future_date = (datetime.now() + timedelta(days=random.randint(1, 7))).strftime(
            "%d/%m"
        )

        text = template.format(
            amount=f"₹{amount:,.0f}",
            half_amount=f"₹{half:,.0f}",
            partial_amount=f"₹{half:,.0f}",
            date=future_date,
        )

        # Map response_type string to enum
        type_map = {
            "paid": CustomerResponseType.PAID,
            "promise": CustomerResponseType.PROMISE_TO_PAY,
            "partial": CustomerResponseType.PARTIAL_PAYMENT,
            "ask_time": CustomerResponseType.ASKS_FOR_MORE_TIME,
            "no_response": CustomerResponseType.NO_RESPONSE,
            "dispute": CustomerResponseType.DISPUTES,
            "payment_failed": CustomerResponseType.PAYMENT_FAILED,
        }

        return (type_map.get(response_type, CustomerResponseType.NO_RESPONSE), text)
