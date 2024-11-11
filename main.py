import logging
import requests
import time
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY")
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY")

# Diccionario para almacenar los objetivos de precio de los usuarios
user_targets = {}

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        '¡Hola! Soy tu bot de seguimiento de Bitcoin.\n'
        'Usa /setprecio <precio> para establecer un objetivo de precio.\n'
        'Por ejemplo: /setprecio 30000'
    )

def set_precio(update: Update, context: CallbackContext):
    try:
        precio_objetivo = float(context.args[0])
        user_id = update.message.chat_id
        user_targets[user_id] = precio_objetivo
        update.message.reply_text(f'Objetivo de precio establecido en ${precio_objetivo}')
    except (IndexError, ValueError):
        update.message.reply_text('Uso correcto: /setprecio <precio>\nEjemplo: /setprecio 30000')

def get_bitcoin_price():
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': 'BTC',
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }
    response = requests.get(url, headers=headers, params=parameters)
    data = response.json()
    price = data['data']['BTC']['quote']['USD']['price']
    return price

def monitor_prices(context: CallbackContext):
    for user_id, target_price in user_targets.items():
        try:
            current_price = get_bitcoin_price()
            if current_price >= target_price:
                context.bot.send_message(
                    chat_id=user_id,
                    text=f'¡Alerta! Bitcoin ha alcanzado el precio de ${current_price:.2f}'
                )
                # Eliminar el objetivo una vez alcanzado
                del user_targets[user_id]
        except Exception as e:
            logger.error(f'Error al monitorear el precio para el usuario {user_id}: {e}')

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers de comandos
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("setprecio", set_precio, pass_args=True))

    # Configurar trabajo periódico para monitorear precios cada minuto
    job_queue = updater.job_queue
    job_queue.run_repeating(monitor_prices, interval=60, first=10)

    # Iniciar el bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
