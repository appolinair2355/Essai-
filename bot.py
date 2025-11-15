"""
Implémentation de l'interaction avec l'API Telegram (Polling et requêtes).
"""
import os
import time
import json
import requests
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Importation hypothétique des gestionnaires de commandes.
# NOTE: Dans un vrai projet, les gestionnaires de commandes ne sont pas ici.
# Nous allons juste garder les méthodes API.

class TelegramBot:
    """Gère les requêtes API Telegram."""

    def __init__(self, token: str):
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.token = token

    def _request(self, method: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Méthode générique pour envoyer une requête à l'API Telegram.
        Timeout augmenté à 35s pour le Long Polling (Long Polling dure 30s).
        """
        url = self.api_url + method
        try:
            if not self.token: return None
            
            # 💡 CORRECTION : Augmentation du timeout HTTP
            HTTP_TIMEOUT = 35 
            
            response = requests.post(url, json=data, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            
            if not result.get('ok'):
                logger.error(f"❌ API Telegram a retourné ok=false pour {method}. Desc: {result.get('description', 'N/A')}")
            
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur API Telegram ({method}): {e}")
            return None

    def delete_webhook(self) -> bool:
        """Supprime l'URL du Webhook (CRUCIAL pour le Polling)."""
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
        data = {'chat_id': chat_id, 'text': text}
        if parse_mode: data['parse_mode'] = parse_mode
        if reply_markup: data['reply_markup'] = json.dumps(reply_markup)

        result = self._request('sendMessage', data)
        return result['result'].get('message_id') if result and result.get('ok') and 'result' in result else None

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        data = {
            'callback_query_id': callback_query_id,
            'text': text
        }
        self._request('answerCallbackQuery', data)
        
    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[Dict]:
        """Récupère les mises à jour via polling (long polling)."""
        data = {
            'timeout': timeout,
            'allowed_updates': ['message', 'callback_query'] 
        }
        if offset:
            data['offset'] = offset
        
        result = self._request('getUpdates', data)
        return result.get('result', []) if result and result.get('ok') else []

    # Les autres méthodes de votre bot.py sont conservées mais omises ici.
    
    # 🚨 NOTE IMPORTANTE : La méthode 'handle_update' est déplacée vers handlers.py (process_update)
    
