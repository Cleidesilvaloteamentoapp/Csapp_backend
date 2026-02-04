import re
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


def validate_cpf(cpf: str) -> bool:
    """Validate Brazilian CPF number"""
    cpf = re.sub(r'[^0-9]', '', cpf)
    
    if len(cpf) != 11:
        return False
    
    if cpf == cpf[0] * 11:
        return False
    
    def calc_digit(cpf_slice: str, weights: list) -> int:
        total = sum(int(d) * w for d, w in zip(cpf_slice, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    first_weights = [10, 9, 8, 7, 6, 5, 4, 3, 2]
    second_weights = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    
    first_digit = calc_digit(cpf[:9], first_weights)
    second_digit = calc_digit(cpf[:10], second_weights)
    
    return cpf[-2:] == f"{first_digit}{second_digit}"


def validate_cnpj(cnpj: str) -> bool:
    """Validate Brazilian CNPJ number"""
    cnpj = re.sub(r'[^0-9]', '', cnpj)
    
    if len(cnpj) != 14:
        return False
    
    if cnpj == cnpj[0] * 14:
        return False
    
    def calc_digit(cnpj_slice: str, weights: list) -> int:
        total = sum(int(d) * w for d, w in zip(cnpj_slice, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    first_weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    second_weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    
    first_digit = calc_digit(cnpj[:12], first_weights)
    second_digit = calc_digit(cnpj[:13], second_weights)
    
    return cnpj[-2:] == f"{first_digit}{second_digit}"


def validate_cpf_cnpj(document: str) -> bool:
    """Validate either CPF or CNPJ"""
    clean = re.sub(r'[^0-9]', '', document)
    
    if len(clean) == 11:
        return validate_cpf(document)
    elif len(clean) == 14:
        return validate_cnpj(document)
    
    return False


def format_cpf(cpf: str) -> str:
    """Format CPF as XXX.XXX.XXX-XX"""
    cpf = re.sub(r'[^0-9]', '', cpf)
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def format_cnpj(cnpj: str) -> str:
    """Format CNPJ as XX.XXX.XXX/XXXX-XX"""
    cnpj = re.sub(r'[^0-9]', '', cnpj)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def format_phone(phone: str) -> str:
    """Format phone as (XX) XXXXX-XXXX or (XX) XXXX-XXXX"""
    phone = re.sub(r'[^0-9]', '', phone)
    
    if len(phone) == 11:
        return f"({phone[:2]}) {phone[2:7]}-{phone[7:]}"
    elif len(phone) == 10:
        return f"({phone[:2]}) {phone[2:6]}-{phone[6:]}"
    
    return phone


def format_currency(value: Decimal) -> str:
    """Format value as Brazilian currency"""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calculate_installments(
    total: Decimal,
    num_installments: int,
    first_due_date: date
) -> list:
    """Calculate payment installments with dates"""
    from dateutil.relativedelta import relativedelta
    
    installment_value = total / num_installments
    installments = []
    
    for i in range(num_installments):
        due_date = first_due_date + relativedelta(months=i)
        installments.append({
            "number": i + 1,
            "value": float(installment_value),
            "due_date": due_date.isoformat()
        })
    
    return installments


def days_overdue(due_date: date) -> int:
    """Calculate days overdue from due date"""
    today = date.today()
    if due_date >= today:
        return 0
    return (today - due_date).days


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for storage"""
    name = re.sub(r'[^\w\s\-\.]', '', filename)
    name = re.sub(r'\s+', '_', name)
    return name.lower()
