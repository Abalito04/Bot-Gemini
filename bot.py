import time
import json
import logging
import csv
import os
import re
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

    def load_state(self):
        """Carga el estado desde el archivo JSON o crea uno nuevo."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "is_running": False,
            "symbol": "SOLUSDT",
            "timeframe": "1m",
            "current_position": None,
            "daily_pnl": 0.0,
            "max_daily_loss": -10.0,
            "monto_operacion": 100.0,
            "tp_pct": 1.2,
            "sl_pct": 0.8,
            "rsi_buy": 42.0,
            "rsi_sell": 62.0,
            "balance_usdt": 0.0,
            "balance_asset": 0.0,
            "operaciones": []
        }

    def save_state(self):
        """Guarda el estado actual en el archivo JSON."""
        self.state['last_update'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=4)

    def initialize_client(self):
        """Inicializa el cliente con limpieza por Regex (fulmina comillas y espacios)."""
        if self.client is None:
            def clean(val):
                if not val: return ""
                return re.sub(r'[^a-zA-Z0-9]', '', str(val))

            k = clean(self.api_key)
            s = clean(self.api_secret)
            
            logger.info(f"MODO: {'TESTNET' if self.testnet else 'MAINNET'} | KEY LIMPIA: [{k[:4]}...{k[-4:]}] (Len: {len(k)})")

            try:
                self.client = Client(k, s, testnet=self.testnet)
                server_time = self.client.get_server_time()
                self.client.timestamp_offset = server_time['serverTime'] - int(time.time() * 1000)
                
                self.order_manager = OrderManager(self.client)
                
                # Obtener balances iniciales
                acc = self.client.get_account(recvWindow=10000)
                usdt_bal = 0.0
                asset_bal = 0.0
                asset_name = self.state['symbol'].replace('USDT', '')
                
                for b in acc['balances']:
                    if b['asset'] == 'USDT': usdt_bal = float(b['free'])
                    if b['asset'] == asset_name: asset_bal = float(b['free'])
                
                self.state['balance_usdt'] = usdt_bal
                self.state['balance_asset'] = asset_bal
                logger.info(f"✅ ¡CONECTADO! USDT: {usdt_bal} | {asset_name}: {asset_bal}")
                
            except Exception as e:
                logger.error(f"❌ FALLO DE AUTENTICACIÓN: {e}")
                self.state['balance_usdt'] = -1.0
            
            self.save_state()

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
            limit=250 
        )
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['rsi'] = self.strategy.calculate_rsi(df)
        df['ema200'] = self.strategy.calculate_ema(df, 200)
        return df

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
        if not self.client:
            self.initialize_client()
            if not self.client: return

        u, a = self.get_balances()
        self.state['balance_usdt'] = u
        self.state['balance_asset'] = a

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
            rsi_buy = self.state.get('rsi_buy', 42.0)
            rsi_sell = self.state.get('rsi_sell', 62.0)
            signal = self.strategy.check_signals(df, rsi_buy=rsi_buy, rsi_sell=rsi_sell) 
            last_price = self.state['last_price']
            last_rsi = self.state['last_rsi']

            if signal:
                logger.info(f"SEÑAL DETECTADA: {signal} | RSI: {last_rsi:.2f}")

            # 3. Lógica de Ejecución (COMPRA ACTIVA)
            if signal == 'BUY' and not self.state['current_position']:
                price = self.state['last_price']
                qty = self.state['monto_operacion'] / price

                logger.info(f"🚀 SEÑAL BUY: Ejecutando orden de {qty:.4f} {self.state['symbol']}...")

                # Ejecutar compra
                order = self.order_manager.place_market_buy(self.state['symbol'], qty)

                if order and 'fills' in order:
                    fill_price = float(order['fills'][0]['price'])
                    actual_qty = float(order['executedQty'])

                    # Calcular precios OCO usando valores configurables del estado
                    tp_pct = self.state.get('tp_pct', 1.2)
                    sl_pct = self.state.get('sl_pct', 0.8)

                    tp_price = fill_price * (1 + tp_pct/100)
                    sl_trigger = fill_price * (1 - sl_pct/100)
                    sl_limit = sl_trigger * 0.998 

                    logger.info(f"Colocando OCO: TP {tp_price:.2f} (+{tp_pct}%) | SL {sl_trigger:.2f} (-{sl_pct}%)")
                    oco = self.order_manager.place_oco_sell(
                        self.state['symbol'], actual_qty, tp_price, sl_trigger, sl_limit
                    )
                    
                    if oco:
                        self.state['current_position'] = {
                            'price': fill_price,
                            'qty': actual_qty,
                            'time': datetime.now().isoformat()
                        }
                        self.state['operaciones'].append({
                            'timestamp': datetime.now().isoformat(),
                            'side': 'BUY',
                            'price': fill_price,
                            'qty': actual_qty,
                            'rsi': self.state['last_rsi'],
                            'reason': 'RSI Oversold + EMA Trend'
                        })
                        self.save_state()
                        logger.info("✅ ¡COMPRA REALIZADA Y OCO COLOCADA!")
                    else:
                        logger.error("❌ Falló la OCO. ¡CUIDADO! Posición abierta sin protección.")
                else:
                    logger.error("❌ Falló la orden de compra.")

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
