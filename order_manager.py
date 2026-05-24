import logging
from binance.client import Client
from binance.enums import *
from decimal import Decimal, ROUND_DOWN

class OrderManager:
    def __init__(self, client: Client):
        self.client = client
        self.logger = logging.getLogger(__name__)

    def get_symbol_info(self, symbol):
        """Obtiene información del símbolo para filtros de precisión."""
        info = self.client.get_symbol_info(symbol)
        filters = {f['filterType']: f for f in info['filters']}
        return filters

    def round_step_size(self, quantity, step_size):
        """Redondea la cantidad según el STEP_SIZE de Binance."""
        step_size_dec = Decimal(str(step_size))
        return float(Decimal(str(quantity)).quantize(step_size_dec, rounding=ROUND_DOWN))

    def round_price_size(self, price, tick_size):
        """Redondea el precio según el TICK_SIZE de Binance."""
        tick_size_dec = Decimal(str(tick_size))
        return float(Decimal(str(price)).quantize(tick_size_dec, rounding=ROUND_DOWN))

    def place_market_buy(self, symbol, quantity):
        """Ejecuta una orden de compra a mercado."""
        try:
            filters = self.get_symbol_info(symbol)
            step_size = filters['LOT_SIZE']['stepSize']
            qty = self.round_step_size(quantity, step_size)
            
            order = self.client.create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            self.logger.info(f"Market Buy Executed: {symbol} Qty: {qty}")
            return order
        except Exception as e:
            self.logger.error(f"Error in Market Buy: {e}")
            return None

    def place_oco_sell(self, symbol, quantity, take_profit_price, stop_loss_price, stop_limit_price):
        """
        Coloca una orden OCO para cerrar posición con TP y SL.
        take_profit_price: Precio de venta (ganancia).
        stop_loss_price: Precio de activación del stop.
        stop_limit_price: Precio límite de venta tras activación del stop.
        """
        try:
            filters = self.get_symbol_info(symbol)
            step_size = filters['LOT_SIZE']['stepSize']
            tick_size = filters['PRICE_FILTER']['tickSize']
            
            qty = self.round_step_size(quantity, step_size)
            tp_price = self.round_price_size(take_profit_price, tick_size)
            sl_price = self.round_price_size(stop_loss_price, tick_size)
            sl_limit_price = self.round_price_size(stop_limit_price, tick_size)

            order = self.client.create_oco_order(
                symbol=symbol,
                side=SIDE_SELL,
                quantity=qty,
                price=str(tp_price),
                stopPrice=str(sl_price),
                stopLimitPrice=str(sl_limit_price),
                stopLimitTimeInForce=TIME_IN_FORCE_GTC
            )
            self.logger.info(f"OCO Order Placed: {symbol} Qty: {qty} TP: {tp_price} SL: {sl_price}")
            return order
        except Exception as e:
            self.logger.error(f"Error in OCO Sell: {e}")
            return None
