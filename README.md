# Binance Scalper Bot 🚀

Bot de trading algorítmico diseñado para scalping de alta frecuencia en Binance, optimizado para Railway.

## Requerimientos
- Python 3.9+
- API Key y Secret de Binance (con permisos de Trading).

## Configuración en Railway
Añade las siguientes variables de entorno:
- `BINANCE_API_KEY`: Tu clave de API.
- `BINANCE_API_SECRET`: Tu clave secreta.
- `PORT`: 5000 (Opcional, Railway lo asigna).

## Arquitectura
- `app.py`: Servidor Flask y Dashboard.
- `bot.py`: Motor de trading (Loop principal).
- `order_manager.py`: Gestión de órdenes (Market + OCO) y redondeo de precisión.
- `strategy.py`: Lógica de RSI (14 periodos).
- `state.json`: Persistencia de estado (PnL, Posiciones).

## Estrategia
- **LONG (Compra)**: RSI <= 42.
- **OCO (Venta)**: Take Profit ~1.2%, Stop Loss ~0.8% (ajustable en `bot.py`).
- **Filtro de Riesgo**: Max Daily Loss (detiene el bot si se alcanza).

## API Endpoints
- `GET /api/state`: Estado actual en tiempo real.
- `POST /api/start`: Iniciar el bot.
- `POST /api/stop`: Detener el bot.
