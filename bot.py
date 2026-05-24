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
        self.testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        self.client = None 
        self.order_manager = None
        self.strategy = Strategy()
        self.state_file = 'state.json'
        self.log_csv = 'trades.csv'
        self.state = self.load_state()

    def initialize_client(self):
        """Inicializa el cliente con limpieza por Regex (fulmina comillas y espacios)."""
        if self.client is None:
            import re
            def clean(val):
                if not val: return ""
                # Solo permite caracteres alfanuméricos (A-Z, 0-9)
                return re.sub(r'[^a-zA-Z0-9]', '', str(val))

            k = clean(self.api_key)
            s = clean(self.api_secret)
            
            logger.info(f"MODO: {'TESTNET' if self.testnet else 'MAINNET'} | KEY LIMPIA: [{k[:4]}...{k[-4:]}] (Len: {len(k)})")

            try:
                self.client = Client(k, s, testnet=self.testnet)
                server_time = self.client.get_server_time()
                self.client.timestamp_offset = server_time['serverTime'] - int(time.time() * 1000)
                
                self.order_manager = OrderManager(self.client)
                
                acc = self.client.get_account(recvWindow=10000)
                usdt_bal = 0.0
                for b in acc['balances']:
                    if b['asset'] == 'USDT':
                        usdt_bal = float(b['free'])
                        break
                
                self.state['balance_usdt'] = usdt_bal
                logger.info(f"✅ ¡CONECTADO! Saldo inicial: {usdt_bal} USDT")
                
            except Exception as e:
                logger.error(f"❌ FALLO DE AUTENTICACIÓN: {e}")
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
        """Obtiene el saldo de USDT de la cuenta."""
        try:
            if not self.client: return 0.0
            balance = self.client.get_asset_balance(asset='USDT')
            return float(balance['free']) if balance else 0.0
        except Exception as e:
            logger.error(f"Error balance: {e}")
            return 0.0

    def run_cycle(self):
        # Asegurar inicialización antes de cada ciclo si falló antes
        if not self.client:
            self.initialize_client()
            if not self.client: return

        # Actualizar balance siempre que estemos inicializados
        current_balance = self.get_balance()
        self.state['balance_usdt'] = current_balance

        # Obtener datos usando la vela CERRADA (-2) para mayor estabilidad
        try:
            df = self.fetch_data()
            self.state['last_price'] = float(df['close'].iloc[-2])
            self.state['last_rsi'] = float(df['rsi'].iloc[-2])
            self.state['last_ema200'] = float(df['ema200'].iloc[-2])
            logger.info(f"Mercado: {self.state['last_price']} | RSI: {self.state['last_rsi']:.1f}")
        except Exception as e:
            logger.error(f"Error datos mercado: {e}")
            
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

            # 2. Señales
            signal = self.strategy.check_signals(df) # strategy.py debe usar iloc[-2] también
            last_price = self.state['last_price']
            last_rsi = self.state['last_rsi']

            logger.info(f"Symbol: {self.state['symbol']} | Price: {last_price} | RSI: {last_rsi:.2f} | Signal: {signal}")

            # 3. Lógica de Ejecución
            if signal == 'BUY' and not self.state['current_position']:
                qty_to_buy = 1.0 # AJUSTAR SEGÚN MONTO DESEADO
                
                order = self.order_manager.place_market_buy(self.state['symbol'], qty_to_buy)
                if order:
                    fill_price = float(order['fills'][0]['price'])
                    qty = float(order['executedQty'])
                    
                    # OCO: TP 1.2%, SL 0.8%
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
                # Monitoreo de posición abierta
                pass

        except Exception as e:
            logger.error(f"Error en el ciclo del bot: {e}")

    def start(self):
        logger.info("Iniciando loop del bot...")
        self.initialize_client()
        while True:
            self.run_cycle()
            time.sleep(60)

if __name__ == "__main__":
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET') or os.getenv('BINANCE_SECRET')
    
    bot = TradingBot(API_KEY, API_SECRET)
    bot.start()
