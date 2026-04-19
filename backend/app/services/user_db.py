"""User database service (in-memory storage)."""
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from app.models.schemas import CartItem, OrderStatus, UserPreferences


class UserDBService:
    """In-memory user data store for carts, orders, and preferences.

    NOTE: Checkout orders and processed Stripe events live here in-memory.
    On a restart the state is lost — migrate to a real DB before handling
    live payments.
    """

    def __init__(self):
        self.carts: Dict[str, List[CartItem]] = {}
        self.preferences: Dict[str, UserPreferences] = {}
        self.orders: Dict[str, OrderStatus] = self._create_mock_orders()
        self.checkout_orders: Dict[str, Dict[str, Any]] = {}
        self.processed_stripe_events: Dict[str, float] = {}

    def _create_mock_orders(self) -> Dict[str, OrderStatus]:
        now = datetime.now()
        return {
            "ORD-2024-001": OrderStatus(
                order_id="ORD-2024-001",
                status="In Transit",
                shipped_at=(now - timedelta(days=2)).isoformat(),
                estimated_delivery=(now + timedelta(days=3)).isoformat(),
                current_location="Distribution Center - Los Angeles",
                tracking_url="https://tracking.example.com/ORD-2024-001",
            ),
            "ORD-2024-002": OrderStatus(
                order_id="ORD-2024-002",
                status="Delivered",
                shipped_at=(now - timedelta(days=5)).isoformat(),
                estimated_delivery=(now - timedelta(days=1)).isoformat(),
                current_location="Delivered",
                tracking_url="https://tracking.example.com/ORD-2024-002",
            ),
        }

    async def add_to_cart(self, user_id: str, item: CartItem) -> List[CartItem]:
        if user_id not in self.carts:
            self.carts[user_id] = []

        existing = next(
            (ci for ci in self.carts[user_id]
             if ci.product_id == item.product_id and ci.variant_id == item.variant_id),
            None,
        )
        if existing:
            existing.quantity += item.quantity
            if item.selected_size:
                existing.selected_size = item.selected_size
            if item.selected_color:
                existing.selected_color = item.selected_color
        else:
            self.carts[user_id].append(item)

        return self.carts[user_id]

    async def get_cart(self, user_id: str) -> List[CartItem]:
        return self.carts.get(user_id, [])

    async def remove_from_cart(self, user_id: str, product_id: str):
        if user_id in self.carts:
            self.carts[user_id] = [
                ci for ci in self.carts[user_id] if ci.product_id != product_id
            ]

    async def update_cart_quantity(self, user_id: str, product_id: str, quantity: int):
        if user_id not in self.carts:
            return
        if quantity <= 0:
            await self.remove_from_cart(user_id, product_id)
            return
        for ci in self.carts[user_id]:
            if ci.product_id == product_id:
                ci.quantity = quantity
                break

    async def clear_cart(self, user_id: str):
        if user_id in self.carts:
            self.carts[user_id] = []

    async def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        return self.orders.get(order_id)

    async def get_preferences(self, user_id: str) -> UserPreferences:
        if user_id not in self.preferences:
            self.preferences[user_id] = UserPreferences(
                brands=["Nike", "Clarks", "Apple"],
                sizes=["8", "M", "L"],
                styles=["casual", "comfortable", "modern"],
                price_range={"min": 0, "max": 500},
            )
        return self.preferences[user_id]

    async def update_preferences(self, user_id: str, preferences: UserPreferences):
        self.preferences[user_id] = preferences

    # ── Checkout orders (Stripe) ───────────────────────────────────

    async def create_checkout_order(
        self, order_id: str, user_id: str, data: Dict[str, Any]
    ) -> None:
        """Persist a frozen order snapshot before calling Stripe. Fulfillment
        in the webhook reads from here, not from the live cart (which the
        user may mutate between redirect and payment settlement)."""
        self.checkout_orders[order_id] = {
            "order_id": order_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            **data,
        }

    async def get_checkout_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self.checkout_orders.get(order_id)

    async def update_checkout_order(
        self, order_id: str, status: str, **extra: Any
    ) -> Optional[Dict[str, Any]]:
        order = self.checkout_orders.get(order_id)
        if not order:
            return None
        order["status"] = status
        order["updated_at"] = datetime.now().isoformat()
        order.update(extra)
        return order

    async def mark_checkout_paid_if_pending(
        self, order_id: str, **extra: Any
    ) -> bool:
        """Atomic-in-asyncio (no await between check and set) guard that
        returns True only for the first caller that transitions the order
        out of the pending/awaiting_payment state."""
        order = self.checkout_orders.get(order_id)
        if not order:
            return False
        if order["status"] == "paid":
            return False
        order["status"] = "paid"
        order["updated_at"] = datetime.now().isoformat()
        order.update(extra)
        return True

    # ── Stripe webhook idempotency ─────────────────────────────────

    def is_stripe_event_processed(self, event_id: str) -> bool:
        self._sweep_stripe_events()
        return event_id in self.processed_stripe_events

    def mark_stripe_event_processed(self, event_id: str) -> None:
        self.processed_stripe_events[event_id] = time.time()

    def _sweep_stripe_events(self) -> None:
        if len(self.processed_stripe_events) <= 5000:
            return
        cutoff = time.time() - 86400  # 24h
        self.processed_stripe_events = {
            eid: ts for eid, ts in self.processed_stripe_events.items() if ts > cutoff
        }
