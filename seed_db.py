import os
import requests
from datetime import date, timedelta
import uuid

# URL de la API local
BASE_URL = os.environ.get("AUTH_API_URL", "http://localhost:8000")

def seed_test_license():
    test_password = os.environ.get("SEED_TEST_PASSWORD")
    if not test_password:
        raise SystemExit(
            "ERROR: defina SEED_TEST_PASSWORD antes de ejecutar este script "
            "(ej: SEED_TEST_PASSWORD=$(python -c \"import secrets; print(secrets.token_urlsafe(16))\"))"
        )
    test_license = {
        "user": "analista_082",
        "password": test_password,
        "name": "Hobéd Díaz",
        "mail": "hobeddiaz@example.com",
        "licence_id": str(uuid.uuid4()),
        "fecha_compra": str(date.today()),
        "dias_vigencia": 365,
        "fecha_expiracion": str(date.today() + timedelta(days=365)),
        "empresa": "SOVEREIGN Intelligence"
    }

    try:
        # Intentar crear la licencia
        response = requests.post(f"{BASE_URL}/licencias/", json=test_license, timeout=10)
        if response.status_code == 201:
            print("✅ Licencia de prueba creada exitosamente.")
            print(f"Usuario: {test_license['user']}")
        elif response.status_code == 400:
            print("ℹ️ El usuario ya existe o la licencia ya está registrada.")
        else:
            print(f"❌ Error al crear licencia: {response.text}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}. Asegúrese de que auth_api.py esté ejecutándose.")

if __name__ == "__main__":
    seed_test_license()
