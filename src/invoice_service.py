from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple


@dataclass
class LineItem:
    sku: str
    category: str
    unit_price: float
    qty: int
    fragile: bool = False


@dataclass
class Invoice:
    invoice_id: str
    customer_id: str
    country: str
    membership: str
    coupon: Optional[str]
    items: List[LineItem]


class InvoiceService:
    VALID_CATEGORIES = {"book", "food", "electronics", "other"}

    # Shipping rules: country -> list of (threshold, shipping_cost)
    # first matched threshold wins (sorted ascending)
    SHIPPING_RULES: Dict[str, List[Tuple[float, float]]] = {
        "TH": [(500, 60), (float("inf"), 0)],
        "JP": [(4000, 600), (float("inf"), 0)],
        "US": [(100, 15), (300, 8), (float("inf"), 0)],
        "DEFAULT": [(200, 25), (float("inf"), 0)],
    }

    # Tax rates by country
    TAX_RATES: Dict[str, float] = {"TH": 0.07, "JP": 0.10, "US": 0.08}
    DEFAULT_TAX_RATE: float = 0.05

    FRAGILE_FEE_PER_ITEM: float = 5.0

    def __init__(self) -> None:
        self._coupon_rate: Dict[str, float] = {
            "WELCOME10": 0.10,
            "VIP20": 0.20,
            "STUDENT5": 0.05,
        }

    def _validate(self, inv: Invoice) -> List[str]:
        problems: List[str] = []
        if inv is None:
            return ["Invoice is missing"]

        if not inv.invoice_id:
            problems.append("Missing invoice_id")
        if not inv.customer_id:
            problems.append("Missing customer_id")
        if not inv.items:
            problems.append("Invoice must contain items")

        for it in inv.items:
            problems.extend(self._validate_item(it))

        return problems

    def _validate_item(self, it: LineItem) -> List[str]:
        problems: List[str] = []
        if not it.sku:
            problems.append("Item sku is missing")
        if it.qty <= 0:
            problems.append(f"Invalid qty for {it.sku}")
        if it.unit_price < 0:
            problems.append(f"Invalid price for {it.sku}")
        if it.category not in self.VALID_CATEGORIES:
            problems.append(f"Unknown category for {it.sku}")
        return problems

    def compute_total(self, inv: Invoice) -> Tuple[float, List[str]]:
        warnings: List[str] = []
        problems = self._validate(inv)
        if problems:
            raise ValueError("; ".join(problems))

        subtotal, fragile_fee = self._compute_subtotal_and_fragile_fee(inv.items)
        shipping = self._compute_shipping(inv.country, subtotal)
        discount, coupon_warning = self._compute_discount(inv, subtotal)
        if coupon_warning:
            warnings.append(coupon_warning)

        tax = self._compute_tax(inv.country, subtotal, discount)
        total = max(0.0, subtotal + shipping + fragile_fee + tax - discount)

        warnings.extend(self._membership_warnings(inv.membership, subtotal))
        return total, warnings

    def _compute_subtotal_and_fragile_fee(self, items: List[LineItem]) -> Tuple[float, float]:
        subtotal = 0.0
        fragile_fee = 0.0
        for it in items:
            line_total = it.unit_price * it.qty
            subtotal += line_total
            if it.fragile:
                fragile_fee += self.FRAGILE_FEE_PER_ITEM * it.qty
        return subtotal, fragile_fee

    def _compute_shipping(self, country: str, subtotal: float) -> float:
        rules = self.SHIPPING_RULES.get(country, self.SHIPPING_RULES["DEFAULT"])
        for threshold, cost in rules:
            if subtotal < threshold:
                return cost
        return 0.0  # fallback (should never happen)

    def _compute_discount(self, inv: Invoice, subtotal: float) -> Tuple[float, Optional[str]]:
        discount = self._membership_discount(inv.membership, subtotal)
        coupon_discount, coupon_warning = self._coupon_discount(inv.coupon, subtotal)
        return discount + coupon_discount, coupon_warning

    def _membership_discount(self, membership: str, subtotal: float) -> float:
        if membership == "gold":
            return subtotal * 0.03
        if membership == "platinum":
            return subtotal * 0.05
        return 20.0 if subtotal > 3000 else 0.0

    def _coupon_discount(self, coupon: Optional[str], subtotal: float) -> Tuple[float, Optional[str]]:
        if coupon is None:
            return 0.0, None

        code = coupon.strip()
        if not code:
            return 0.0, None

        rate = self._coupon_rate.get(code)
        if rate is None:
            return 0.0, "Unknown coupon"

        return subtotal * rate, None

    def _compute_tax(self, country: str, taxable_base: float, discount: float) -> float:
        rate = self.TAX_RATES.get(country, self.DEFAULT_TAX_RATE)
        return (taxable_base - discount) * rate

    def _membership_warnings(self, membership: str, subtotal: float) -> List[str]:
        if subtotal > 10000 and membership not in ("gold", "platinum"):
            return ["Consider membership upgrade"]
        return []
