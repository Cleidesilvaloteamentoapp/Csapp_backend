import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for testing"""
    with patch("app.database.get_supabase_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_admin_supabase():
    """Mock Supabase admin client for testing"""
    with patch("app.database.get_supabase_admin_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def app():
    """Create test application"""
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def admin_token():
    """Mock admin JWT token"""
    return "mock-admin-token"


@pytest.fixture
def client_token():
    """Mock client JWT token"""
    return "mock-client-token"


@pytest.fixture
def sample_client_data():
    """Sample client data for testing"""
    return {
        "email": "test@example.com",
        "password": "SecurePass123!",
        "full_name": "Test Client",
        "cpf_cnpj": "12345678901",
        "phone": "11999999999"
    }


@pytest.fixture
def sample_development_data():
    """Sample development data for testing"""
    return {
        "name": "Test Development",
        "description": "A test development",
        "location": "Test Location, City - State"
    }


@pytest.fixture
def sample_lot_data():
    """Sample lot data for testing"""
    return {
        "development_id": "test-dev-id",
        "lot_number": "01",
        "block": "A",
        "area_m2": 300.00,
        "price": 50000.00,
        "status": "available"
    }
