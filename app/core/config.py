from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_NAME: str = "Real Estate Management API"
    APP_VERSION: str = "1.0.0"
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Asaas Payment Gateway
    ASAAS_API_KEY: str
    ASAAS_ENVIRONMENT: str = "sandbox"
    
    # Email
    EMAIL_PROVIDER_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "noreply@example.com"
    
    # WhatsApp
    WHATSAPP_API_KEY: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    
    # JWT (reference from Supabase)
    JWT_SECRET: str = ""
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def asaas_base_url(self) -> str:
        if self.ASAAS_ENVIRONMENT == "production":
            return "https://api.asaas.com/v3"
        return "https://sandbox.asaas.com/api/v3"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
