import pandas as pd
import numpy as np

class Strategy:
    @staticmethod
    def calculate_rsi(data, period=14):
        """Calcula el RSI sin librerías externas pesadas."""
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_ema(data, period=200):
        """Calcula la Media Móvil Exponencial (EMA)."""
        return data['close'].ewm(span=period, adjust=False).mean()

    def check_signals(self, df, rsi_buy=42, rsi_sell=62):
        """
        Evalúa señales LONG/SHORT basadas en RSI dinámico y Filtro de EMA 200.
        """
        if df.empty or len(df) < 201:
            return None
        
        last_rsi = df['rsi'].iloc[-1]
        last_price = df['close'].iloc[-1]
        last_ema = df['ema200'].iloc[-1]
        
        # Filtro de Tendencia: Solo compramos si el precio está por encima de la EMA 200
        if last_rsi <= rsi_buy and last_price > last_ema:
            return 'BUY'
        elif last_rsi >= rsi_sell:
            return 'SELL'
        
        return None
