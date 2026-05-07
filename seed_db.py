import requests
from datetime import date, timedelta
import uuid

# URL de la API local
BASE_URL = "http://localhost:8000"

def seed_test_license():
    test_license = {
        "user": "analista_082",
        "password": "password123",
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
        response = requests.post(f"{BASE_URL}/licencias/", json=test_license)
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
