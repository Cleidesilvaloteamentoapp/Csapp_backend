import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


class TestAuthRoutes:
    """Test authentication routes"""
    
    def test_login_success(self, client, mock_supabase):
        """Test successful login"""
        mock_session = MagicMock()
        mock_session.access_token = "test-access-token"
        mock_session.refresh_token = "test-refresh-token"
        
        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        mock_user.email = "test@example.com"
        
        mock_response = MagicMock()
        mock_response.session = mock_session
        mock_response.user = mock_user
        
        mock_supabase.auth.sign_in_with_password.return_value = mock_response
        
        mock_profile = MagicMock()
        mock_profile.data = {"id": "test-user-id", "role": "client", "full_name": "Test User"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_profile
        
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    def test_login_invalid_credentials(self, client, mock_supabase):
        """Test login with invalid credentials"""
        mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword"
        })
        
        assert response.status_code == 401
    
    def test_login_missing_fields(self, client):
        """Test login with missing fields"""
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com"
        })
        
        assert response.status_code == 422


class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test health check returns healthy status"""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns API info"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["status"] == "running"
