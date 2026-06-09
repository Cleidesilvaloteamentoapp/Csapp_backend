"""CPF/CNPJ validation helpers (Brazilian taxpayer documents)."""

import re


def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def is_valid_cpf(cpf: str) -> bool:
    """Validate a CPF using its two check digits."""
    cpf = _only_digits(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for length in (9, 10):
        total = sum(int(cpf[i]) * ((length + 1) - i) for i in range(length))
        check = (total * 10) % 11
        check = 0 if check == 10 else check
        if check != int(cpf[length]):
            return False
    return True


def is_valid_cnpj(cnpj: str) -> bool:
    """Validate a CNPJ using its two check digits."""
    cnpj = _only_digits(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6] + weights_first
    for weights, pos in ((weights_first, 12), (weights_second, 13)):
        total = sum(int(cnpj[i]) * weights[i] for i in range(pos))
        rem = total % 11
        check = 0 if rem < 2 else 11 - rem
        if check != int(cnpj[pos]):
            return False
    return True


def is_valid_cpf_cnpj(documento: str) -> bool:
    """Validate a document as either a CPF (11 digits) or CNPJ (14 digits)."""
    digits = _only_digits(documento)
    if len(digits) == 11:
        return is_valid_cpf(digits)
    if len(digits) == 14:
        return is_valid_cnpj(digits)
    return False
