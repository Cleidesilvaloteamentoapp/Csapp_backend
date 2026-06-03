"""Unit tests for pricing_service.compute_plan (pure, no DB)."""

from decimal import Decimal

import pytest

from app.services.pricing_service import compute_plan


def test_installments_given_derives_monthly():
    plan = compute_plan(total_value=200000, down_payment=50000, installments=180)
    assert plan.financed_value == Decimal("150000.00")
    assert plan.installments == 180
    assert plan.monthly_value == Decimal("833.33")
    # Sum of all installments must equal the financed value exactly.
    total = plan.monthly_value * (plan.installments - 1) + plan.last_installment_value
    assert total == plan.financed_value
    assert plan.has_residue is True  # 833.33 * 180 != 150000


def test_monthly_given_derives_installments():
    plan = compute_plan(total_value=120000, down_payment=0, monthly_value=1000)
    assert plan.financed_value == Decimal("120000.00")
    assert plan.installments == 120
    assert plan.monthly_value == Decimal("1000.00")
    assert plan.last_installment_value == Decimal("1000.00")
    assert plan.has_residue is False


def test_monthly_with_residue_on_last():
    # 100000 / 999 -> 100.10 (rounded), residue lands on last installment.
    plan = compute_plan(total_value=100000, monthly_value=333.33)
    total = plan.monthly_value * (plan.installments - 1) + plan.last_installment_value
    assert total == plan.financed_value


def test_exact_division_no_residue():
    plan = compute_plan(total_value=12000, installments=12)
    assert plan.monthly_value == Decimal("1000.00")
    assert plan.last_installment_value == Decimal("1000.00")
    assert plan.has_residue is False


def test_down_payment_equal_total_is_fully_paid():
    plan = compute_plan(total_value=50000, down_payment=50000, installments=12)
    assert plan.financed_value == Decimal("0.00")
    assert plan.installments == 0
    assert plan.monthly_value == Decimal("0.00")


def test_monthly_greater_than_financed_single_installment():
    plan = compute_plan(total_value=10000, down_payment=2000, monthly_value=20000)
    assert plan.installments == 1
    assert plan.monthly_value == Decimal("8000.00")
    assert plan.last_installment_value == Decimal("8000.00")


def test_requires_installments_or_monthly():
    with pytest.raises(ValueError):
        compute_plan(total_value=10000)


def test_rejects_down_payment_above_total():
    with pytest.raises(ValueError):
        compute_plan(total_value=10000, down_payment=20000, installments=10)


def test_rejects_nonpositive_total():
    with pytest.raises(ValueError):
        compute_plan(total_value=0, installments=10)
