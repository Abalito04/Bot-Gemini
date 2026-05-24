import time
import json
import logging
import csv
import os
from datetime import datetime
from binance.client import Client
from order_manager import OrderManager
from strategy import Strategy
import pandas as pd

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = None # Se inicializará en start()
        self.order_manager = None
        self.strategy = Strategy()
        self.state_file = 'state.json'
        self.log_csv = 'trades.csv'
        self.state = self.load_state()

    def initialize_client(self):
        """Inicializa el cliente imitando la configuración del bot exitoso."""
        if self.client is None:
            def clean(val):
                if not val: return ""
                return str(val).strip().replace('"', '').replace("'", "").replace('\\', '')

            k = clean(self.api_key)
            s = clean(self.api_secret)
            
            logger.info(f"INICIANDO CONEXIÓN ROBUSTA: [{k[:4]}...{k[-4:]}]")

            try:
                # Usamos la inicialización más limpia posible
                # tld='com' asegura que apunte a binance.com (Mainnet)
                self.client = Client(k, s, tld='com')
                
                # Sincronización de tiempo forzada (como hace el otro bot con timestamp)
                self.sync_time()
                
                self.order_manager = OrderManager(self.client)
                
                # Prueba de fuego: get_account es lo que usa el otro bot
                acc = self.client.get_account(recvWindow=10000)
                usdt_bal = 0.0
                for b in acc['balances']:
                    if b['asset'] == 'USDT':
                        usdt_bal = float(b['free'])
                        break
                
                self.state['balance_usdt'] = usdt_bal
                logger.info(f"✅ ¡CONECTADO CON ÉXITO! Saldo: {usdt_bal} USDT")
                
            except Exception as e:
                logger.error(f"❌ Error de autenticación: {e}")
                self.state['balance_usdt'] = -1.0
            
            self.save_state()

    def sync_time(self):
        """Sincroniza el tiempo local con el servidor de Binance."""
        try:
            server_time = self.client.get_server_time()
            self.client.timestamp_offset = server_time['serverTime'] - int(time.time() * 1000)
            logger.info(f"Tiempo sincronizado con Binance. Offset: {self.client.timestamp_offset}ms")
        except Exception as e:
            logger.error(f"Error sincronizando tiempo: {e}")
        
    def load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {
            "is_running": False,
            "symbol": "SOLUSDT",
            "timeframe": "1m",
            "current_position": None,
            "daily_pnl": 0.0,
            "max_daily_loss": -10.0,
            "operaciones": []
        }

    def save_state(self):
        self.state['last_update'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=4)

    def log_trade_csv(self, trade_data):
        file_exists = os.path.isfile(self.log_csv)
        with open(self.log_csv, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['timestamp', 'symbol', 'side', 'price', 'rsi', 'qty', 'pnl', 'reason'])
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade_data)

    def fetch_data(self):
        candles = self.client.get_klines(
            symbol=self.state['symbol'],
            interval=self.state['timeframe'],
            limit=250 # Aumentado para EMA 200
        )
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['rsi'] = self.strategy.calculate_rsi(df)
        df['ema200'] = self.strategy.calculate_ema(df, 200)
        return df

    def get_balance(self):
        """Obtiene el saldo de USDT con mayor tolerancia de tiempo (recvWindow)."""
        try:
            asset = "USDT"
            # Consultamos la cuenta completa con una ventana de tiempo más amplia (10 segundos)
            account = self.client.get_account(recvWindow=10000)
            balances = account.get('balances', [])
            
            for b in balances:
                if b['asset'] == asset:
                    free_amount = float(b['free'])
                    logger.info(f"Balance recuperado (get_account): {free_amount} {asset}")
                    return free_amount
            
            logger.warning(f"No se encontró {asset} en los balances de la cuenta.")
            return 0.0
        except Exception as e:
            logger.error(f"Error crítico obteniendo balance de Binance: {e}")
            return 0.0

    def run_cycle(self):
        # Actualizar balance siempre
        current_balance = self.get_balance()
        self.state['balance_usdt'] = current_balance
        
        # Obtener datos de mercado iniciales para que el dashboard no esté vacío
        try:
            df = self.fetch_data()
            self.state['last_price'] = float(df['close'].iloc[-1])
            self.state['last_rsi'] = float(df['rsi'].iloc[-1])
            self.state['last_ema200'] = float(df['ema200'].iloc[-1])
            logger.info(f"Datos de mercado actualizados: {self.state['last_price']}")
        except Exception as e:
            logger.error(f"Error cargando datos iniciales: {e}")
            
        self.save_state()

        if not self.state.get('is_running', False):
            return

        try:
            # 1. Verificar límites de riesgo
            if self.state['daily_pnl'] <= self.state['max_daily_loss']:
                logger.warning("Límite de pérdida diaria alcanzado. Deteniendo bot.")
                self.state['is_running'] = False
                self.save_state()
                return

            # 2. Obtener datos y señales
            df = self.fetch_data()
            signal = self.strategy.check_signals(df)
            last_price = float(df['close'].iloc[-1])
            last_rsi = float(df['rsi'].iloc[-1])
            last_ema = float(df['ema200'].iloc[-1])

            # Actualizar estado para el Dashboard
            self.state['last_price'] = last_price
            self.state['last_rsi'] = last_rsi
            self.state['last_ema200'] = last_ema
            self.save_state()

            logger.info(f"Symbol: {self.state['symbol']} | Price: {last_price} | RSI: {last_rsi:.2f} | Signal: {signal}")

            # 3. Lógica de Ejecución
            if signal == 'BUY' and not self.state['current_position']:
                # Calcular Qty basado en balance (ejemplo 10 USDT fijo para scalping)
                # En un entorno real, se calcularía dinámicamente
                qty_to_buy = 1.0 # Ejemplo para SOL (ajustar según USDT)
                
                order = self.order_manager.place_market_buy(self.state['symbol'], qty_to_buy)
                if order:
                    fill_price = float(order['fills'][0]['price'])
                    qty = float(order['executedQty'])
                    
                    # Configurar OCO: TP 1.2%, SL 0.8%
                    tp_price = fill_price * 1.012
                    sl_trigger = fill_price * 0.992
                    sl_limit = fill_price * 0.991
                    
                    oco_order = self.order_manager.place_oco_sell(
                        self.state['symbol'], qty, tp_price, sl_trigger, sl_limit
                    )
                    
                    if oco_order:
                        self.state['current_position'] = {
                            'entry_price': fill_price,
                            'qty': qty,
                            'oco_id': oco_order['orderListId']
                        }
                        self.log_trade_csv({
                            'timestamp': datetime.now().isoformat(),
                            'symbol': self.state['symbol'],
                            'side': 'BUY',
                            'price': fill_price,
                            'rsi': last_rsi,
                            'qty': qty,
                            'pnl': 0,
                            'reason': 'RSI Oversold'
                        })
                        self.save_state()

            elif self.state['current_position']:
                # Verificar si la OCO se ejecutó
                # En scalping de alta frecuencia, se suele monitorear el balance o eventos de websocket
                # Aquí simplificamos consultando la orden OCO
                oco_status = self.client.get_order_list(orderListId=self.state['current_position']['oco_id'])
                # Lógica para detectar si se cerró...
                # (Para MVP, si no hay posición en balance o la orden no está activa)
                pass

        except Exception as e:
            logger.error(f"Error en el ciclo del bot: {e}")

    def start(self):
        logger.info("Iniciando loop del bot...")
        self.initialize_client() # Inicializar cliente antes del primer ciclo
        while True:
            self.run_cycle()
            time.sleep(60) # Esperar 1 minuto para el siguiente ciclo

if __name__ == "__main__":
    # Railway inyecta estas variables automáticamente
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    
    if not API_KEY or not API_SECRET:
        logger.error("ERROR: No se encontraron las API Keys en las variables de entorno.")
    
    bot = TradingBot(API_KEY, API_SECRET)
    bot.start()
