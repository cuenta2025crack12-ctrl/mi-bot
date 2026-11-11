import os
import threading
from flask import Flask
import telebot

# 1. Configurar Flask (El mini servidor web para Render)
app = Flask(__name__)

@app.route('/')
def home():
    # Render entrará aquí para verificar que el bot está vivo
    return "Bot de Telegram funcionando 24/7", 200

# 2. Configurar el Bot
# Lee el token desde las variables de entorno (¡Más seguro!)
TOKEN = os.environ.get('TELEGRAM_TOKEN') 
bot = telebot.TeleBot(TOKEN)

# --- AQUÍ VA TU LÓGICA DEL BOT ---
# Por ejemplo:
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "¡Hola! Bienvenido al bot de cuentas.")

@bot.message_handler(commands=['reclamar'])
def reclamar_cuenta(message):
    # Tu lógica de base de datos aquí
    bot.reply_to(message, "Buscando una cuenta para ti...")
# ---------------------------------

# 3. Función para iniciar el bot en un hilo separado
def run_bot():
    print("Iniciando el bot de Telegram...")
    bot.infinity_polling()

# 4. Arrancar todo
if __name__ == "__main__":
    # Iniciamos el bot en un hilo paralelo para que no bloquee a Flask
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # Iniciamos el servidor web de Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
