"""
Razorpay Test Mode Client for Vasooli Revenue Recovery.

Strictly operates in TEST MODE using Razorpay test credentials.
Never hardcodes credentials and never exposes or logs API secrets.
Falls back gracefully if credentials are not configured or calls fail.
"""

import os
from typing import Optional, Dict, Any


class RazorpayTestClient:
    """
    Isolated Razorpay client designed strictly for Test Mode revenue recovery.
    """

    PLACEHOLDERS = {
        "your_test_key_id",
        "your_test_key_secret",
        "your_key_id",
        "your_key_secret",
        "rzp_test_placeholder",
    }

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
    ):
        if key_id is None or key_secret is None:
            from pathlib import Path
            from dotenv import load_dotenv

            env_file = Path(__file__).parent.parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)

        raw_key_id = key_id if key_id is not None else os.getenv("RAZORPAY_KEY_ID", "")
        raw_key_secret = (
            key_secret if key_secret is not None else os.getenv("RAZORPAY_KEY_SECRET", "")
        )
        self.key_id: str = raw_key_id.strip() if raw_key_id else ""
        self._key_secret: str = raw_key_secret.strip() if raw_key_secret else ""
        self._client = None
        self._init_client()

    def is_configured(self) -> bool:
        """
        Check if valid non-placeholder test credentials are configured.
        Returns False if credentials are missing or default placeholders.
        """
        if not self.key_id or not self._key_secret:
            return False
        if (
            self.key_id.lower() in self.PLACEHOLDERS
            or self._key_secret.lower() in self.PLACEHOLDERS
        ):
            return False
        return True

    def _init_client(self):
        """Initialize official Razorpay Client if credentials and SDK are available."""
        if not self.is_configured():
            return
        try:
            import razorpay

            self._client = razorpay.Client(auth=(self.key_id, self._key_secret))
        except ImportError:
            self._client = None

    def get_public_info(self) -> Dict[str, Any]:
        """Return non-sensitive client configuration status."""
        masked_id = (
            f"{self.key_id[:8]}..."
            if len(self.key_id) > 8
            else ("configured" if self.key_id else "none")
        )
        return {
            "provider": "razorpay_test",
            "is_configured": self.is_configured(),
            "key_id_preview": masked_id,
            "mode": "test",
        }

    def create_payment_retry(
        self,
        invoice_id: str,
        amount: float,
        customer_id: str,
        customer_name: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a bounded payment retry order in Razorpay Test Mode.

        Args:
            invoice_id: Identifier of the invoice to recover
            amount: Recovery amount in INR
            customer_id: Customer ID
            customer_name: Optional customer name
            notes: Optional contextual metadata

        Returns:
            Dict indicating outcome with provider="razorpay_test"
        """
        if not self.is_configured():
            return {
                "success": False,
                "provider": "razorpay_test",
                "transaction_id": None,
                "status": "unconfigured",
                "error": "Razorpay test credentials not configured or placeholder",
            }

        if self._client is None:
            return {
                "success": False,
                "provider": "razorpay_test",
                "transaction_id": None,
                "status": "client_unavailable",
                "error": "Razorpay SDK client unavailable",
            }

        try:
            # Razorpay amounts are represented in integer paise (1 INR = 100 paise)
            amount_in_paise = max(100, int(round(amount * 100)))

            order_notes = {
                "invoice_id": str(invoice_id),
                "customer_id": str(customer_id),
                "channel": "vasooli_recovery_retry",
                "mode": "test",
            }
            if customer_name:
                order_notes["customer_name"] = str(customer_name)[:50]
            if notes:
                order_notes.update({str(k): str(v)[:50] for k, v in notes.items()})

            # Razorpay receipts must be <= 40 chars
            receipt = f"rec_{str(invoice_id).replace('-', '')}"[:40]

            order_payload = {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": order_notes,
                "payment_capture": 1,
            }

            rzp_order = self._client.order.create(data=order_payload)
            order_id = rzp_order.get("id")
            order_status = rzp_order.get("status", "created")

            return {
                "success": True,
                "provider": "razorpay_test",
                "transaction_id": order_id,
                "status": order_status,
                "amount": amount,
                "currency": "INR",
                "receipt": receipt,
                "created_at": rzp_order.get("created_at"),
            }

        except Exception as e:
            error_msg = str(e)
            # Guarantee secret is never in the error message
            if self._key_secret and self._key_secret in error_msg:
                error_msg = error_msg.replace(self._key_secret, "[REDACTED]")

            return {
                "success": False,
                "provider": "razorpay_test",
                "transaction_id": None,
                "status": "failed",
                "error": error_msg,
            }
