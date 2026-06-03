
"""Pricing service: intelligent, bidirectional payment-plan computation.

Single source of truth for deriving a payment plan from the four values that
always exist for a contract: valor total, entrada, parcelas e valor mensal.

Rules (per business requirements):
  * total + entrada + parcelas  -> valor mensal = (total - entrada) / parcelas
  * total + entrada + mensal    -> parcelas     = round((total - entrada) / mensal)

All money math uses ``Decimal`` quantized to 2 decimals with ``ROUND_HALF_UP``.
Any rounding residue is absorbed by the LAST installment so the sum of all
installments equals the financed amount exactly (never over/under-charge).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Union

Number = Union[Decimal, int, float, str, None]

CENTS = Decimal("0.01")


def _to_decimal(value: Number) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass
class PaymentPlan:
    """Result of :func:`compute_plan`.

    All amounts are quantized to 2 decimals. ``installments`` parcelas are due,
    each worth ``monthly_value`` except the last one (``last_installment_value``)
    which absorbs the rounding residue.
    """

    total_value: Decimal
    down_payment: Decimal
    financed_value: Decimal
    installments: int
    monthly_value: Decimal
    last_installment_value: Decimal
    # Whether the last installment differs from the regular monthly value.
    has_residue: bool

    def as_dict(self) -> dict:
        return {
            "total_value": str(self.total_value),
            "down_payment": str(self.down_payment),
            "financed_value": str(self.financed_value),
            "installments": self.installments,
            "monthly_value": str(self.monthly_value),
            "last_installment_value": str(self.last_installment_value),
            "has_residue": self.has_residue,
        }


def compute_plan(
    total_value: Number,
    down_payment: Number = None,
    installments: Optional[int] = None,
    monthly_value: Number = None,
) -> PaymentPlan:
    """Derive a complete payment plan from whichever values were provided.

    Precedence: if ``installments`` is given (>0) it is authoritative and the
    monthly value is computed from it. Otherwise ``monthly_value`` is used to
    derive the number of installments.

    Raises ``ValueError`` for invalid/insufficient input so callers can return a
    clean 400 instead of producing a silently wrong contract.
    """
    total = _to_decimal(total_value)
    if total is None or total <= 0:
        raise ValueError("total_value deve ser maior que zero")

    down = _to_decimal(down_payment) or Decimal("0")
    if down < 0:
        raise ValueError("down_payment não pode ser negativo")
    if down > total:
        raise ValueError("entrada não pode ser maior que o valor total")

    financed = _money(total - down)
    monthly = _to_decimal(monthly_value)

    if installments is not None and installments > 0:
        n = int(installments)
        base = _money(financed / n)
    elif monthly is not None and monthly > 0:
        if monthly > financed:
            # Single installment covers the whole financed amount.
            n = 1
            base = financed
        else:
            n = int((financed / monthly).to_integral_value(rounding=ROUND_HALF_UP))
            n = max(1, n)
            base = _money(monthly)
    else:
        raise ValueError(
            "Informe o número de parcelas ou o valor mensal para calcular o plano"
        )

    if financed == 0:
        # Fully paid via down payment; no financing.
        return PaymentPlan(
            total_value=_money(total),
            down_payment=_money(down),
            financed_value=Decimal("0.00"),
            installments=0,
            monthly_value=Decimal("0.00"),
            last_installment_value=Decimal("0.00"),
            has_residue=False,
        )

    # Last installment absorbs the residue so the sum equals financed exactly.
    last = _money(financed - base * (n - 1))
    has_residue = last != base

    return PaymentPlan(
        total_value=_money(total),
        down_payment=_money(down),
        financed_value=financed,
        installments=n,
        monthly_value=base,
        last_installment_value=last,
        has_residue=has_residue,
    )
