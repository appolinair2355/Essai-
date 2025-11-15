"""
Fichier de configuration : Charge les variables d'environnement
Avec IDs pré-configurés pour le déploiement
Détection automatique de l'environnement (Replit vs Render.com)
"""
import os
import logging

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        # IDs pré-configurés (peuvent être surchargés par les variables d'environnement)
        DEFAULT_TARGET_CHANNEL_ID = "-1003424179389"
        DEFAULT_PREDICTION_CHANNEL_ID = "-1003362820311"
        
        # Détection automatique de l'environnement
        self.IS_REPLIT = os.environ.get('REPL_SLUG') is not None
        self.IS_RENDER = os.environ.get('RENDER') is not None
        
        self.BOT_TOKEN = os.environ.get('BOT_TOKEN')
        self.TARGET_CHANNEL_ID = os.environ.get('TARGET_CHANNEL_ID') or DEFAULT_TARGET_CHANNEL_ID
        self.PREDICTION_CHANNEL_ID = os.environ.get('PREDICTION_CHANNEL_ID') or DEFAULT_PREDICTION_CHANNEL_ID
        self.ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')
        
        # Port intelligent : Replit utilise 10000, Render utilise son port dynamique
        if self.IS_REPLIT:
            self.PORT = 10000
        else:
            self.PORT = int(os.environ.get('PORT') or 10000)
        
        # Validation et logs détaillés
        logger.info("=" * 50)
        logger.info("🔧 Configuration du Bot")
        logger.info("=" * 50)
        
        # Afficher l'environnement détecté
        if self.IS_REPLIT:
            logger.info("🏠 Environnement détecté: REPLIT")
        elif self.IS_RENDER:
            logger.info("🌐 Environnement détecté: RENDER.COM")
        else:
            logger.info("💻 Environnement détecté: LOCAL/AUTRE")
        
        if not self.BOT_TOKEN:
            logger.critical("❌ BOT_TOKEN n'est pas configuré - Le bot ne peut pas démarrer")
        else:
            logger.info(f"✅ BOT_TOKEN configuré (longueur: {len(self.BOT_TOKEN)})")
        
        logger.info(f"✅ TARGET_CHANNEL_ID: {self.TARGET_CHANNEL_ID} (pré-configuré)")
        logger.info(f"✅ PREDICTION_CHANNEL_ID: {self.PREDICTION_CHANNEL_ID} (pré-configuré)")
        
        if not self.ADMIN_CHAT_ID:
            logger.warning("⚠️ ADMIN_CHAT_ID non configuré")
        else:
            logger.info(f"✅ ADMIN_CHAT_ID: {self.ADMIN_CHAT_ID}")
        
        logger.info(f"✅ PORT: {self.PORT}")
        logger.info("=" * 50)
