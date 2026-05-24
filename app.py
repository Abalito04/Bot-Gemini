from flask import Flask, jsonify, render_template, request
import threading
import os
import json
from bot import TradingBot

# 1. Instanciar Flask antes que cualquier otra cosa
app = Flask(__name__)

# 2. Cargar configuración desde entorno (Railway las inyecta directamente)
API_KEY = os.getenv('BINANCE_API_KEY')
# Soportamos ambos nombres para evitar errores de configuración
API_SECRET = os.getenv('BINANCE_API_SECRET') or os.getenv('BINANCE_SECRET')
TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print("ERROR: API Keys no encontradas. Revisa BINANCE_API_KEY y BINANCE_SECRET en Railway.")

# 3. Instanciar el bot (sin llamadas de red en el constructor)
bot = TradingBot(API_KEY, API_SECRET)

def run_bot_background():
    """Ejecuta el bot en un hilo separado."""
    bot.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Retorna el estado actual del bot desde la memoria."""
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

# 4. Iniciar el hilo del bot de forma global para que corra bajo Gunicorn
bot_thread = threading.Thread(target=run_bot_background, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    # Este bloque solo se ejecuta localmente (python app.py)
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
