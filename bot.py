"""
Implémentation de l'interaction avec l'API Telegram (Webhook et requêtes).
"""
import os
import time
import json
import requests
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class TelegramBot:
    """Gère les requêtes API Telegram."""

    def __init__(self, token: str):
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.token = token

    def _request(self, method: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Méthode générique pour envoyer une requête à l'API Telegram."""
        url = self.api_url + method
        try:
            if not self.token:
                 return None
            response = requests.post(url, json=data, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            # Vérifier si l'API Telegram a retourné ok=false
            if not result.get('ok'):
                logger.error(f"❌ API Telegram a retourné ok=false pour {method}")
                logger.error(f"Description: {result.get('description', 'Aucune description')}")
                logger.error(f"Données envoyées: {data}")
            
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur API Telegram ({method}): {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Détails de l'erreur: {error_detail}")
                except:
                    logger.error(f"Réponse brute: {e.response.text}")
            return None

    def set_webhook(self, webhook_url: str) -> bool:
        """Configure l'URL du Webhook."""
        # drop_pending_updates=True résout l'erreur 409 Conflict en supprimant l'ancien Webhook
        data = {
            'url': webhook_url,
            'drop_pending_updates': True
        }
        result = self._request('setWebhook', data)
        if result and result.get('ok'):
            logger.info(f"✅ Webhook configuré : {webhook_url}")
            return True
        else:
            logger.error(f"❌ Échec de la configuration du Webhook. Réponse : {result}")
            return False

    def delete_webhook(self) -> bool:
        """Supprime l'URL du Webhook (utile pour la réinitialisation ou le debug)."""
        data = {'drop_pending_updates': True}
        result = self._request('deleteWebhook', data)
        if result and result.get('ok'):
            logger.info("✅ Webhook supprimé avec succès.")
            return True
        else:
            logger.error(f"❌ Échec de la suppression du Webhook. Réponse : {result}")
            return False

    # --- Méthodes API ---

    def send_message(self, chat_id, text: str, parse_mode: Optional[str] = None, reply_markup: Optional[Dict] = None) -> Optional[int]:
        data = {
            'chat_id': chat_id,
            'text': text
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)

        result = self._request('sendMessage', data)
        if result and result.get('ok') and 'result' in result:
            return result['result'].get('message_id')
        return None

    def edit_message_text(self, chat_id, message_id: int, text: str, parse_mode: Optional[str] = None, reply_markup: Optional[Dict] = None):
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)

        self._request('editMessageText', data)

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        data = {
            'callback_query_id': callback_query_id,
            'text': text
        }
        self._request('answerCallbackQuery', data)

    def send_document(self, chat_id: str, file_path: str) -> bool:
        """Send a document file."""
        url = f"{self.api_url}sendDocument"

        try:
            if not os.path.exists(file_path):
                logger.error(f"❌ Fichier introuvable: {file_path}")
                return False

            with open(file_path, 'rb') as file:
                files = {'document': (os.path.basename(file_path), file, 'application/zip')}
                data = {'chat_id': chat_id}
                logger.info(f"📤 Envoi du fichier {file_path}...")
                response = requests.post(url, data=data, files=files, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        logger.info(f"✅ Fichier {file_path} envoyé avec succès")
                        return True
                    else:
                        logger.error(f"❌ API a refusé: {result}")
                        return False
                else:
                    logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Exception lors de l'envoi du fichier: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[Dict]:
        """Récupère les mises à jour via polling (long polling)."""
        data = {
            'timeout': timeout,
            'allowed_updates': ['message', 'edited_message', 'channel_post', 'edited_channel_post', 'callback_query']
        }
        if offset:
            data['offset'] = offset
        
        result = self._request('getUpdates', data)
        if result and result.get('ok'):
            return result.get('result', [])
        return []