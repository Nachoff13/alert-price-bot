import logging
import requests
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY")
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY")

# Diccionario para almacenar los objetivos de precio de los usuarios
user_targets = {}

def get_top_tokens():
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
    parameters = {
        'start': '1',
        'limit': '20',
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }
    
    try:
        response = requests.get(url, headers=headers, params=parameters)
        response.raise_for_status()  # Lanza una excepción para códigos de estado HTTP 4xx/5xx
        data = response.json()
        tokens = {crypto['symbol']: crypto['name'] for crypto in data['data']}
        return tokens
    except requests.exceptions.RequestException as e:
        logger.error('Error al obtener la lista de tokens: %s', e)
        return {}

async def start(update: Update, context: CallbackContext):
    tokens = get_top_tokens()
    keyboard = [[InlineKeyboardButton(name, callback_data=symbol)] for symbol, name in tokens.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Selecciona un token:', reply_markup=reply_markup)

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    token = query.data
    context.user_data['selected_token'] = token
    await query.edit_message_text(text=f"Seleccionaste {token}. Ahora, ingresa el precio objetivo usando /setprecio <precio>.")

async def set_precio(update: Update, context: CallbackContext):
    try:
        token = context.user_data.get('selected_token')
        if not token:
            await update.message.reply_text('Primero selecciona un token usando /start.')
            return
        precio_objetivo = float(context.args[0])
        user_id = update.message.chat_id
        if token not in get_top_tokens():
            await update.message.reply_text('Token no válido. Usa /start para ver la lista de tokens disponibles.')
            return
        if user_id not in user_targets:
            user_targets[user_id] = {}
        logger.info(f'Estableciendo objetivo de precio para el usuario {user_id}: {token} = {precio_objetivo}')
        user_targets[user_id][token] = precio_objetivo
        logger.info(f'Objetivo de precio establecido: {user_targets[user_id]}')
        await update.message.reply_text(f'Objetivo de precio para {token} establecido en ${precio_objetivo}')
    except (IndexError, ValueError):
        await update.message.reply_text('Uso correcto: /setprecio <precio>\nEjemplo: /setprecio 30000')

def get_token_price(token):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': token,
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }
    
    try:
        response = requests.get(url, headers=headers, params=parameters)
        response.raise_for_status()  # Lanza una excepción para códigos de estado HTTP 4xx/5xx
        data = response.json()
        
        # Verificar que la estructura de la respuesta sea la esperada
        if 'data' in data and token in data['data'] and 'quote' in data['data'][token] and 'USD' in data['data'][token]['quote']:
            price = data['data'][token]['quote']['USD']['price']
            return price
        else:
            logger.error('Estructura de respuesta inesperada: %s', data)
            return None
    except requests.exceptions.RequestException as e:
        logger.error('Error al obtener el precio de %s: %s', token, e)
        return None

async def monitor_prices(context: CallbackContext):
    for user_id, targets in user_targets.items():
        for token, target_price in targets.items():
            try:
                current_price = get_token_price(token)
                if current_price is not None and current_price >= target_price:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f'¡Alerta! {token} ha alcanzado el precio de ${current_price:.2f}'
                    )
                    # Eliminar el objetivo una vez alcanzado
                    del user_targets[user_id][token]
            except Exception as e:
                logger.error(f'Error al monitorear el precio de {token} para el usuario {user_id}: {e}')
            
async def main():
    # Crear la aplicación y pasar el token
    application = Application.builder().token(TELEGRAM_API_KEY).build()

    # Configurar JobQueue
    job_queue = application.job_queue

    # Agregar handlers de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setprecio", set_precio))
    application.add_handler(CallbackQueryHandler(button))

    # Configurar trabajo periódico para monitorear precios cada minuto
    job_queue.run_repeating(monitor_prices, interval=60, first=10)

    # Iniciar el bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == '__main__':
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(main())
    loop.run_forever()