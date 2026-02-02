"""
Payment processing service - Stripe Terminal integration
Handles card reader communication and payment processing
"""

import stripe
from typing import Tuple, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from event_store import Money
from api.config import get_settings

settings = get_settings()

# Only set Stripe API key if configured (runtime env var, not build-time)
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentService:
    """
    Stripe Terminal payment processing
    Handles auth → capture flow for card-present transactions
    """

    def __init__(self):
        self.stripe = stripe

    def create_payment_intent(
        self,
        amount: Money,
        description: str = "POS Transaction"
    ) -> str:
        """
        Create a payment intent for terminal processing

        Args:
            amount: Amount to charge
            description: Transaction description

        Returns:
            payment_intent_id
        """
        intent = stripe.PaymentIntent.create(
            amount=amount.amount_minor,
            currency=amount.currency.lower(),
            payment_method_types=["card_present"],
            capture_method="manual",  # Auth first, capture later
            description=description,
        )
        return intent.id

    def process_payment_on_reader(
        self,
        reader_id: str,
        payment_intent_id: str
    ) -> dict:
        """
        Process payment on a specific reader

        Args:
            reader_id: Stripe Terminal reader ID
            payment_intent_id: Payment intent to process

        Returns:
            Payment intent result
        """
        try:
            # Process payment on reader
            result = stripe.terminal.Reader.process_payment_intent(
                reader_id,
                payment_intent=payment_intent_id,
            )
            return result
        except stripe.error.StripeError as e:
            raise Exception(f"Card reader error: {str(e)}")

    def capture_payment(
        self,
        payment_intent_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Capture (settle) an authorized payment

        Args:
            payment_intent_id: Payment intent to capture

        Returns:
            (success, card_last_four)
        """
        try:
            intent = stripe.PaymentIntent.capture(payment_intent_id)

            # Extract card details if available
            card_last_four = None
            if intent.charges and intent.charges.data:
                charge = intent.charges.data[0]
                if hasattr(charge, 'payment_method_details'):
                    card_present = charge.payment_method_details.card_present
                    if card_present and hasattr(card_present, 'last4'):
                        card_last_four = card_present.last4

            return (True, card_last_four)

        except stripe.error.StripeError as e:
            raise Exception(f"Payment capture failed: {str(e)}")

    def cancel_payment_intent(self, payment_intent_id: str):
        """Cancel a payment intent"""
        try:
            stripe.PaymentIntent.cancel(payment_intent_id)
        except stripe.error.StripeError as e:
            raise Exception(f"Cancel failed: {str(e)}")

    def list_readers(self, limit: int = 10) -> list:
        """
        List available card readers

        Args:
            limit: Max number of readers to return

        Returns:
            List of reader objects
        """
        try:
            readers = stripe.terminal.Reader.list(limit=limit)
            return [
                {
                    "id": reader.id,
                    "label": reader.label,
                    "serial_number": reader.serial_number,
                    "status": reader.status,
                    "device_type": reader.device_type,
                }
                for reader in readers.data
            ]
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to list readers: {str(e)}")

    def get_reader_status(self, reader_id: str) -> dict:
        """Get current status of a reader"""
        try:
            reader = stripe.terminal.Reader.retrieve(reader_id)
            return {
                "id": reader.id,
                "label": reader.label,
                "status": reader.status,
                "device_type": reader.device_type,
            }
        except stripe.error.StripeError as e:
            raise Exception(f"Failed to get reader status: {str(e)}")

    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[Money] = None
    ) -> str:
        """
        Create a refund for a payment

        Args:
            payment_intent_id: Original payment intent
            amount: Amount to refund (None for full refund)

        Returns:
            refund_id
        """
        try:
            # Get the charge from payment intent
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            if not intent.charges or not intent.charges.data:
                raise Exception("No charge found for this payment")

            charge_id = intent.charges.data[0].id

            # Create refund
            refund_params = {"charge": charge_id}
            if amount:
                refund_params["amount"] = amount.amount_minor

            refund = stripe.Refund.create(**refund_params)
            return refund.id

        except stripe.error.StripeError as e:
            raise Exception(f"Refund failed: {str(e)}")

    def process_cash_payment(
        self,
        amount: Money,
        description: str = "Cash Payment"
    ) -> str:
        """
        Record a cash payment (no actual processing needed)

        Args:
            amount: Cash amount received
            description: Transaction description

        Returns:
            Mock payment_id for tracking
        """
        # For cash, we don't actually process through Stripe
        # Just return a tracking ID for our records
        import uuid
        return f"cash_{uuid.uuid4().hex[:16]}"

    def simulate_card_present_payment(
        self,
        amount: Money,
        description: str = "Test Payment"
    ) -> Tuple[str, str]:
        """
        Simulate a card present payment for testing (without physical reader)

        Args:
            amount: Amount to charge
            description: Transaction description

        Returns:
            (payment_intent_id, simulated_card_last_four)
        """
        # Create payment intent with test mode
        intent = stripe.PaymentIntent.create(
            amount=amount.amount_minor,
            currency=amount.currency.lower(),
            payment_method_types=["card_present"],
            capture_method="manual",
            description=description,
        )

        # In test mode, we can't actually process on reader
        # So we simulate by creating a test payment method and confirming
        try:
            # Create test payment method
            pm = stripe.PaymentMethod.create(
                type="card",
                card={
                    "token": "tok_visa",  # Test token
                },
            )

            # Attach and confirm (simulates card tap)
            confirmed = stripe.PaymentIntent.confirm(
                intent.id,
                payment_method=pm.id,
            )

            # Capture immediately
            captured = stripe.PaymentIntent.capture(confirmed.id)

            return (captured.id, "4242")  # Test card last 4

        except Exception as e:
            # If simulation fails, just return intent ID
            return (intent.id, "0000")
