#!/usr/bin/env python3
"""
BOT DE TELEGRAM - WUAWURI CHK (Adaptado para Render)
"""

import re
import random
import time
import json
import sqlite3
import os
import subprocess
import shutil
import threading
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ============ CONFIGURACIÓN ============
# Usamos variables de entorno para el token (más seguro)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8909444338:AAGCyNDfa3HpxCFGwuqMR_I19pyopjOKLXg")
START_IMAGE = "https://i.imgur.com/ncIgmGy.jpeg"
OWNER_ID = 6073662581 
ADMIN_IDS = [6073662581] 

ultimo_gen = {}
ultima_dir = {}
NOMBRE_BOT = "Wuawuri Chk"

# --- SERVIDOR WEB PARA RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot funcionando correctamente", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ============ BASE DE DATOS ============
# (Todo tu código de base de datos se mantiene igual)
def init_db():
    conn = sqlite3.connect('bot_stats.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY, nombre TEXT, username TEXT, fecha_registro TEXT, es_vip INTEGER DEFAULT 0, esta_baneado INTEGER DEFAULT 0, crds_usadas INTEGER DEFAULT 0, fecha_expiracion TEXT DEFAULT 'N/A', creditos INTEGER DEFAULT 0, ultimo_diario TEXT DEFAULT 'N/A')''')
    c.execute('''CREATE TABLE IF NOT EXISTS lives_guardadas (id INTEGER PRIMARY KEY AUTOINCREMENT, tarjeta TEXT, usuario_id INTEGER, fecha TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rate_limit (usuario_id INTEGER, timestamp REAL)''')
    conn.commit(); conn.close()

def obtener_nombre():
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave = 'nombre_bot'"); res = c.fetchone(); conn.close()
    return res[0] if res else "Wuawuri Chk"

def guardar_nombre(nombre):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('nombre_bot', ?)", (nombre,)); conn.commit(); conn.close()

def es_owner(uid): return uid == OWNER_ID
def es_admin(uid): return uid in ADMIN_IDS or es_owner(uid)

def es_vip(uid):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT es_vip FROM usuarios WHERE id = ?", (uid,)); res = c.fetchone(); conn.close()
    return res and res[0] == 1

def esta_baneado(uid):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT esta_baneado FROM usuarios WHERE id = ?", (uid,)); res = c.fetchone(); conn.close()
    return res and res[0] == 1

def obtener_usuario(uid):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT id, nombre, username, es_vip, esta_baneado, crds_usadas, fecha_expiracion, creditos, ultimo_diario FROM usuarios WHERE id = ?", (uid,))
    res = c.fetchone(); conn.close(); return res

def registrar_usuario(uid, nombre, username):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT id FROM usuarios WHERE id = ?", (uid,))
    if not c.fetchone():
        exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO usuarios (id, nombre, username, fecha_registro, fecha_expiracion) VALUES (?, ?, ?, ?, ?)", (uid, nombre, username, datetime.now().isoformat(), exp))
        conn.commit()
    conn.close()

def cambiar_vip(uid, estado):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    if estado == 1:
        exp = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE usuarios SET es_vip = 1, fecha_expiracion = ? WHERE id = ?", (exp, uid))
    else: c.execute("UPDATE usuarios SET es_vip = 0 WHERE id = ?", (uid,))
    conn.commit(); conn.close()

def agregar_creditos(uid, cantidad):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("UPDATE usuarios SET creditos = creditos + ? WHERE id = ?", (cantidad, uid)); conn.commit(); conn.close()

def quitar_creditos(uid, cantidad):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("UPDATE usuarios SET creditos = creditos - ? WHERE id = ?", (cantidad, uid)); conn.commit(); conn.close()

def guardar_live(tarjeta, usuario_id):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("INSERT INTO lives_guardadas (tarjeta, usuario_id, fecha) VALUES (?, ?, ?)", (tarjeta, usuario_id, datetime.now().isoformat())); conn.commit(); conn.close()

def obtener_lives(usuario_id):
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT tarjeta FROM lives_guardadas WHERE usuario_id = ?", (usuario_id,)); res = c.fetchall(); conn.close(); return res

# ============ ANTI-SPAM ============
def check_rate_limit(usuario_id):
    if usuario_id == OWNER_ID: return True 
    ahora = time.time()
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("DELETE FROM rate_limit WHERE timestamp < ?", (ahora - 60,))
    c.execute("SELECT COUNT(*) FROM rate_limit WHERE usuario_id = ?", (usuario_id,))
    intentos = c.fetchone()[0]
    if intentos >= 3: conn.close(); return False 
    c.execute("INSERT INTO rate_limit (usuario_id, timestamp) VALUES (?, ?)", (usuario_id, ahora))
    conn.commit(); conn.close(); return True 

# ============ LÓGICA CC ============
def limpiar_numero(card): return re.sub(r'\D', '', card)
def luhn_check(card):
    card = re.sub(r'\D', '', card)
    if not card.isdigit() or len(card) < 13: return False
    total = 0
    for i, digit in enumerate(card[::-1]):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9: n -= 9
        total += n
    return total % 10 == 0
def detectar_tipo(card):
    card = re.sub(r'\D', '', card)
    if card.startswith('4'): return "VISA"
    if card.startswith(('51','52','53','54','55')): return "MASTERCARD"
    if card.startswith(('34','37')): return "AMEX"
    if card.startswith('6'): return "DISCOVER"
    return "DESCONOCIDO"

def generar_tarjetas(cant, bin_p, mes, año, cvv):
    res = []
    for _ in range(cant):
        m = mes.zfill(2) if mes and mes.isdigit() else str(random.randint(1, 12)).zfill(2)
        a = año if año and año.isdigit() else str(random.randint(25, 30))
        c_v = cvv.zfill(3) if cvv and cvv.lower() != 'rnd' and cvv.isdigit() else str(random.randint(100, 999))
        if 'x' in bin_p:
            n = bin_p
            for _ in range(n.count('x')): n = n.replace('x', str(random.randint(0, 9)), 1)
        else:
            n = bin_p + ''.join(str(random.randint(0, 9)) for _ in range(16 - len(bin_p))) if len(bin_p) < 16 else bin_p[:16]
        total = sum((int(d) * 2 - 9 if int(d)*2 > 9 else int(d)*2) if i%2==1 else int(d) for i,d in enumerate(n[::-1]))
        n = n[:-1] + str((10 - (total % 10)) % 10)
        res.append(f"{n}|{m}|{a}|{c_v}")
    return res

def get_rango(user_id, nombre):
    if es_owner(user_id): return f"👑 {nombre} » OWNER"
    if es_admin(user_id): return f"🛡️ {nombre} » ADMIN"
    if es_vip(user_id): return f"⭐ {nombre} » PREMIUM"
    return f"👤 {nombre} » FREE"

# (Aquí continúan todos tus comandos: dir_cmd, gen_cmd, start_cmd, etc. SIN CAMBIOS)
# ... [Copia y pega aquí el resto de tus funciones async: dir_cmd, ejecutar_generacion_dir, gen_cmd, start_cmd, cmds_cmd, me_cmd, daily_cmd, buyvip_cmd, stealth_cmd, setname_cmd, down_cmd, bin_cmd, check_gratis_cmd, mss1_cmd, mislives_cmd, owner_panel, admin_list_users, admin_toggle_vip, broadcast, button_handler, handle_text] ...

# ============ ARRANQUE ============
def main():
    init_db()
    global NOMBRE_BOT
    NOMBRE_BOT = obtener_nombre()
    
    # 1. Iniciar el servidor web en un hilo separado para Render
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # 2. Iniciar el bot de Telegram
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cmds", cmds_cmd))
    app.add_handler(CommandHandler("me", me_cmd))
    app.add_handler(CommandHandler("bin", bin_cmd))
    app.add_handler(CommandHandler("gen", gen_cmd))
    app.add_handler(CommandHandler("check_gratis", check_gratis_cmd))
    app.add_handler(CommandHandler("mss1", mss1_cmd))
    app.add_handler(CommandHandler("mass1", mss1_cmd))
    app.add_handler(CommandHandler("mislives", mislives_cmd))
    app.add_handler(CommandHandler("setname", setname_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("buyvip", buyvip_cmd))
    app.add_handler(CommandHandler("stealth", stealth_cmd))
    app.add_handler(CommandHandler("dir", dir_cmd))
    app.add_handler(CommandHandler("down", down_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    
    print("🌸 Bot Wuawuri Chk iniciado y escuchando en Render.")
    app.run_polling()

if __name__ == "__main__":
    main()
