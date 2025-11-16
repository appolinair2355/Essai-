# bot.py

"""
Telegram Bot implementation with advanced features and deployment capabilities
"""
import os
import logging
import requests
import json
from typing import Dict, Any, Optional

# Importation des classes de logique métier
from handlers import TelegramHandlers
from card_predictor import CardPredictor # Importé pour référence comme dans votre schéma, mais non utilisé directement ici

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TelegramBot:
    """
    Classe de haut niveau pour gérer les interactions avec l'API Telegram
    et déléguer le traitement des mises à jour aux handlers.
    """

    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        # Fichier de déploiement (comme dans le schéma)
        self.deployment_file_path = "final2025.zip" 
        
        # Initialize advanced handlers
        self.handlers = TelegramHandlers(token)
        
        if not self.handlers.card_predictor:
            logger.error("🚨 Le moteur de prédiction n'a pas pu être initialisé.")


    def handle_update(self, update: Dict[str, Any]) -> None:
        """Handle incoming Telegram update with advanced features for webhook mode"""
        try:
            # Log avec type de message (Adherence au schéma)
            if 'message' in update:
                logger.info(f"🔄 Bot traite message normal via webhook")
            elif 'edited_message' in update:
                logger.info(f"🔄 Bot traite message édité via webhook")
            elif 'channel_post' in update:
                 logger.info(f"🔄 Bot traite post de canal via webhook")
            elif 'edited_channel_post' in update:
                 logger.info(f"🔄 Bot traite post de canal édité via webhook")
            
            logger.debug(f"Received update: {json.dumps(update, indent=2)}")

            # Use the advanced handlers for processing (délégation)
            self.handlers.handle_update(update)
            
            logger.info(f"✅ Update traité avec succès via webhook")

        except Exception as e:
            logger.error(f"❌ Error handling update via webhook: {e}")

    # --- Méthodes API Directes (Requises par le schéma) ---

    def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown') -> bool:
        """Send text message to user"""
        # Note: La méthode de handlers.py est utilisée pour la logique de prédiction/édition, 
        # mais cette méthode publique est là pour respecter le schéma et les cas génériques.
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }

            response = requests.post(url, json=data, timeout=10)
            result = response.json()

            if result.get('ok'):
                logger.debug(f"Message sent successfully to chat {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message: {result}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending message: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def send_document(self, chat_id: int, file_path: str) -> bool:
        """Send document file to user (Méthode incluse pour respecter le schéma)"""
        try:
            url = f"{self.base_url}/sendDocument"

            if not os.path.exists(file_path):
                logger.error(f"File not found for sending: {file_path}")
                return False

            with open(file_path, 'rb') as file:
                files = {
                    'document': (os.path.basename(file_path), file, 'application/zip')
                }
                data = {
                    'chat_id': chat_id,
                    'caption': '📦 Deployment Package for render.com'
                }

                response = requests.post(url, data=data, files=files, timeout=60)
                result = response.json()

                if result.get('ok'):
                    logger.info(f"Document sent successfully to chat {chat_id}")
                    return True
                else:
                    logger.error(f"Failed to send document: {result}")
                    return False

        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False


    def set_webhook(self, webhook_url: str) -> bool:
        """Set webhook URL for the bot"""
        try:
            url = f"{self.base_url}/setWebhook"
            data = {
                'url': webhook_url,
                'allowed_updates': ['message', 'edited_message', 'channel_post', 'edited_channel_post']
            }

            response = requests.post(url, json=data, timeout=10)
            result = response.json()

            if result.get('ok'):
                logger.info(f"Webhook set successfully: {webhook_url}")
                return True
            else:
                logger.error(f"Failed to set webhook: {result}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error setting webhook: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return False

    def get_bot_info(self) -> Dict[str, Any]:
        """Get bot information"""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=30)
            result = response.json()

            if result.get('ok'):
                return result.get('result', {})
            else:
                logger.error(f"Failed to get bot info: {result}")
                return {}

        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return {}
            
