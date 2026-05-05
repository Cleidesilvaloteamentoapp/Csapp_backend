#!/usr/bin/env python3
"""
Script para testar o endpoint POST /admin/clients diretamente no backend.
Uso: python test_post_client.py
"""

import requests
import json
import sys

# CONFIGURAÇÃO - AJUSTE CONFORME NECESSÁRIO
BACKEND_URL = "https://csappbackend-production.up.railway.app"  # URL do backend no Railway
# BACKEND_URL = "http://localhost:8000"  # Para teste local

# Token de autenticação (pegue do localStorage do frontend ou faça login)
# Substitua pelo token real do seu usuário SUPER_ADMIN
AUTH_TOKEN = "seu_token_aqui"  

def test_create_client():
    """Testa a criação de um cliente via POST /admin/clients"""
    
    url = f"{BACKEND_URL}/api/v1/admin/clients"
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Dados do cliente de teste
    payload = {
        "email": "teste@exemplo.com",
        "full_name": "Cliente Teste",
        "cpf_cnpj": "12345678901",
        "phone": "11999999999",
        "contract_number": "TEST-001",
        "matricula": "MAT-001",
        "address": {
            "street": "Rua Teste",
            "number": "123",
            "city": "São Paulo",
            "state": "SP",
            "zip_code": "01234-567"
        },
        "notes": "Cliente criado via teste de API",
        "create_access": False
    }
    
    print(f"🔍 Testando POST para: {url}")
    print(f"📦 Payload:\n{json.dumps(payload, indent=2)}\n")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📄 Response Headers:")
        for key, value in response.headers.items():
            print(f"   {key}: {value}")
        
        print(f"\n📝 Response Body:")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)
        
        if response.status_code == 201:
            print("\n✅ SUCESSO! Cliente criado com sucesso!")
            return True
        elif response.status_code == 405:
            print("\n❌ ERRO 405: Method Not Allowed")
            print("   A rota POST não está sendo aceita pelo servidor")
            return False
        elif response.status_code == 401:
            print("\n❌ ERRO 401: Não autorizado")
            print("   Atualize o AUTH_TOKEN no script com um token válido")
            return False
        elif response.status_code == 403:
            print("\n❌ ERRO 403: Acesso negado")
            print("   Verifique se o usuário tem permissão 'manage_clients'")
            return False
        else:
            print(f"\n⚠️  Status inesperado: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição: {str(e)}")
        return False

def test_list_clients():
    """Testa o endpoint GET /admin/clients para comparação"""
    
    url = f"{BACKEND_URL}/api/v1/admin/clients"
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"\n🔍 Testando GET para: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📊 GET Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ GET funcionando corretamente!")
            return True
        else:
            print(f"⚠️  GET retornou: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição GET: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTE DE ENDPOINT POST /admin/clients")
    print("=" * 60)
    
    if AUTH_TOKEN == "seu_token_aqui":
        print("\n⚠️  AVISO: Atualize a variável AUTH_TOKEN no script!")
        print("   Você pode pegar o token do localStorage do frontend ou fazer login via API")
        print("\n   Exemplo de como obter o token via login:")
        print("   POST /api/v1/auth/login")
        print("   {\"email\": \"seu_email\", \"password\": \"sua_senha\"}")
        sys.exit(1)
    
    # Testa GET primeiro para verificar conectividade
    print("\n📍 Passo 1: Testando GET (deve funcionar)")
    get_works = test_list_clients()
    
    # Testa POST
    print("\n📍 Passo 2: Testando POST (problema relatado)")
    post_works = test_create_client()
    
    print("\n" + "=" * 60)
    print("📋 RESUMO")
    print("=" * 60)
    print(f"GET /admin/clients:  {'✅ OK' if get_works else '❌ FALHOU'}")
    print(f"POST /admin/clients: {'✅ OK' if post_works else '❌ FALHOU'}")
    
    if not post_works and get_works:
        print("\n💡 DIAGNÓSTICO:")
        print("   - GET funciona, mas POST não")
        print("   - Possíveis causas:")
        print("     1. Problema de roteamento no FastAPI")
        print("     2. Middleware bloqueando POST")
        print("     3. Problema no proxy do frontend")
        print("     4. CORS não configurado corretamente para POST")
