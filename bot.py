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
        """Inicializa el cliente con diagnóstico profundo."""
        if self.client is None:
            import re
            
            # Ver valor original (anonimizado)
            raw_k = str(self.api_key) if self.api_key else "VACÍO"
            raw_s = str(self.api_secret) if self.api_secret else "VACÍO"
            logger.info(f"ORIGINAL -> Key: {raw_k[:4]}..., Secret: {raw_s[:4]}...")

            def clean(val):
                if not val or val == "VACÍO": return ""
                # Fulminamos todo lo que no sea alfanumérico
                return re.sub(r'[^a-zA-Z0-9]', '', str(val))

            k = clean(self.api_key)
            s = clean(self.api_secret)
            
            logger.info(f"LIMPIA -> Key Len: {len(k)}, Secret Len: {len(s)}")

            try:
                self.client = Client(k, s, testnet=self.testnet)
                server_time = self.client.get_server_time()
                self.client.timestamp_offset = server_time['serverTime'] - int(time.time() * 1000)
                
                self.order_manager = OrderManager(self.client)
                
                # Obtener todos los balances de una vez
                acc = self.client.get_account(recvWindow=10000)
                usdt_bal = 0.0
                asset_bal = 0.0
                asset_name = self.state['symbol'].replace('USDT', '')
                
                for b in acc['balances']:
                    if b['asset'] == 'USDT':
                        usdt_bal = float(b['free'])
                    if b['asset'] == asset_name:
                        asset_bal = float(b['free'])
                
                self.state['balance_usdt'] = usdt_bal
                self.state['balance_asset'] = asset_bal
                logger.info(f"✅ ¡CONECTADO! USDT: {usdt_bal} | {asset_name}: {asset_bal}")
                
            except Exception as e:
                logger.error(f"❌ FALLO DE AUTENTICACIÓN: {e}")
                self.state['balance_usdt'] = -1.0
            
            self.save_state()

    def get_balances(self):
        """Obtiene balances actualizados de USDT y el Activo."""
        try:
            if not self.client: return 0.0, 0.0
            acc = self.client.get_account(recvWindow=10000)
            usdt = 0.0
            asset = 0.0
            asset_name = self.state['symbol'].replace('USDT', '')
            for b in acc['balances']:
                if b['asset'] == 'USDT': usdt = float(b['free'])
                if b['asset'] == asset_name: asset = float(b['free'])
            return usdt, asset
        except Exception as e:
            logger.error(f"Error actualizando balances: {e}")
            return self.state.get('balance_usdt', 0.0), self.state.get('balance_asset', 0.0)

    def run_cycle(self):
        # Asegurar inicialización
        if not self.client:
            self.initialize_client()
            if not self.client: return

        # Actualizar balances
        u, a = self.get_balances()
        self.state['balance_usdt'] = u
        self.state['balance_asset'] = a

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
