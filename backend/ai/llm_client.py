"""
Real LLM implementations for recovery diagnosis and action proposals.
Supports Gemini and Claude APIs with structured output validation.
"""

import os
import json
from typing import Optional, Dict, Any

from ai.provider import (
    AIProvider,
    DiagnosisOutput,
    ActionProposal,
    PromiseExtraction,
)
from config.constants import ActionType


class GeminiProvider(AIProvider):
    """Google Gemini API provider"""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set. "
                "Use AI_PROVIDER=mock for development."
            )
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
        except ImportError:
            raise ImportError(
                "google-generativeai not installed. "
                "Install with: pip install google-generativeai"
            )

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
        """Diagnose using Gemini API"""
        prompt = f"""Analyze this B2B payment situation and provide diagnosis.

Customer: {customer_name}
Invoice Amount: ₹{invoice_amount:,.0f}
Days Overdue: {days_overdue}
Reliability Score: {reliability_score:.2f} (0=unreliable, 1=very reliable)
Payment History: {payment_history}
Delay Reason (if provided): {delay_reason or 'Not specified'}
Dispute Status: {dispute_status}
Escalation Stage: {escalation_stage}/4

Respond ONLY with valid JSON (no other text):
{{
    "root_cause": "Brief root cause (e.g., cash-flow issue, dispute, payment method problem)",
    "confidence": 0.0-1.0,
    "context": "Additional context"
}}"""

        try:
            response = self.client.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                },
            )
            data = json.loads(response.text)
            return DiagnosisOutput(
                root_cause=data.get("root_cause", "Unknown cause"),
                confidence=float(data.get("confidence", 0.5)),
                context=data.get("context", ""),
            )
        except Exception as e:
            # Fallback to deterministic diagnosis on LLM error
            from ai.mock_llm import MockLLM

            return MockLLM().diagnose(
                invoice_amount=invoice_amount,
                days_overdue=days_overdue,
                customer_name=customer_name,
                reliability_score=reliability_score,
                payment_history=payment_history,
                delay_reason=delay_reason,
                dispute_status=dispute_status,
                escalation_stage=escalation_stage,
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
        """Propose action using Gemini API"""
        allowed_actions = [a.value for a in ActionType]

        prompt = f"""Based on this recovery situation, recommend ONE action.

Diagnosis: {diagnosis.root_cause}
Customer: {customer_name}
Invoice Amount: ₹{invoice_amount:,.0f}
Days Overdue: {days_overdue}
Reliability Score: {reliability_score:.2f}
Escalation Stage: {escalation_stage}/4
Previous Attempts: {previous_attempts}

Allowed actions only: {', '.join(allowed_actions)}

Respond ONLY with valid JSON (no other text):
{{
    "proposed_action": "One of the allowed actions",
    "reasoning": "Why this action",
    "confidence": 0.0-1.0
}}"""

        try:
            response = self.client.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                },
            )
            data = json.loads(response.text)
            proposed = data.get("proposed_action", ActionType.STOP.value)

            # Validate action is allowed
            if proposed not in allowed_actions:
                proposed = ActionType.STOP.value

            return ActionProposal(
                proposed_action=proposed,
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as e:
            # Fallback to deterministic action proposal on LLM error
            from ai.mock_llm import MockLLM

            return MockLLM().propose_action(
                diagnosis=diagnosis,
                invoice_amount=invoice_amount,
                days_overdue=days_overdue,
                customer_name=customer_name,
                reliability_score=reliability_score,
                escalation_stage=escalation_stage,
                previous_attempts=previous_attempts,
            )

    def extract_promise(
        self,
        customer_response: str,
        invoice_amount: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> PromiseExtraction:
        """Extract promise using Gemini API"""
        prompt = f"""Extract promise-to-pay details from customer response.

Customer Response: "{customer_response}"
Invoice Amount: ₹{invoice_amount:,.0f}

If no promise is evident, set confidence to 0.0.
Respond ONLY with valid JSON (no other text):
{{
    "promised_amount": 0.0,
    "promised_date": "YYYY-MM-DD or null",
    "confidence": 0.0-1.0,
    "extracted_text": "Relevant excerpt if found"
}}"""

        try:
            response = self.client.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                },
            )
            data = json.loads(response.text)
            return PromiseExtraction(
                promised_amount=float(data.get("promised_amount", invoice_amount / 2)),
                promised_date=data.get("promised_date", None),
                confidence=float(data.get("confidence", 0.0)),
                extracted_text=data.get("extracted_text", None),
            )
        except Exception as e:
            # Fallback to deterministic promise extraction on LLM error
            from ai.mock_llm import MockLLM

            return MockLLM().extract_promise(
                customer_response=customer_response,
                invoice_amount=invoice_amount,
                context=context,
            )


class ClaudeProvider(AIProvider):
    """Anthropic Claude API provider"""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Use AI_PROVIDER=mock for development."
            )
        self.model = "claude-3-5-sonnet-20241022"
        try:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError(
                "anthropic not installed. Install with: pip install anthropic"
            )

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
        """Diagnose using Claude API"""
        prompt = f"""Analyze this B2B payment situation and provide diagnosis.

Customer: {customer_name}
Invoice Amount: ₹{invoice_amount:,.0f}
Days Overdue: {days_overdue}
Reliability Score: {reliability_score:.2f} (0=unreliable, 1=very reliable)
Payment History: {payment_history}
Delay Reason (if provided): {delay_reason or 'Not specified'}
Dispute Status: {dispute_status}
Escalation Stage: {escalation_stage}/4

Respond ONLY with valid JSON (no other text):
{{
    "root_cause": "Brief root cause",
    "confidence": 0.0-1.0,
    "context": "Additional context"
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(message.content[0].text)
            return DiagnosisOutput(
                root_cause=data.get("root_cause", "Unknown cause"),
                confidence=float(data.get("confidence", 0.5)),
                context=data.get("context", ""),
            )
        except Exception as e:
            from ai.mock_llm import MockLLM

            return MockLLM().diagnose(
                invoice_amount=invoice_amount,
                days_overdue=days_overdue,
                customer_name=customer_name,
                reliability_score=reliability_score,
                payment_history=payment_history,
                delay_reason=delay_reason,
                dispute_status=dispute_status,
                escalation_stage=escalation_stage,
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
        """Propose action using Claude API"""
        allowed_actions = [a.value for a in ActionType]

        prompt = f"""Based on this recovery situation, recommend ONE action.

Diagnosis: {diagnosis.root_cause}
Customer: {customer_name}
Invoice Amount: ₹{invoice_amount:,.0f}
Days Overdue: {days_overdue}
Reliability Score: {reliability_score:.2f}
Escalation Stage: {escalation_stage}/4
Previous Attempts: {previous_attempts}

Allowed actions only: {', '.join(allowed_actions)}

Respond ONLY with valid JSON (no other text):
{{
    "proposed_action": "One of the allowed actions",
    "reasoning": "Why this action",
    "confidence": 0.0-1.0
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(message.content[0].text)
            proposed = data.get("proposed_action", ActionType.STOP.value)

            if proposed not in allowed_actions:
                proposed = ActionType.STOP.value

            return ActionProposal(
                proposed_action=proposed,
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as e:
            from ai.mock_llm import MockLLM

            return MockLLM().propose_action(
                diagnosis=diagnosis,
                invoice_amount=invoice_amount,
                days_overdue=days_overdue,
                customer_name=customer_name,
                reliability_score=reliability_score,
                escalation_stage=escalation_stage,
                previous_attempts=previous_attempts,
            )

    def extract_promise(
        self,
        customer_response: str,
        invoice_amount: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> PromiseExtraction:
        """Extract promise using Claude API"""
        prompt = f"""Extract promise-to-pay details from customer response.

Customer Response: "{customer_response}"
Invoice Amount: ₹{invoice_amount:,.0f}

If no promise is evident, set confidence to 0.0.
Respond ONLY with valid JSON (no other text):
{{
    "promised_amount": 0.0,
    "promised_date": "YYYY-MM-DD or null",
    "confidence": 0.0-1.0,
    "extracted_text": "Relevant excerpt if found"
}}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(message.content[0].text)
            return PromiseExtraction(
                promised_amount=float(data.get("promised_amount", invoice_amount / 2)),
                promised_date=data.get("promised_date", None),
                confidence=float(data.get("confidence", 0.0)),
                extracted_text=data.get("extracted_text", None),
            )
        except Exception as e:
            from ai.mock_llm import MockLLM

            return MockLLM().extract_promise(
                customer_response=customer_response,
                invoice_amount=invoice_amount,
                context=context,
            )
