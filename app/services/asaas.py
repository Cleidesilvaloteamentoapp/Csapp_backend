import httpx
from typing import Optional, Dict, Any, List
from datetime import date
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings


class AsaasService:
    """Service for Asaas payment gateway integration"""
    
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.asaas_base_url
        self.api_key = settings.ASAAS_API_KEY
        self.headers = {
            "access_token": self.api_key,
            "Content-Type": "application/json"
        }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Asaas API with retry logic"""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=f"{self.base_url}/{endpoint}",
                headers=self.headers,
                json=data,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def create_customer(
        self,
        name: str,
        cpf_cnpj: str,
        email: str,
        phone: Optional[str] = None,
        address: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a new customer in Asaas
        Returns customer data including the Asaas customer ID
        """
        payload = {
            "name": name,
            "cpfCnpj": cpf_cnpj.replace(".", "").replace("-", "").replace("/", ""),
            "email": email,
        }
        
        if phone:
            payload["phone"] = phone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        
        if address:
            payload["address"] = address.get("street", "")
            payload["addressNumber"] = address.get("number", "")
            payload["complement"] = address.get("complement", "")
            payload["province"] = address.get("neighborhood", "")
            payload["postalCode"] = address.get("zip_code", "").replace("-", "")
        
        return await self._request("POST", "customers", data=payload)
    
    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer by Asaas ID"""
        return await self._request("GET", f"customers/{customer_id}")
    
    async def update_customer(
        self,
        customer_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update customer data in Asaas"""
        payload = {}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        
        return await self._request("PUT", f"customers/{customer_id}", data=payload)
    
    async def create_payment(
        self,
        customer_id: str,
        value: Decimal,
        due_date: date,
        description: str,
        external_reference: Optional[str] = None,
        installment_count: int = 1,
        installment_value: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Create a boleto payment in Asaas
        Returns payment data including barcode and payment URL
        """
        payload = {
            "customer": customer_id,
            "billingType": "BOLETO",
            "value": float(value),
            "dueDate": due_date.isoformat(),
            "description": description,
        }
        
        if external_reference:
            payload["externalReference"] = external_reference
        
        if installment_count > 1 and installment_value:
            payload["installmentCount"] = installment_count
            payload["installmentValue"] = float(installment_value)
        
        return await self._request("POST", "payments", data=payload)
    
    async def create_installment_payments(
        self,
        customer_id: str,
        total_value: Decimal,
        installment_count: int,
        first_due_date: date,
        description: str,
        external_reference: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Create multiple installment payments (boletos)
        Returns list of created payments
        """
        installment_value = total_value / installment_count
        
        payload = {
            "customer": customer_id,
            "billingType": "BOLETO",
            "value": float(total_value),
            "dueDate": first_due_date.isoformat(),
            "description": description,
            "installmentCount": installment_count,
            "installmentValue": float(installment_value),
        }
        
        if external_reference:
            payload["externalReference"] = external_reference
        
        result = await self._request("POST", "payments", data=payload)
        
        if installment_count > 1:
            payments = await self.list_payments(customer_id=customer_id)
            return payments.get("data", [])
        
        return [result]
    
    async def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """Get payment by Asaas ID"""
        return await self._request("GET", f"payments/{payment_id}")
    
    async def list_payments(
        self,
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        due_date_ge: Optional[date] = None,
        due_date_le: Optional[date] = None,
        offset: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List payments with filters"""
        params = {"offset": offset, "limit": limit}
        
        if customer_id:
            params["customer"] = customer_id
        if status:
            params["status"] = status
        if due_date_ge:
            params["dueDate[ge]"] = due_date_ge.isoformat()
        if due_date_le:
            params["dueDate[le]"] = due_date_le.isoformat()
        
        return await self._request("GET", "payments", params=params)
    
    async def cancel_payment(self, payment_id: str) -> Dict[str, Any]:
        """Cancel a payment"""
        return await self._request("DELETE", f"payments/{payment_id}")
    
    async def get_payment_barcode(self, payment_id: str) -> Dict[str, Any]:
        """Get boleto barcode and digitable line"""
        return await self._request("GET", f"payments/{payment_id}/identificationField")
    
    async def list_overdue_payments(
        self,
        customer_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all overdue payments"""
        result = await self.list_payments(
            customer_id=customer_id,
            status="OVERDUE"
        )
        return result.get("data", [])


def get_asaas_service() -> AsaasService:
    """Dependency for getting Asaas service instance"""
    return AsaasService()
