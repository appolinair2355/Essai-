"""
Main entry point for the Telegram bot deployment on render.com (POLLING MODE)
"""
import os
import logging
import threading
from flask import Flask
from bot import TelegramBot # Assurez-vous que bot.py expose une méthode de démarrage du Polling
from config import Config

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
bot = TelegramBot(bot_token) # Supposons que ceci initialise la librairie de bot

# --- NOUVELLE FONCTION : DÉMARRAGE DU POLLING ---
def start_polling_process():
    """Lance le bot en mode Polling."""
    logger.info("🤖 Démarrage du bot en mode Polling...")
    
    try:
        # 🚨 ATTENTION : Vous devez utiliser la fonction de Polling spécifique à votre librairie de bot
        # Exemples (adaptez à votre librairie) :
        
        # Exemple 1: Si votre bot est basé sur 'python-telegram-bot' (Updater/Application)
        # application.run_polling() 
        
        # Exemple 2: Si vous utilisez un simple 'while True' loop avec bot.get_updates()
        # bot.run_polling_loop() 

        # Exemple 3: Si votre classe TelegramBot a une méthode start_polling
        bot.start_polling() # <-- C'est l'hypothèse la plus probable pour le Polling
        
        logger.info("✅ Polling du bot démarré avec succès et actif.")
    except Exception as e:
        logger.error(f"❌ Erreur critique lors du démarrage du Polling : {e}")
        
# --- ENDPOINTS POUR RENDER.COM (HEALTH CHECK) ---
# Nous gardons ces routes pour satisfaire l'exigence du PORT de Render
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for render.com"""
    # Si le thread du bot est actif, tout va bien
    if bot_thread.is_alive():
        return {'status': 'healthy', 'service': 'telegram-bot'}, 200
    return {'status': 'unhealthy', 'service': 'telegram-bot'}, 503

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return {'message': 'Telegram Bot is running in POLLING mode', 'status': 'active'}, 200

# Global thread variable for the bot
bot_thread = None

if __name__ == '__main__':
    # 1. Crée et lance le thread de Polling
    bot_thread = threading.Thread(target=start_polling_process)
    bot_thread.daemon = True # Permet au programme de se fermer si le thread principal meurt
    bot_thread.start()

    # 2. Récupère le port
    port = int(os.getenv('PORT') or 5000)
    logger.info(f"Serveur Flask démarré sur le port {port} pour Render.com (Health Check).")

    # 3. Démarre l'application Flask pour écouter sur le PORT requis par Render
    app.run(host='0.0.0.0', port=port, debug=False)

