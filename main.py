# main.py

"""
Main entry point for the Telegram bot deployment on render.com
"""
import os
import logging
from flask import Flask, request, jsonify
import requests

# Importe notre classe de gestionnaire et l'aliasse en TelegramBot pour respecter le schéma
from handlers import TelegramHandlers as TelegramBot 

# --- CONFIGURATION (Lecture directe de l'environnement) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "VOTRE_TOKEN_TELEGRAM_ICI") 
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "VOTRE_URL_WEBHOOK_ICI") 
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize bot
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in environment variables.")

# 'bot' est notre instance de TelegramHandlers
bot = TelegramBot(BOT_TOKEN)

# --- LOGIQUE WEBHOOK ---

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook from Telegram"""
    try:
        update = request.get_json(silent=True)
        if not update:
            return jsonify({'status': 'ok'}), 200

        # Log type de message reçu avec détails (Adherence au schéma)
        if 'message' in update:
            msg = update['message']
            chat_id = msg.get('chat', {}).get('id', 'unknown')
            user_id = msg.get('from', {}).get('id', 'unknown')
            text = msg.get('text', '')[:50]
            logger.info(f"📨 WEBHOOK - Message normal | Chat:{chat_id} | User:{user_id} | Text:{text}...")
        elif 'edited_message' in update:
            msg = update['edited_message']
            chat_id = msg.get('chat', {}).get('id', 'unknown')
            user_id = msg.get('from', {}).get('id', 'unknown')
            text = msg.get('text', '')[:50]
            logger.info(f"✏️ WEBHOOK - Message édité | Chat:{chat_id} | User:{user_id} | Text:{text}...")
        elif 'channel_post' in update:
            msg = update['channel_post']
            chat_id = msg.get('chat', {}).get('id', 'unknown')
            text = msg.get('text', '')[:50]
            logger.info(f"📢 WEBHOOK - Post Canal | Chat:{chat_id} | Text:{text}...")

        logger.debug(f"Webhook received update: {update}")

        if update:
            # Traitement direct pour meilleure réactivité
            bot.handle_update(update)
            logger.info("Update processed successfully")

        return 'OK', 200
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return 'Error', 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for render.com"""
    return {'status': 'healthy', 'service': 'telegram-bot'}, 200

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return {'message': 'Telegram Bot is running', 'status': 'active'}, 200

# --- CONFIGURATION WEBHOOK ---

def set_webhook_request(url: str) -> bool:
    """Envoie la requête à l'API Telegram pour configurer le webhook."""
    setup_url = f"{TELEGRAM_API_URL}/setWebhook?url={url}"
    try:
        response = requests.get(setup_url)
        response.raise_for_status()
        result = response.json()
        return result.get('ok', False)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur lors de l'appel setWebhook: {e}")
        return False

def setup_webhook():
    """Set up webhook on startup"""
    try:
        if WEBHOOK_URL and not WEBHOOK_URL.startswith("VOTRE_"):
            full_webhook_url = f"{WEBHOOK_URL}/webhook"
            logger.info(f"🔗 Configuration webhook: {full_webhook_url}")

            # Configure webhook 
            success = set_webhook_request(full_webhook_url)
            
            if success:
                logger.info(f"✅ Webhook configuré avec succès: {full_webhook_url}")
                logger.info(f"🎯 Bot prêt pour prédictions automatiques et vérifications via webhook")
            else:
                logger.error("❌ Échec configuration webhook")
        else:
            logger.warning("⚠️ WEBHOOK_URL non configurée ou valeur par défaut. Le webhook ne sera PAS configuré.")
            logger.info("💡 Pour activer le webhook, configurez la variable WEBHOOK_URL dans votre environnement.")
    except Exception as e:
        logger.error(f"❌ Erreur configuration webhook: {e}")

if __name__ == '__main__':
    # Set up webhook on startup
    setup_webhook()

    # Get port from environment 
    port = int(os.getenv('PORT') or 10000)

    # Run the Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
            
