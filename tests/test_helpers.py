import pytest
from decimal import Decimal
from datetime import date

from app.utils.helpers import (
    validate_cpf,
    validate_cnpj,
    validate_cpf_cnpj,
    format_cpf,
    format_cnpj,
    format_phone,
    format_currency,
    days_overdue,
    sanitize_filename
)


class TestCPFValidation:
    """Test CPF validation"""
    
    def test_valid_cpf(self):
        """Test valid CPF numbers"""
        assert validate_cpf("529.982.247-25") == True
        assert validate_cpf("52998224725") == True
    
    def test_invalid_cpf_wrong_digits(self):
        """Test CPF with wrong check digits"""
        assert validate_cpf("529.982.247-00") == False
    
    def test_invalid_cpf_same_digits(self):
        """Test CPF with all same digits"""
        assert validate_cpf("111.111.111-11") == False
        assert validate_cpf("000.000.000-00") == False
    
    def test_invalid_cpf_wrong_length(self):
        """Test CPF with wrong length"""
        assert validate_cpf("123456789") == False
        assert validate_cpf("123456789012") == False


class TestCNPJValidation:
    """Test CNPJ validation"""
    
    def test_valid_cnpj(self):
        """Test valid CNPJ numbers"""
        assert validate_cnpj("11.444.777/0001-61") == True
        assert validate_cnpj("11444777000161") == True
    
    def test_invalid_cnpj_wrong_digits(self):
        """Test CNPJ with wrong check digits"""
        assert validate_cnpj("11.444.777/0001-00") == False
    
    def test_invalid_cnpj_same_digits(self):
        """Test CNPJ with all same digits"""
        assert validate_cnpj("11.111.111/1111-11") == False
    
    def test_invalid_cnpj_wrong_length(self):
        """Test CNPJ with wrong length"""
        assert validate_cnpj("1234567890123") == False


class TestFormatting:
    """Test formatting functions"""
    
    def test_format_cpf(self):
        """Test CPF formatting"""
        assert format_cpf("52998224725") == "529.982.247-25"
    
    def test_format_cnpj(self):
        """Test CNPJ formatting"""
        assert format_cnpj("11444777000161") == "11.444.777/0001-61"
    
    def test_format_phone_mobile(self):
        """Test mobile phone formatting"""
        assert format_phone("11999999999") == "(11) 99999-9999"
    
    def test_format_phone_landline(self):
        """Test landline phone formatting"""
        assert format_phone("1133333333") == "(11) 3333-3333"
    
    def test_format_currency(self):
        """Test currency formatting"""
        assert format_currency(Decimal("1234.56")) == "R$ 1.234,56"
        assert format_currency(Decimal("1000000.00")) == "R$ 1.000.000,00"


class TestDaysOverdue:
    """Test days overdue calculation"""
    
    def test_not_overdue(self):
        """Test when not overdue (future date)"""
        future_date = date(2030, 1, 1)
        assert days_overdue(future_date) == 0
    
    def test_due_today(self):
        """Test when due today"""
        today = date.today()
        assert days_overdue(today) == 0


class TestSanitizeFilename:
    """Test filename sanitization"""
    
    def test_sanitize_normal_filename(self):
        """Test normal filename"""
        assert sanitize_filename("document.pdf") == "document.pdf"
    
    def test_sanitize_filename_with_spaces(self):
        """Test filename with spaces"""
        assert sanitize_filename("my document.pdf") == "my_document.pdf"
    
    def test_sanitize_filename_with_special_chars(self):
        """Test filename with special characters"""
        result = sanitize_filename("my@doc#ument!.pdf")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result
