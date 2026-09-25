"""Coerce a query-string value into an enum member.

Comparing an enum column directly against a raw query string is a 500 waiting
to happen: Postgres rejects the value with
``invalid input value for enum invoice_status: "pending"`` and the whole request
dies. That is exactly what made every filter on the Financeiro screen fail,
since the screen sends its values lower-cased.
"""

from enum import Enum
from typing import Optional, Type, TypeVar

from fastapi import HTTPException, status

E = TypeVar("E", bound=Enum)


def parse_enum_filter(
    enum_cls: Type[E],
    value: Optional[str],
    *,
    field: str = "status",
    treat_all_as_none: bool = True,
) -> Optional[E]:
    """Return the enum member for *value*, or None when there is no filter.

    Accepts any casing. An unknown value is a 400 naming the valid options --
    a client error, reported as one, instead of a database crash.
    """
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned or (treat_all_as_none and cleaned.lower() == "all"):
        return None

    try:
        return enum_cls(cleaned.upper())
    except ValueError:
        valid = ", ".join(m.value for m in enum_cls)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} inválido: '{value}'. Valores aceitos: {valid}.",
        ) from None
