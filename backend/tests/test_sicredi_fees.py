"""Tests for the Sicredi fee vocabulary translation.

Regression guard for the carnê failure: the app sent ``tipoJuros: "PERCENTUAL_MES"``
(or ``"VALOR_DIA"``) straight to Sicredi, which only understands ``VALOR`` and
``PERCENTUAL``, so every boleto carrying juros was rejected with HTTP 400 before
being registered. Boletos with juros exempt omitted the field and went through —
which is why the bug only showed up once late-payment rules were filled in.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.sicredi.fees import (
    normalize_desconto,
    normalize_juros,
    normalize_multa,
)
from app.services.sicredi.schemas import CriarBoletoRequest, Pagador


# ---------------------------------------------------------------------------
# normalize_juros
# ---------------------------------------------------------------------------

def test_percentual_dia_converts_to_monthly_percentage():
    """A contract's "0,33% ao dia" is registered as 9,90% ao mês."""
    assert normalize_juros("PERCENTUAL_DIA", Decimal("0.33")) == (
        "PERCENTUAL",
        Decimal("9.90"),
    )


def test_percentual_mes_keeps_its_amount():
    assert normalize_juros("PERCENTUAL_MES", Decimal("9.9")) == (
        "PERCENTUAL",
        Decimal("9.90"),
    )


def test_valor_dia_maps_to_valor():
    assert normalize_juros("VALOR_DIA", Decimal("5")) == ("VALOR", Decimal("5.00"))


def test_wire_vocabulary_passes_through():
    """Older batch_operations.input_data rows may already hold wire values."""
    assert normalize_juros("PERCENTUAL", Decimal("2")) == ("PERCENTUAL", Decimal("2.00"))
    assert normalize_juros("VALOR", Decimal("2")) == ("VALOR", Decimal("2.00"))


@pytest.mark.parametrize("tipo", ["ISENTO", "isento", None, "", "   "])
def test_exempt_drops_both_type_and_amount(tipo):
    assert normalize_juros(tipo, Decimal("10")) == (None, None)


@pytest.mark.parametrize("valor", [None, Decimal("0")])
def test_type_without_amount_is_dropped_entirely(valor):
    """Sicredi rejects a fee type with no amount, so drop the pair."""
    assert normalize_juros("PERCENTUAL_DIA", valor) == (None, None)


def test_unknown_vocabulary_raises():
    with pytest.raises(ValueError, match="tipoJuros"):
        normalize_juros("PERCENTUAL_ANO", Decimal("1"))


def test_rounding_is_half_up_to_two_places():
    # 0.125 * 30 = 3.75 exactly; 0.3333 * 30 = 9.999 -> 10.00
    assert normalize_juros("PERCENTUAL_DIA", Decimal("0.125"))[1] == Decimal("3.75")
    assert normalize_juros("PERCENTUAL_DIA", Decimal("0.3333"))[1] == Decimal("10.00")


# ---------------------------------------------------------------------------
# normalize_multa / normalize_desconto
# ---------------------------------------------------------------------------

def test_multa_percentual_passes_through():
    assert normalize_multa("PERCENTUAL", Decimal("5")) == ("PERCENTUAL", Decimal("5.00"))


def test_multa_has_no_per_day_vocabulary():
    with pytest.raises(ValueError, match="tipoMulta"):
        normalize_multa("PERCENTUAL_MES", Decimal("5"))


def test_desconto_isento_is_dropped():
    assert normalize_desconto("ISENTO", Decimal("10")) == (None, None)


# ---------------------------------------------------------------------------
# CriarBoletoRequest — the choke point every caller goes through
# ---------------------------------------------------------------------------

def _pagador() -> Pagador:
    return Pagador(
        tipoPessoa="PESSOA_FISICA",
        documento="12345678901",
        nome="Rosinei",
        endereco="Rua Um, 10",
        cidade="Cidade",
        uf="SP",
        cep="12345678",
    )


def _request(**overrides) -> CriarBoletoRequest:
    payload = dict(
        codigoBeneficiario="12345",
        pagador=_pagador(),
        dataVencimento=date(2026, 10, 20),
        valor=Decimal("930.19"),
        seuNumero="BAT0001001",
    )
    payload.update(overrides)
    return CriarBoletoRequest(**payload)


def test_payload_never_contains_app_vocabulary():
    """The exact bug: PERCENTUAL_MES must not reach the wire."""
    payload = _request(
        tipoJuros="PERCENTUAL_DIA",
        juros=Decimal("0.33"),
        tipoMulta="PERCENTUAL",
        multa=Decimal("5"),
    ).to_api_payload()

    assert payload["tipoJuros"] == "PERCENTUAL"
    assert Decimal(str(payload["juros"])) == Decimal("9.90")
    assert payload["tipoMulta"] == "PERCENTUAL"
    assert "_" not in payload["tipoJuros"]
    assert "_" not in payload["tipoMulta"]


def test_exempt_juros_omits_both_fields():
    payload = _request(tipoJuros="ISENTO", juros=Decimal("0.33")).to_api_payload()
    assert "tipoJuros" not in payload
    assert "juros" not in payload


def test_amount_is_dropped_with_its_type():
    """Previously the amount was still sent when the type was filtered out."""
    payload = _request(tipoJuros=None, juros=Decimal("9.9")).to_api_payload()
    assert "juros" not in payload


def test_dropped_desconto_clears_values_and_dates():
    payload = _request(
        tipoDesconto="ISENTO",
        valorDesconto1=Decimal("10"),
        valorDesconto2=Decimal("5"),
        dataDesconto1=date(2026, 10, 19),
    ).to_api_payload()
    for field in (
        "tipoDesconto",
        "valorDesconto1",
        "valorDesconto2",
        "dataDesconto1",
    ):
        assert field not in payload


def test_unknown_type_fails_before_any_api_call():
    with pytest.raises(ValueError):
        _request(tipoJuros="PERCENTUAL_MENSAL", juros=Decimal("1"))
