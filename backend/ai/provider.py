"""
Abstract AI provider for recovery diagnosis and action proposals.
Supports multiple LLM backends and mock mode for testing.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel
import os
import json


class DiagnosisOutput(BaseModel):
    """Structured diagnosis output from AI"""
    root_cause: str
    confidence: float
    context: str


class ActionProposal(BaseModel):
    """Structured action proposal from AI"""
    proposed_action: str
    reasoning: str
    confidence: float


class PromiseExtraction(BaseModel):
    """Structured promise extraction from customer response"""
    promised_amount: float
    promised_date: str  # YYYY-MM-DD
    confidence: float
    extracted_text: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers"""

    @abstractmethod
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
        """Diagnose root cause of non-payment"""
        pass

    @abstractmethod
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
        """Propose recovery action based on diagnosis"""
        pass

    @abstractmethod
    def extract_promise(
        self,
        customer_response: str,
        invoice_amount: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> PromiseExtraction:
        """Extract promise details from customer response"""
        pass


class AIProviderFactory:
    """Factory to create AI provider instances"""

    _provider_instance: Optional[AIProvider] = None

    @staticmethod
    def get_provider() -> AIProvider:
        """Get singleton AI provider instance"""
        if AIProviderFactory._provider_instance is None:
            provider_type = os.getenv("AI_PROVIDER", "mock").lower()
            
            if provider_type == "mock":
                from ai.mock_llm import MockLLM
                AIProviderFactory._provider_instance = MockLLM()
            elif provider_type == "gemini":
                try:
                    from ai.llm_client import GeminiProvider
                    AIProviderFactory._provider_instance = GeminiProvider()
                except Exception as e:
                    print(f"Warning: Failed to initialize GeminiProvider ({e}). Falling back to MockLLM.")
                    from ai.mock_llm import MockLLM
                    AIProviderFactory._provider_instance = MockLLM()
            elif provider_type == "claude":
                try:
                    from ai.llm_client import ClaudeProvider
                    AIProviderFactory._provider_instance = ClaudeProvider()
                except Exception as e:
                    print(f"Warning: Failed to initialize ClaudeProvider ({e}). Falling back to MockLLM.")
                    from ai.mock_llm import MockLLM
                    AIProviderFactory._provider_instance = MockLLM()
            else:
                from ai.mock_llm import MockLLM
                AIProviderFactory._provider_instance = MockLLM()
        
        return AIProviderFactory._provider_instance

    @staticmethod
    def reset_provider():
        """Reset provider instance (useful for testing)"""
        AIProviderFactory._provider_instance = None
