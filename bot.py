#!/usr/bin/env python3
"""
BOT DE TELEGRAM - SUKUNA CHK
Versión 23.0 - Líneas estilizadas con <code> (Color integrado)
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
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ============ CONFIGURACIÓN ============
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8909444338:AAGCyNDfa3HpxCFGwuqMR_I19pyopjOKLXg")
START_IMAGE = "https://i.imgur.com/RHvnM05.jpg"
OWNER_ID = 6073662581 
ADMIN_IDS = [6073662581] 

ultimo_gen = {}
ultima_dir = {}
NOMBRE_BOT = "Sukuna Chk"

# ============ SERVIDOR WEB PARA RENDER ============
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot funcionando correctamente", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ============ BASE DE DATOS ============
def init_db():
    conn = sqlite3.connect('bot_stats.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY, nombre TEXT, username TEXT,
                    fecha_registro TEXT, es_vip INTEGER DEFAULT 0, esta_baneado INTEGER DEFAULT 0,
                    crds_usadas INTEGER DEFAULT 0, fecha_expiracion TEXT DEFAULT 'N/A',
                    creditos INTEGER DEFAULT 0, ultimo_diario TEXT DEFAULT 'N/A')''')
    c.execute('''CREATE TABLE IF NOT EXISTS lives_guardadas (id INTEGER PRIMARY KEY AUTOINCREMENT, tarjeta TEXT, usuario_id INTEGER, fecha TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rate_limit (usuario_id INTEGER, timestamp REAL)''')
    conn.commit(); conn.close()

def obtener_nombre():
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave = 'nombre_bot'"); res = c.fetchone(); conn.close()
    return res[0] if res else "Sukuna Chk"

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

# ============ GENERADOR DE DIRECCIONES ============
async def dir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_rate_limit(user.id): return await update.message.reply_text("⏳ Ve más despacio.")
    
    if not context.args:
        menu = f"⚡ <b>{NOMBRE_BOT} | Address Generator</b>\n➖➖➖➖➖➖➖➖➖➖\n➡️ Use: <code>/dir [country_code]</code>\n➖➖➖➖➖➖➖➖➖➖\nAvailable Countries:\n🇪🇸 ES │ 🇹🇷 TR │ 🇺🇸 US │ 🇳🇱 NL\n🇲🇽 MX │ 🇧🇪 BE │ 🇨🇴 CO │ 🇸🇪 SE\n🇦🇷 AR │ 🇳🇴 NO │ 🇧🇷 BR │ 🇫🇮 FI\n🇫🇷 FR │ 🇩🇰 DK │ 🇩🇪 DE │ 🇵🇱 PL\n🇮🇹 IT │ 🇬🇷 GR │ 🇬🇧 UK │ 🇵🇹 PT\n🇨🇦 CA │ 🇨🇭 CH │ 🇨🇱 CL │ 🇦🇹 AT\n🇵🇪 PE │ 🇭🇺 HU │ 🇻🇪 VE │ 🇨🇿 CZ\n🇪🇨 EC │ 🇷🇴 RO │ 🇸🇻 SV │ 🇬🇹 GT\n🇨🇷 CR │ 🇵🇦 PA │ 🇩🇴 DO │ 🇧🇴 BO\n🇵🇾 PY │ 🇺🇾 UY"
        return await update.message.reply_text(menu, parse_mode='HTML')
    
    codigo = context.args[0].lower()
    ultima_dir[user.id] = codigo
    msg = await update.message.reply_text("⏳ Generando dirección...")
    await ejecutar_generacion_dir(update, context, user, codigo, msg)

async def ejecutar_generacion_dir(update: Update, context: ContextTypes.DEFAULT_TYPE, user, codigo, msg):
    locales = {'es': 'es_ES', 'tr': 'tr_TR', 'us': 'en_US', 'nl': 'nl_NL', 'mx': 'es_MX', 'be': 'nl_BE', 'co': 'es_CO', 'se': 'sv_SE', 'ar': 'es_AR', 'no': 'no_NO', 'br': 'pt_BR', 'fi': 'fi_FI', 'fr': 'fr_FR', 'dk': 'dk_DK', 'de': 'de_DE', 'pl': 'pl_PL', 'it': 'it_IT', 'gr': 'el_GR', 'uk': 'en_GB', 'pt': 'pt_PT', 'ca': 'en_CA', 'ch': 'de_CH', 'cl': 'es_CL', 'at': 'de_AT', 'pe': 'es_PE', 'hu': 'hu_HU', 've': 'es_VE', 'cz': 'cs_CZ', 'ec': 'es_EC', 'ro': 'ro_RO', 'sv': 'es_SV', 'gt': 'es_GT', 'cr': 'es_CR', 'pa': 'es_PA', 'do': 'es_DO', 'bo': 'es_BO', 'py': 'es_PY', 'uy': 'es_UY'}
    
    if codigo not in locales:
        return await msg.edit_text("❌ Código no soportado. Usa /dir para ver la lista.")
    
    try:
        from faker import Faker
        try:
            fake = Faker(locales[codigo]); nombre_pais = fake.current_country()
        except:
            fake = Faker('es_ES'); nombre_pais = codigo.upper()

        direccion = fake.address().replace('\n', ', ')
        calle = fake.street_address(); ciudad = fake.city()
        try: estado = fake.state()
        except: estado = fake.city()
        telefono = fake.phone_number(); cp = fake.postcode()
        
        # LÍNEAS CON <code> PARA HEREDAR EL COLOR GRIS OSCURO
        texto = (
            f"<a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
            f"<code>.dir {codigo}</code>\n"
            f"⚡ <b>{NOMBRE_BOT} | Address Generator</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"➤ <b>Country:</b> {nombre_pais}\n➤ <b>Full Address:</b> {direccion}\n"
            f"<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"➤ <b>Street:</b> <code>{calle}</code>\n➤ <b>City:</b> <code>{ciudad}</code>\n"
            f"➤ <b>State:</b> <code>{estado}</code>\n➤ <b>Phone:</b> <code>{telefono}</code>\n"
            f"➤ <b>ZIP Code:</b> <code>{cp}</code>\n"
            f"<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n〰️ <b>Req By:</b> {get_rango(user.id, user.first_name)}\n"
            f"<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 <b>Bot Version:</b> 1.3 ⛈"
        )
        kb = [[InlineKeyboardButton("🔄 Re-Gen Address", callback_data='btn_regen_dir', api_kwargs={"style": "primary"}), InlineKeyboardButton("!! Updates ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"})]]
        
        if msg: await msg.edit_text(texto, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        else: await update.callback_query.message.edit_text(texto, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
    except Exception as e:
        error_msg = f"❌ Error al generar dirección: {e}"
        if msg: await msg.edit_text(error_msg)
        else: await update.callback_query.message.reply_text(error_msg)

# ============ GENERADOR MODO TURBO ============
async def gen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_rate_limit(user.id): return await update.message.reply_text("⏳ Ve más despacio.")
    if not context.args: return await update.message.reply_text("❌ Uso: `.gen BIN|MES|AÑO|CVV`")
    
    arg_completo = " ".join(context.args).replace('/', '|')
    partes = arg_completo.split('|')
    cantidad = 10
    if len(partes) >= 5 and partes[-1].isdigit():
        cantidad = int(partes[-1])
        if cantidad > 50: cantidad = 50
        partes = partes[:-1]
    arg = "|".join(partes)
    ultimo_gen[user.id] = {"arg": arg, "cantidad": cantidad}
    
    info_bin = {"scheme": "visa", "type": "debit", "brand": "classic", "bank": {"name": "Banco Agricola S.A."}, "country": {"name": "El Salvador", "emoji": "🇸🇻"}} if limpiar_numero(partes[0])[:6] == "411841" else None
    tarjetas = generar_tarjetas(cantidad, partes[0], partes[1] if len(partes)>1 else None, partes[2] if len(partes)>2 else None, partes[3] if len(partes)>3 else None)
    
    brand = info_bin.get('scheme', 'N/A').upper() if info_bin else 'N/A'
    banco = info_bin.get('bank', {}).get('name', 'N/A').upper() if info_bin else 'N/A'
    pais = info_bin.get('country', {}).get('name', 'N/A').upper() if info_bin else 'N/A'
    rango = "👤 Anónimo » VIP" if context.user_data.get('stealth') else get_rango(user.id, user.first_name)
    nombre_mostrar = "Anónimo" if context.user_data.get('stealth') else user.first_name

    # LÍNEAS CON <code>
    texto = f"<a href='tg://user?id={user.id}'>{nombre_mostrar}</a>\n<code>.gen {arg}</code>\n⚡ <b>{NOMBRE_BOT} | CC Generator</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
    for t in tarjetas: texto += f"<code>{t}</code>\n"
    texto += f"<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n➤ <b>Bin:</b> {limpiar_numero(partes[0])[:6]}\n➤ <b>Info:</b> {brand}\n➤ <b>Issuer:</b> {banco}\n➤ <b>Country:</b> {pais}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n〰️ <b>Req By:</b> {rango}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 <b>Bot Version:</b> 1.3 ⛈"
    kb = [[InlineKeyboardButton("⚙️ Re-Gen", callback_data='btn_regen', api_kwargs={"style": "primary"}), InlineKeyboardButton("!! Updates ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"})]]
    await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# ============ COMANDOS BÁSICOS ============
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    registrar_usuario(user.id, user.first_name, f"@{user.username}" if user.username else "N/A")
    if esta_baneado(user.id): return await update.message.reply_text("🚫 Estás baneado.")
    rango = "⭐ VIP" if es_vip(user.id) else "👤 Normal"
    if es_owner(user.id): rango = "👑 Fundador"
    elif es_admin(user.id): rango = "🛡️ Admin"
    caption = f"🌸 <b>SUKUNA CHK</b> 🌸\n║  ✨ Nuevo Proyecto ✨            ║\n╚══════════════════════════════════════╝\n\n👤 <b>Usuario:</b> {user.first_name}\n🆔 <b>ID:</b> <code>{user.id}</code>\n🏆 <b>Rango:</b> {rango}\n\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n👉 Usa /cmds para abrir el panel interactivo."
    keyboard = [[InlineKeyboardButton("📰 References ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"}), InlineKeyboardButton("📈 Updates ↗", url="https://t.me/tu_canal", api_kwargs={"style": "success"})]]
    await update.message.reply_photo(photo=START_IMAGE, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def cmds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if esta_baneado(user.id): return await update.message.reply_text("🚫 Estás baneado.")
    caption = f"🦾 <b>{NOMBRE_BOT} | Command Panel</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n⚪ Gateways: 4 | Tools: 14\n⚪ Api Status: Online ✅\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 Bot Version: 1.3 ⚡️"
    keyboard = [[InlineKeyboardButton("⚡ Gateways", callback_data='menu_gateways', api_kwargs={"style": "primary"}), InlineKeyboardButton("⚙️ Tools", callback_data='menu_tools', api_kwargs={"style": "primary"})], [InlineKeyboardButton("📰 References ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"}), InlineKeyboardButton("🆓 Free Group ↗", url="https://t.me/tu_grupo", api_kwargs={"style": "success"})], [InlineKeyboardButton("📈 Updates ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"}), InlineKeyboardButton("💸 Buy Kaori ↗", url="https://t.me/tu_contacto", api_kwargs={"style": "success"})]]
    if es_admin(user.id): keyboard.append([InlineKeyboardButton("👑 Panel de Control", callback_data='owner_panel', api_kwargs={"style": "danger"})])
    await update.message.reply_photo(photo=START_IMAGE, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    datos = obtener_usuario(user.id) or (user.id, user.first_name, "N/A", 0, 0, 0, "N/A", 0, "N/A")
    uid, nombre, username, es_vip_val, baneado, crds, expiracion, creditos, ultimo_diario = datos
    status = "❌ Inactiva" if not es_vip_val and not es_admin(uid) else "✅ Activa"
    rol = "FUNDADOR" if es_owner(uid) else "ADMIN" if es_admin(uid) else "USER"
    # LÍNEAS CON <code>
    texto = f"🦾 <b>{NOMBRE_BOT} | User Info</b> ⛈\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔘 <b>User:</b> {nombre} (<code>{uid}</code>)\n🔘 <b>Username:</b> {username}\n🔘 <b>Plan:</b> PREMIUM | Role: {rol}\n🔘 <b>Status:</b> {'BANNED 🚫' if baneado else 'ACTIVE 🟢'}\n🔘 <b>Crds:</b> {crds} | <b>Cookies:</b> 0\n🔘 <b>Expiration:</b> {expiracion}\n🔘 <b>Créditos:</b> {creditos}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 <b>Bot Version:</b> 1.3 ⛈"
    await update.message.reply_text(texto, parse_mode='HTML')

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    datos = obtener_usuario(user.id)
    if not datos: return await update.message.reply_text("❌ Usa /start primero.")
    if datos[8] == datetime.now().strftime("%Y-%m-%d"): return await update.message.reply_text("⏳ Ya reclamaste tus créditos hoy.")
    agregar_creditos(user.id, 10); conn = sqlite3.connect('bot_stats.db'); c = conn.cursor(); c.execute("UPDATE usuarios SET ultimo_diario = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d"), user.id)); conn.commit(); conn.close()
    await update.message.reply_text("✅ Has reclamado **10 créditos**.")

async def buyvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    datos = obtener_usuario(user.id)
    if datos[7] < 100: return await update.message.reply_text(f"❌ Necesitas 100 créditos. Tienes {datos[7]}.")
    quitar_creditos(user.id, 100); cambiar_vip(user.id, 1)
    await update.message.reply_text("👑 ¡Felicidades! Has comprado VIP por 1 día.")

async def stealth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not es_admin(user.id): return await update.message.reply_text("❌ Solo administradores.")
    context.user_data['stealth'] = not context.user_data.get('stealth', False)
    await update.message.reply_text("🕵️ Modo Incógnito " + ("ACTIVADO" if context.user_data['stealth'] else "DESACTIVADO"))

async def setname_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global NOMBRE_BOT
    if not es_admin(update.effective_user.id): return
    if not context.args: return await update.message.reply_text(f"ℹ️ Nombre actual: {NOMBRE_BOT}")
    NOMBRE_BOT = " ".join(context.args); guardar_nombre(NOMBRE_BOT)
    await update.message.reply_text(f"✅ Nombre cambiado a: {NOMBRE_BOT}")

# ============ DESCARGADOR INTELIGENTE CON AUDIO Y CFR ============
async def down_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args: return await update.message.reply_text("❌ Uso: `.down <enlace>`")
    
    url = context.args[0]
    msg = await update.message.reply_text("⏳ Analizando enlace, extrayendo datos y descargando...")
    timestamp = int(time.time())
    
    try:
        if "tiktok.com" in url and ("/photo/" in url or "slideshow" in url):
            carpeta_salida = f"fotos_{user.id}_{timestamp}"
            comando = ["gallery-dl", "--dest", carpeta_salida, "--range", "1-10", url]
            subprocess.run(comando, check=True, capture_output=True, timeout=120)
            
            titulo = "Fotos de TikTok"
            try:
                meta_json = subprocess.run(["yt-dlp", "--dump-json", "--no-download", url], capture_output=True, text=True, timeout=30)
                if meta_json.returncode == 0:
                    data = json.loads(meta_json.stdout)
                    titulo = data.get('description', data.get('title', 'Fotos de TikTok'))
                    if len(titulo) > 200: titulo = titulo[:200] + "..."
            except: pass

            fotos_enviadas = 0
            for root, dirs, files in os.walk(carpeta_salida):
                for file in files:
                    if file.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        ruta_foto = os.path.join(root, file)
                        caption_foto = f"🖼️ <b>{titulo}</b>\n\n📸 Foto {fotos_enviadas+1}" if fotos_enviadas == 0 else f"📸 Foto {fotos_enviadas+1}"
                        await update.message.reply_photo(photo=open(ruta_foto, 'rb'), caption=caption_foto, parse_mode='HTML')
                        fotos_enviadas += 1
                        if fotos_enviadas >= 10: break
                if fotos_enviadas >= 10: break
            
            shutil.rmtree(carpeta_salida, ignore_errors=True)
            if fotos_enviadas > 0: await msg.delete()
            else: await msg.edit_text("❌ No se encontraron fotos en ese enlace.")
            
        else:
            archivo_salida = f"video_{user.id}_{timestamp}.mp4"
            archivo_audio = f"audio_{user.id}_{timestamp}.mp3"
            
            titulo = "Video de TikTok"
            descripcion = ""
            try:
                meta_json = subprocess.run(["yt-dlp", "--dump-json", "--no-download", url], capture_output=True, text=True, timeout=30)
                if meta_json.returncode == 0:
                    data = json.loads(meta_json.stdout)
                    titulo = data.get('title', 'Video de TikTok')
                    descripcion = data.get('description', '')
                    if len(descripcion) > 500: descripcion = descripcion[:500] + "..."
            except Exception as e: print(f"No se pudieron extraer metadatos: {e}")

            comando = ["yt-dlp", "-f", "best", "--no-warnings", "-o", archivo_salida, url]
            subprocess.run(comando, check=True, capture_output=True, timeout=120)
            
            if os.path.exists(archivo_salida):
                archivo_arreglado = f"fixed_{archivo_salida}"
                comando_ffmpeg = ["ffmpeg", "-i", archivo_salida, "-vf", "fps=30", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", archivo_arreglado]
                
                try:
                    subprocess.run(comando_ffmpeg, check=True, capture_output=True, timeout=60)
                    os.remove(archivo_salida); archivo_salida = archivo_arreglado
                except Exception as e: print(f"No se pudo convertir a CFR: {e}")

                comando_extraer_audio = ["ffmpeg", "-i", archivo_salida, "-q:a", "0", "-map", "a", archivo_audio]
                try: subprocess.run(comando_extraer_audio, check=True, capture_output=True, timeout=60)
                except Exception as e: print(f"No se pudo extraer el audio: {e}")

                caption_final = f"🎬 <b>{titulo}</b>"
                if descripcion: caption_final += f"\n\n📝 {descripcion}"
                caption_final += f"\n\n〰️ Req By: {user.first_name}"
                
                await update.message.reply_video(video=open(archivo_salida, 'rb'), caption=caption_final, parse_mode='HTML')
                
                if os.path.exists(archivo_audio):
                    await update.message.reply_audio(audio=open(archivo_audio, 'rb'), caption=f"🎵 Audio extraído: {titulo[:50]}...")
                    os.remove(archivo_audio)
                
                os.remove(archivo_salida); await msg.delete()
            else: await msg.edit_text("❌ No se pudo encontrar el archivo de video.")
                
    except subprocess.TimeoutExpired: await msg.edit_text("❌ El video es muy grande o la conexión es lenta.")
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

# ============ COMANDOS RESTAURADOS ============
async def bin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args: return await update.message.reply_text("❌ Uso: `.bin 411841...`")
    bin_num = limpiar_numero(context.args[0])[:6]
    info = {"scheme": "visa", "type": "debit", "brand": "classic", "bank": {"name": "Banco Agricola S.A."}, "country": {"name": "El Salvador", "emoji": "🇸🇻"}} if bin_num == "411841" else None
    brand = info.get('scheme', 'N/A').upper() if info else 'N/A'
    tipo = info.get('type', 'N/A').upper() if info else 'N/A'
    banco = info.get('bank', {}).get('name', 'N/A').upper() if info else 'N/A'
    pais = info.get('country', {}).get('name', 'N/A').upper() if info else 'N/A'
    bandera = info.get('country', {}).get('emoji', '🏳️') if info else '🏳️'
    # LÍNEAS CON <code>
    texto = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>\n<code>.bin {bin_num}</code>\n⚡ <b>{NOMBRE_BOT} | BIN Lookup</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n➤ <b>BIN:</b> {bin_num}\n➤ <b>Info:</b> {brand} - {tipo}\n➤ <b>Issuer:</b> {banco}\n➤ <b>Country:</b> {pais} {bandera}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n〰️ <b>Req By:</b> {get_rango(user.id, user.first_name)}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 <b>Bot Version:</b> 1.3 ⛈"
    await update.message.reply_text(texto, parse_mode='HTML')

async def check_gratis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or len(context.args[0].split('|')) != 4: return await update.message.reply_text("❌ Uso: `.check_gratis NUM|MES|AÑO|CVV`")
    p = context.args[0].split('|'); num = limpiar_numero(p[0])
    status = "✅ VÁLIDA" if luhn_check(num) else "❌ INVÁLIDA"
    # LÍNEAS CON <code>
    texto = f"🦾 <b>{NOMBRE_BOT} | Validación</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n➤ <b>Número:</b> <code>{p[0]}</code>\n➤ <b>Resultado:</b> {status}\n➤ <b>Tipo:</b> {detectar_tipo(num)}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>"
    await update.message.reply_text(texto, parse_mode='HTML')

async def mss1_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_rate_limit(user.id): return await update.message.reply_text("⏳ Límite alcanzado.")
    tarjetas = []
    if update.message.reply_to_message:
        texto = update.message.reply_to_message.text or ""
        tarjetas.extend(re.findall(r'(\d{15,16}\|\d{1,2}\|\d{2,4}\|\d{3,4})', texto))
    if context.args:
        tarjetas.extend(re.findall(r'(\d{15,16}\|\d{1,2}\|\d{2,4}\|\d{3,4})', " ".join(context.args)))
    if not tarjetas: return await update.message.reply_text("❌ Responde a un mensaje o escribe tarjetas.")
    tarjetas = list(set(tarjetas))[:50]
    msg = await update.message.reply_text(f"⏳ Verificando {len(tarjetas)}...")
    lives = [t for t in tarjetas if luhn_check(t.split('|')[0])]
    for l in lives: guardar_live(l, user.id)
    # LÍNEAS CON <code>
    texto = f"🦾 <b>{NOMBRE_BOT} | Masivo</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n✅ <b>LIVES ({len(lives)}):</b>\n"
    for l in lives: texto += f"`{l}`\n"
    texto += f"\n❌ <b>DEAD:</b> {len(tarjetas)-len(lives)}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>"
    await msg.edit_text(texto, parse_mode='HTML')

async def mislives_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lives = obtener_lives(user.id)
    if not lives: return await update.message.reply_text("❌ No hay LIVES guardadas.")
    archivo = f"lives_{user.id}.txt"
    with open(archivo, "w") as f:
        for l in lives: f.write(f"{l[0]}\n")
    await update.message.reply_document(document=open(archivo, 'rb'), caption=f"✅ Tus {len(lives)} LIVES.")
    os.remove(archivo)

# ============ PANEL DE ADMINISTRACIÓN ============
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if not es_admin(update.effective_user.id): return await query.answer("❌ No permisos.", show_alert=True)
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor(); c.execute("SELECT COUNT(*) FROM usuarios"); total = c.fetchone()[0]; c.execute("SELECT COUNT(*) FROM usuarios WHERE es_vip=1"); vips = c.fetchone()[0]; conn.close()
    # LÍNEAS CON <code>
    caption = f"👑 <b>{NOMBRE_BOT} | Fundador Panel</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n👥 Usuarios: <b>{total}</b>\n⭐ VIPs: <b>{vips}</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>"
    keyboard = [
        [InlineKeyboardButton("👥 Gestionar Usuarios", callback_data='admin_users_0', api_kwargs={"style": "primary"})],
        [InlineKeyboardButton("📢 Enviar Mensaje Global (Broadcast)", callback_data='admin_broadcast', api_kwargs={"style": "success"})],
        [InlineKeyboardButton("🚫 Cerrar Panel", callback_data='btn_back_main', api_kwargs={"style": "danger"})]
    ]
    try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except: await query.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if not es_admin(update.effective_user.id): return
    page = int(query.data.split('_')[-1]); limit = 5; offset = page * limit
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor(); c.execute("SELECT id, nombre, es_vip FROM usuarios LIMIT ? OFFSET ?", (limit, offset)); usuarios = c.fetchall(); c.execute("SELECT COUNT(*) FROM usuarios"); total = c.fetchone()[0]; conn.close()
    # LÍNEAS CON <code>
    caption = f"👥 <b>Usuarios</b> (Pág {page+1})\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"; keyboard = []
    for u_id, nombre, vip in usuarios:
        caption += f"🆔 <code>{u_id}</code> | {nombre} | {'⭐' if vip else '👤'}\n"
        keyboard.append([InlineKeyboardButton(f"{'❌ Quitar' if vip else '⭐ Dar'} VIP", callback_data=f"admin_{'unvip' if vip else 'setvip'}_{u_id}", api_kwargs={"style": "danger" if vip else "success"})])
    
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f'admin_users_{page-1}', api_kwargs={"style": "primary"}))
    if offset + limit < total: nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f'admin_users_{page+1}', api_kwargs={"style": "primary"}))
    if nav_buttons: keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data='owner_panel', api_kwargs={"style": "danger"})])
    try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except: pass

async def admin_toggle_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer("✅ Hecho")
    if not es_admin(update.effective_user.id): return
    data = query.data.split('_'); cambiar_vip(int(data[2]), 1 if data[1] == 'setvip' else 0)
    await admin_list_users(update, context)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id) or not context.args: 
        return await update.message.reply_text("❌ Uso: `/broadcast <mensaje>`")
    
    msg = ' '.join(context.args)
    msg_espera = await update.message.reply_text("⏳ Enviando mensajes...")
    
    conn = sqlite3.connect('bot_stats.db'); c = conn.cursor(); c.execute("SELECT id FROM usuarios"); us = c.fetchall(); conn.close()
    
    exitos = 0
    fallos = 0
    for (uid,) in us:
        try: 
            await context.bot.send_message(uid, f"📢 <b>ADMIN:</b>\n\n{msg}", parse_mode='HTML')
            exitos += 1
            await asyncio.sleep(0.05) 
        except: 
            fallos += 1
            
    await msg_espera.edit_text(f"✅ **Broadcast finalizado.**\n\n📬 Enviados: {exitos}\n❌ Fallidos: {fallos}")

# ============ MANEJADOR DE BOTONES ============
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user = update.effective_user
    
    if query.data == 'btn_regen_dir':
        codigo = ultima_dir.get(user.id)
        if not codigo: return await query.message.reply_text("❌ Usa .dir primero.")
        await ejecutar_generacion_dir(update, context, user, codigo, None)
    elif query.data == 'btn_regen':
        datos = ultimo_gen.get(user.id)
        if not datos: return await query.message.reply_text("❌ Usa .gen primero.")
        partes = datos["arg"].split('|')
        tarjetas = generar_tarjetas(datos["cantidad"], partes[0], partes[1] if len(partes)>1 else None, partes[2] if len(partes)>2 else None, partes[3] if len(partes)>3 else None)
        info_bin = {"scheme": "visa", "type": "debit", "brand": "classic", "bank": {"name": "Banco Agricola S.A."}, "country": {"name": "El Salvador", "emoji": "🇸🇻"}} if limpiar_numero(partes[0])[:6] == "411841" else None
        # LÍNEAS CON <code>
        texto = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>\n<code>.gen {datos['arg']}</code>\n⚡ <b>{NOMBRE_BOT} | CC Generator</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        for t in tarjetas: texto += f"<code>{t}</code>\n"
        texto += f"<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n➤ <b>Bin:</b> {limpiar_numero(partes[0])[:6]}\n➤ <b>Info:</b> {info_bin['scheme'].upper() if info_bin else 'N/A'}\n➤ <b>Issuer:</b> {info_bin['bank']['name'].upper() if info_bin else 'N/A'}\n➤ <b>Country:</b> {info_bin['country']['name'].upper() if info_bin else 'N/A'}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n〰️ <b>Req By:</b> {get_rango(user.id, user.first_name)}\n<code>━━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 <b>Bot Version:</b> 1.3 ⛈"
        try: await query.message.edit_text(texto, reply_markup=query.message.reply_markup, parse_mode='HTML')
        except: pass
        
    elif query.data == 'owner_panel': await owner_panel(update, context)
    elif query.data == 'admin_broadcast':
        texto_instruccion = (
            "📢 <b>ENVIAR MENSAJE GLOBAL</b>\n\n"
            "Para enviar un mensaje a todos los usuarios, usa el siguiente comando en el chat:\n\n"
            "<code>/broadcast Tu mensaje aquí</code>\n\n"
            "⚠️ <i>Nota: El mensaje se enviará a todos los usuarios que hayan usado /start.</i>"
        )
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='owner_panel', api_kwargs={"style": "danger"})]]
        try: await query.message.edit_caption(caption=texto_instruccion, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass
    elif query.data.startswith('admin_users_'): await admin_list_users(update, context)
    elif query.data.startswith('admin_setvip_') or query.data.startswith('admin_unvip_'): await admin_toggle_vip(update, context)
    
    # ============ MENÚ GATEWAYS ============
    elif query.data == 'menu_gateways':
        # LÍNEAS CON <code>
        caption = f"🦾 <b>{NOMBRE_BOT} | Gateways</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n🔘 Active: 4 🟩\n🔘 Inactive: 0 ❌\n🔘 Maintenance: 0 ⚠️\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n☁️ Bot Version: 1.3 ⛈"
        keyboard = [
            [InlineKeyboardButton("🔘 Auth", callback_data='gw_auth', api_kwargs={"style": "primary"}), InlineKeyboardButton("🔘 Charge", callback_data='gw_charge', api_kwargs={"style": "primary"})], 
            [InlineKeyboardButton("🆓 Free Gate", callback_data='gw_free', api_kwargs={"style": "success"})], 
            [InlineKeyboardButton("🚫 Back", callback_data='btn_back_main', api_kwargs={"style": "danger"})]
        ]
        try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass
        
    # ============ PANEL AUTH CON COMANDOS ============
    elif query.data == 'gw_auth':
        # LÍNEAS CON <code>
        caption = (
            f"🦾 <b>{NOMBRE_BOT} | Auth</b> 🦾 4/4\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>Braintree</b> | ON ✅ | Premium\n"
            "   ➤ <code>.check_braintree 12345678xxx|MM|YY|CVV</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>Stripe</b> | ON ✅ | Free\n"
            "   ➤ <code>.check_stripe 12345678xxx|MM|YY|CVV</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>Free Gate</b> | ON ✅ | Free\n"
            "   ➤ <code>.check_gratis 12345678xxx|MM|YY|CVV</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>Massive Gate</b> | ON ✅ | Premium\n"
            "   ➤ <code>/mass1 1234 5678 9012...</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "☁️ Bot Version: 1.3 ⛈"
        )
        keyboard = [
            [InlineKeyboardButton("🚫 Back", callback_data='menu_gateways', api_kwargs={"style": "danger"})]
        ]
        try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass
        
    # ============ PANEL CHARGE CON COMANDOS ============
    elif query.data == 'gw_charge':
        # LÍNEAS CON <code>
        caption = (
            f"🦾 <b>{NOMBRE_BOT} | Charge</b> 🦾 1/1\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>Stripe $1</b> | ON ✅ | Premium\n"
            "   ➤ <code>.check_stripe 12345678xxx|MM|YY|CVV</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "☁️ Bot Version: 1.3 ⛈"
        )
        keyboard = [[InlineKeyboardButton("🚫 Back", callback_data='menu_gateways', api_kwargs={"style": "danger"})]]
        try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass
        
    # ============ PANEL FREE CON COMANDOS ============
    elif query.data == 'gw_free':
        # LÍNEAS CON <code>
        caption = (
            f"🦾 <b>{NOMBRE_BOT} | Free Gate</b> 🦾 1/1\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "🔘 <b>DevTools Luhn</b> | ON ✅ | Free\n"
            "   ➤ <code>.check_gratis 12345678xxx|MM|YY|CVV</code>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "☁️ Bot Version: 1.3 ⛈"
        )
        keyboard = [[InlineKeyboardButton("🚫 Back", callback_data='menu_gateways', api_kwargs={"style": "danger"})]]
        try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass

    # ============ PANEL PRINCIPAL ============
    elif query.data == 'btn_back_main':
        # LÍNEAS CON <code>
        caption = f"🦾 <b>{NOMBRE_BOT} | Command Panel</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n⚪ Gateways: 4 | Tools: 14\n⚪ Api Status: Online ✅\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n🔥 Bot Version: 1.3 ⚡️"
        keyboard = [[InlineKeyboardButton("⚡ Gateways", callback_data='menu_gateways', api_kwargs={"style": "primary"}), InlineKeyboardButton("⚙️ Tools", callback_data='menu_tools', api_kwargs={"style": "primary"})], [InlineKeyboardButton("📈 Updates ↗", url="https://t.me/tu_canal", api_kwargs={"style": "danger"})]]
        if es_admin(user.id): keyboard.append([InlineKeyboardButton("👑 Panel de Control", callback_data='owner_panel', api_kwargs={"style": "danger"})])
        try: await query.message.edit_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except: pass
    elif query.data == 'menu_tools':
        # LÍNEAS CON <code>
        tools_text = f"⚙️ <b>{NOMBRE_BOT} | Tools</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n1️⃣ `/gen` - Generar Tarjetas\n2️⃣ `/bin` - Consultar BIN\n3️⃣ `/me` - Ver tu Perfil\n4️⃣ `/check_gratis` - Validación Luhn\n5️⃣ `/mass1` - Verificador Masivo\n6️⃣ `/mislives` - Descargar LIVES\n7️⃣ `/daily` - Reclamar créditos\n8️⃣ `/buyvip` - Comprar VIP\n9️⃣ `/stealth` - Modo Incógnito\n🔟 `/dir` - Generar Dirección\n1️⃣1️⃣ `/down` - Descargar Video/Fotos\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n💡 <i>Usa con <code>/</code> o <code>.</code></i>"
        try: await query.message.edit_caption(caption=tools_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Back", callback_data='btn_back_main', api_kwargs={"style": "danger"})]]), parse_mode='HTML')
        except: pass

# ============ MANEJO DE TEXTO ============
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith('.'):
        cmd = text[1:].split(' ')[0]
        context.args = text[1:].split(' ')[1:]
        if cmd == 'me': await me_cmd(update, context)
        elif cmd == 'bin': await bin_cmd(update, context)
        elif cmd == 'gen': await gen_cmd(update, context)
        elif cmd == 'cmds': await cmds_cmd(update, context)
        elif cmd == 'start': await start_cmd(update, context)
        elif cmd == 'check_gratis': await check_gratis_cmd(update, context)
        elif cmd in ['mass1', 'mss1']: await mss1_cmd(update, context)
        elif cmd == 'mislives': await mislives_cmd(update, context)
        elif cmd == 'setname': await setname_cmd(update, context)
        elif cmd == 'daily': await daily_cmd(update, context)
        elif cmd == 'buyvip': await buyvip_cmd(update, context)
        elif cmd == 'stealth': await stealth_cmd(update, context)
        elif cmd == 'dir': await dir_cmd(update, context)
        elif cmd == 'down': await down_cmd(update, context)

# ============ ARRANQUE ============
def main():
    init_db()
    global NOMBRE_BOT
    if obtener_nombre() == "Wuawuri Chk":
        guardar_nombre("Sukuna Chk")
    NOMBRE_BOT = "Sukuna Chk"
    
    threading.Thread(target=run_web_server, daemon=True).start()
    
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
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.TEXT | filters.COMMAND & ~filters.COMMAND | filters.TEXT, handle_text))
    
    print("🌸 Bot Sukuna Chk iniciado (Render + Colores).")
    app.run_polling()

if __name__ == "__main__":
    main()
