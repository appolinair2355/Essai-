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

class TelegramBot:
    """Gère les requêtes API Telegram."""

    def __init__(self, token: str):
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.token = token
        # Mettez vos commandes ici pour un traitement rapide
        self.handlers = {
            '/start': self._handle_start,
            '/ping': self._handle_ping,
        }

    def _request(self, method: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Méthode générique pour envoyer une requête à l'API Telegram."""
        url = self.api_url + method
        try:
            if not self.token: return None
            response = requests.post(url, json=data, timeout=5)
            response.raise_for_status()
            result = response.json()
            
            if not result.get('ok'):
                logger.error(f"❌ API Telegram a retourné ok=false pour {method}. Desc: {result.get('description', 'N/A')}")
            
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur API Telegram ({method}): {e}")
            return None

    def set_webhook(self, webhook_url: str) -> bool:
        """Configure l'URL du Webhook. Utilisé ici pour la suppression."""
        data = {'url': webhook_url, 'drop_pending_updates': True}
        result = self._request('setWebhook', data)
        return result and result.get('ok')

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

    # ... autres méthodes (edit_message_text, answer_callback_query, send_document) ...
    # Les autres méthodes de votre bot.py sont conservées mais omises ici pour la concision

    def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> List[Dict]:
        """Récupère les mises à jour via polling (long polling)."""
        data = {
            'timeout': timeout,
            'allowed_updates': ['message', 'callback_query'] # Simplifié
        }
        if offset:
            data['offset'] = offset
        
        result = self._request('getUpdates', data)
        return result.get('result', []) if result and result.get('ok') else []

    # --- Gestion des updates Polling ---
    
    def _log_update_info(self, update: Dict):
        """Logue l'info essentielle de l'update pour le debug."""
        if 'message' in update:
            msg = update['message']
            chat_id = msg.get('chat', {}).get('id', 'unknown')
            user_id = msg.get('from', {}).get('id', 'unknown')
            text = msg.get('text', '')[:50]
            logger.info(f"📨 MESSAGE | Chat:{chat_id} | User:{user_id} | Text: {text}...")
        elif 'callback_query' in update:
            query = update['callback_query']
            user_id = query.get('from', {}).get('id', 'unknown')
            data = query.get('data', '')
            logger.info(f"📲 CALLBACK | User:{user_id} | Data: {data}")

    def _handle_start(self, chat_id: str, message: Dict):
        self.send_message(chat_id, "🚀 Je suis le bot en mode Polling déployé sur Render.com. Utilisez /ping pour vérifier mon activité.")

    def _handle_ping(self, chat_id: str, message: Dict):
        self.send_message(chat_id, "Pong! Je suis bien vivant et je pollise.")
        
    def handle_update(self, update: Dict):
        """Distribue l'update au bon gestionnaire."""
        self._log_update_info(update)
        
        if 'message' in update:
            message = update['message']
            chat_id = message.get('chat', {}).get('id')
            text = message.get('text', '')
            
            if text.startswith('/'):
                command = text.split()[0]
                handler = self.handlers.get(command)
                if handler:
                    handler(chat_id, message)
                else:
                    logger.warning(f"Commande non gérée: {command}")
        
        elif 'callback_query' in update:
            # Logique pour les boutons
            query = update['callback_query']
            chat_id = query.get('message', {}).get('chat', {}).get('id')
            data = query.get('data')
            
            # Exemple : self._handle_callback(chat_id, data)
            self.answer_callback_query(query['id'], text=f"Donnée reçue: {data}")

