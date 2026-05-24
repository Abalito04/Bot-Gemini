from flask import Flask, jsonify, render_template, request
import threading
import os
import json
from bot import TradingBot
from dotenv import load_dotenv

# Cargar variables desde .env
load_dotenv()

app = Flask(__name__)

# Cargar configuración desde entorno
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

# Instanciar el bot
bot = TradingBot(API_KEY, API_SECRET)

def run_bot_background():
    """Ejecuta el bot en un hilo separado."""
    bot.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Retorna el estado actual del bot desde la memoria con logging."""
    # Log para ver qué tiene el bot en memoria
    # logger.info(f"Enviando estado: Balance={bot.state.get('balance_usdt')}, Precio={bot.state.get('last_price')}")
    return jsonify(bot.state)

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Inicia el bot."""
    bot.state['is_running'] = True
    bot.save_state()
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Detiene el bot."""
    bot.state['is_running'] = False
    bot.save_state()
    return jsonify({"status": "stopped"})

@app.route('/api/operaciones', methods=['GET'])
def get_operaciones():
    """Retorna el historial de operaciones desde la memoria."""
    return jsonify(bot.state.get('operaciones', []))

if __name__ == '__main__':
    # Iniciar el bot en un hilo separado para no bloquear Flask
    bot_thread = threading.Thread(target=run_bot_background, daemon=True)
    bot_thread.start()
    
    # Railway usa el puerto de la variable de entorno PORT
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
