"""
Main entry point for the Telegram bot deployment on render.com (POLLING MODE)
Implémente le 'Double Démarrage' (Polling en thread + Flask Health Check)
"""
import os
import logging
import threading
import time
from flask import Flask, jsonify
from bot import TelegramBot
from config import Config
# 💡 IMPORT CRUCIAL : Importation de la fonction de traitement
from handlers import process_update 

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize bot and config
config = Config()
bot_token = config.BOT_TOKEN
if not bot_token:
    raise ValueError("BOT_TOKEN is required")
bot = TelegramBot(bot_token)

# Thread global pour le statut du bot
bot_thread = None

# --- FONCTION DE DÉMARRAGE DU POLLING (CORRIGÉE) ---
def start_polling_process():
    """Lance le bot en mode Polling, gère les mises à jour, l'offset et appelle le handler."""
    logger.info("🤖 Démarrage du bot en mode Polling...")
    
    # ÉTAPE 1 : S'assurer qu'aucun webhook n'est configuré
    try:
        bot.delete_webhook() 
        logger.info("✅ Webhook supprimé avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du Webhook : {e}")

    offset = None 
    
    while True:
        try:
            # Récupère les updates via Long Polling
            updates = bot.get_updates(offset=offset, timeout=30)
            
            if updates:
                logger.info(f"📥 {len(updates)} nouvelles mises à jour reçues.")
                
                for update in updates:
                    # 💡 CORRECTION : Appeler la fonction de traitement (handlers.py)
                    process_update(bot, update)
                    
                    # Mise à jour de l'offset pour la prochaine requête
                    update_id = update.get('update_id')
                    if update_id is not None:
                        offset = update_id + 1
                        
        except Exception as e:
            logger.error(f"❌ Erreur critique dans la boucle de Polling : {e}. Nouvelle tentative dans 5s.")
            time.sleep(5)

# --- ENDPOINTS POUR RENDER.COM (HEALTH CHECK) ---
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint pour Render.com."""
    if bot_thread and bot_thread.is_alive():
        return jsonify({'status': 'healthy', 'service': 'telegram-bot-polling'}), 200
    
    logger.error("❌ Thread de Polling inactif!")
    return jsonify({'status': 'unhealthy', 'service': 'telegram-bot-polling', 'error': 'Polling thread died'}), 503

@app.route('/', methods=['GET'])
def home():
    """Endpoint racine."""
    return jsonify({'message': 'Telegram Bot is running in POLLING mode', 'status': 'active'}), 200

# --- DÉMARRAGE PRINCIPAL ---
if __name__ == '__main__':
    
    # 1. Crée et lance le thread de Polling (le bot)
    logger.info("Démarrage du Thread de Polling...")
    bot_thread = threading.Thread(target=start_polling_process)
    bot_thread.daemon = True 
    bot_thread.start()

    # 2. Démarre l'application Flask (Health Check) sur le PORT requis par Render
    logger.info(f"Serveur Flask (Health Check) démarré sur le port {config.PORT}.")
    app.run(host='0.0.0.0', port=config.PORT, debug=False)
        
