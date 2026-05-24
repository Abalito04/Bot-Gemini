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

    def check_signals(self, df):
        """
        Evalúa señales LONG/SHORT basadas en RSI y Filtro de EMA 200.
        LONG: RSI <= 42 Y Precio > EMA 200 (Tendencia alcista)
        SHORT (Exit): RSI >= 62
        """
        if df.empty or len(df) < 201: # Necesitamos al menos 200 velas para la EMA
            return None
        
        last_rsi = df['rsi'].iloc[-1]
        last_price = df['close'].iloc[-1]
        last_ema = df['ema200'].iloc[-1]
        
        # Filtro de Tendencia: Solo compramos si el precio está por encima de la EMA 200
        if last_rsi <= 42 and last_price > last_ema:
            return 'BUY'
        elif last_rsi >= 62:
            return 'SELL'
        
        return None
