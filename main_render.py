"""
Point d'entrée pour Render.com - MODE POLLING PUR
Le bot fonctionne sans Flask/Webhook
"""

import os
import logging
import time
from config import Config
from bot import TelegramBot
from handlers import process_update

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Initialisation ---
config = Config()

if not config.BOT_TOKEN:
    logger.critical("❌ FATAL - BOT_TOKEN n'est pas configuré")
    exit(1)

bot = TelegramBot(config.BOT_TOKEN)

# --- Fonction de Polling ---
def start_polling():
    """Démarre le polling Telegram (longpolling)"""
    logger.info("=" * 60)
    logger.info("🤖 BOT TELEGRAM DAME PRÉDICTION - MODE POLLING")
    logger.info("=" * 60)
    logger.info(f"✅ Bot Token configuré")
    logger.info(f"✅ Admin Chat ID: {config.ADMIN_CHAT_ID}")
    logger.info(f"✅ Canal Source: {config.TARGET_CHANNEL_ID}")
    logger.info(f"✅ Canal Prédiction: {config.PREDICTION_CHANNEL_ID}")
    logger.info(f"✅ Environnement: {'RENDER.COM' if config.IS_RENDER else 'AUTRE'}")
    logger.info("=" * 60)
    
    # Supprimer le webhook s'il existe
    logger.info("🔧 Suppression du webhook existant...")
    bot.delete_webhook()
    time.sleep(1)
    
    offset = 0
    logger.info("🚀 Démarrage du polling...")
    
    while True:
        try:
            updates = bot.get_updates(offset=offset, timeout=30)
            
            if updates:
                for update in updates:
                    try:
                        process_update(bot, update)
                        offset = update['update_id'] + 1
                    except Exception as e:
                        logger.error(f"❌ Erreur traitement update: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
        except Exception as e:
            logger.error(f"❌ Erreur polling: {e}")
            time.sleep(5)

if __name__ == '__main__':
    start_polling()
