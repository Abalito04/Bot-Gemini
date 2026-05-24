from flask import Flask, jsonify, render_template, request
import threading
import os
import json
from bot import TradingBot

# 1. Instanciar Flask antes que cualquier otra cosa
app = Flask(__name__)

# 2. Buscador exhaustivo de llaves (Cazador de variables)
def find_env_var(names):
    for name in names:
        val = os.getenv(name)
        if val: return val
    # Si no lo encuentra, busca cualquier variable que contenga la palabra clave
    for k, v in os.environ.items():
        for name in names:
            if name in k.upper(): return v
    return None

API_KEY = find_env_var(['BINANCE_API_KEY', 'BINANCE_KEY', 'API_KEY'])
API_SECRET = find_env_var(['BINANCE_API_SECRET', 'BINANCE_SECRET', 'SECRET_KEY', 'API_SECRET'])
TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

if not API_KEY or not API_SECRET:
    print(f"CRÍTICO: No se encontraron llaves. Variables disponibles: {list(os.environ.keys())}")

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

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Obtiene o actualiza la configuración de trading."""
    if request.method == 'POST':
        data = request.json
        # Actualizamos solo los campos permitidos
        if 'monto_operacion' in data: bot.state['monto_operacion'] = float(data['monto_operacion'])
        if 'tp_pct' in data: bot.state['tp_pct'] = float(data['tp_pct'])
        if 'sl_pct' in data: bot.state['sl_pct'] = float(data['sl_pct'])
        bot.save_state()
        return jsonify({"status": "updated", "config": {
            "monto": bot.state.get('monto_operacion'),
            "tp": bot.state.get('tp_pct'),
            "sl": bot.state.get('sl_pct')
        }})
    return jsonify({
        "monto": bot.state.get('monto_operacion', 100.0),
        "tp": bot.state.get('tp_pct', 1.2),
        "sl": bot.state.get('sl_pct', 0.8)
    })

# 4. Iniciar el hilo del bot de forma global para que corra bajo Gunicorn
bot_thread = threading.Thread(target=run_bot_background, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    # Este bloque solo se ejecuta localmente (python app.py)
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
