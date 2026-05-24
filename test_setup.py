import os
import sys
import pandas as pd
import numpy as np
from binance.client import Client

def test_environment():
    print("--- Verificando Entorno ---")
    try:
        import flask
        import binance
        print("✅ Librerías instaladas correctamente.")
    except ImportError as e:
        print(f"❌ Falta una librería: {e}")
        return False

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        print("⚠️ Advertencia: BINANCE_API_KEY o BINANCE_API_SECRET no están configuradas.")
        print("   Para probar sin API, el bot fallará al intentar conectar con Binance.")
    else:
        print("✅ Variables de entorno detectadas.")
        try:
            client = Client(api_key, api_secret)
            status = client.get_system_status()
            print(f"✅ Conexión con Binance exitosa. Status: {status['msg']}")
        except Exception as e:
            print(f"❌ Error al conectar con Binance: {e}")

    return True

if __name__ == "__main__":
    if test_environment():
        print("\n--- Instrucciones de ejecución ---")
        print("1. Instala dependencias: pip install -r requirements.txt")
        print("2. Configura tus credenciales (Windows):")
        print('   $env:BINANCE_API_KEY="TU_KEY"; $env:BINANCE_API_SECRET="TU_SECRET"')
        print("3. Ejecuta el dashboard: python app.py")
        print("4. Abre en tu navegador: http://localhost:5000")
    else:
        sys.exit(1)
