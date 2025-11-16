"""
Event handlers for the Telegram bot - adapted for webhook deployment
"""

import logging
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, Any, Optional, List, Tuple
import requests 
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- IMPORTS ET CONSTANTES ---

# L'importation de CardPredictor est faite dans __init__ pour éviter les problèmes d'importation circulaire avec main.py
TARGET_CHANNEL_ID = -1003424179389
PREDICTION_CHANNEL_ID = -1003362820311

# Limites de débit
user_message_counts = defaultdict(list)
MAX_MESSAGES_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60

# Messages
WELCOME_MESSAGE = """
🎭 **BIENVENUE DANS LE MONDE DE JOKER DEPLOY299999 !** 🔮

🎯 **COMMANDES DISPONIBLES:**
• `/start` - Accueil
• `/stat` - Statistiques de réussite (Dame Q)
• `/bilan` - Bilan des prédictions stockées
• `/inter [apply|default]` - Gérer le Mode Intelligent

🎯 **Version DEPLOY299999 - Port 10000**
"""

GREETING_MESSAGE = "👋 **Bot de Prédiction Intelligent Dame (Q)!**\n\nCommandes: /start, /stat, /bilan, /inter."

def is_rate_limited(user_id: int) -> bool:
    """Vérifie si l'utilisateur est soumis à une limite de débit."""
    now = datetime.now()
    user_messages = user_message_counts[user_id]
    user_messages[:] = [msg_time for msg_time in user_messages 
                       if now - msg_time < timedelta(seconds=RATE_LIMIT_WINDOW)]
    if len(user_messages) >= MAX_MESSAGES_PER_MINUTE:
        return True
    user_messages.append(now)
    return False

# --- CLASSE HANDLERS ---

class TelegramHandlers:
    """Handlers for Telegram bot using webhook approach"""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        try:
            from card_predictor import CardPredictor
            self.card_predictor = CardPredictor()
        except ImportError:
            logger.error("❌ Échec de l'importation de CardPredictor.")
            self.card_predictor = None

    # --- MÉTHODES D'INTERACTION TELEGRAM (requests) ---

    def send_message(self, chat_id: int, text: str, parse_mode='Markdown', message_id: Optional[int] = None) -> Optional[Dict]:
        """Envoie ou édite un message via requests."""
        if message_id:
            method = 'editMessageText'
            payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': parse_mode}
        else:
            method = 'sendMessage'
            payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}

        url = f"{self.base_url}/{method}"
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur {method} Telegram à {chat_id}: {e}")
            return None

    def edit_message(self, chat_id: int, message_id: int, text: str, parse_mode='Markdown') -> bool:
        """Fonction utilitaire pour l'édition de message."""
        result = self.send_message(chat_id, text, parse_mode, message_id)
        return result.get('ok', False) if result else False
            
    def process_prediction_action(self, action: Dict):
        """Traite les actions de prédiction/vérification (envoi/édition)."""
        
        predicted_game = action.get('predicted_game')
        new_message = action.get('new_message')
        chat_id = self.card_predictor.prediction_channel_id 

        if action.get('type') == 'new_prediction':
            result = self.send_message(chat_id=chat_id, text=new_message)
            
            if result and result.get('ok'):
                message_id = result['result']['message_id']
                if predicted_game in self.card_predictor.predictions:
                    self.card_predictor.predictions[predicted_game]['message_id'] = message_id
            
        elif action.get('type') == 'edit_message':
            prediction_data = self.card_predictor.predictions.get(predicted_game)
            message_id = prediction_data.get('message_id') if prediction_data else None

            if message_id:
                self.edit_message(
                    chat_id=chat_id, 
                    text=new_message,
                    message_id=message_id
                )
            else:
                self.send_message(chat_id=chat_id, text=new_message)
        
        self.card_predictor._save_all_data()

    # --- GESTION DES COMMANDES ---

    def _handle_start_command(self, chat_id: int, user_id: Optional[int]) -> None:
        """Gère la commande /start."""
        self.send_message(chat_id, WELCOME_MESSAGE)
        
    def _handle_stat_command(self, chat_id: int, user_id: Optional[int]) -> None:
        """Gère la commande /stat."""
        if not self.card_predictor: return
        
        correct_count = sum(1 for p in self.card_predictor.predictions.values() if p['status'].startswith('correct'))
        failed_count = sum(1 for p in self.card_predictor.predictions.values() if p['status'] == 'failed')
        total_verified = correct_count + failed_count
        win_rate = (correct_count / total_verified) * 100 if total_verified > 0 else 0
        
        text = (
            f"**📈 STATISTIQUES GLOBALES 📊**\n"
            f"**TAUX DE RÉUSSITE (Q):** **{win_rate:.2f}%**\n"
            f"Prédictions Totales (Vérifiées): {total_verified}\n"
            f"Mode Intelligent Actif: {'✅ OUI' if self.card_predictor.is_inter_mode_active else '❌ NON'}"
        )
        self.send_message(chat_id, text)

    def _handle_bilan_command(self, chat_id: int, user_id: Optional[int]) -> None:
        """Gère la commande /bilan."""
        if not self.card_predictor: return
        
        pending = len([g for g, p in self.card_predictor.predictions.items() if p['status'] == 'pending'])
        text = (
            f"**📋 BILAN 🛎️**\n"
            f"Messages uniques traités: {len(self.card_predictor.processed_messages)}\n"
            f"Prédictions stockées: {len(self.card_predictor.predictions)}\n"
            f"Prédictions en Attente (⏳): {pending}"
        )
        self.send_message(chat_id, text)

    def _handle_inter_command(self, chat_id: int, text: str, user_id: Optional[int]) -> None:
        """Gère la commande /inter [apply|default]."""
        if not self.card_predictor: 
            self.send_message(chat_id, "⚠️ Le système de prédiction n'est pas initialisé.")
            return
        
        parts = text.split()
        args = parts[1:]
        
        if args and args[0].lower() == 'apply':
            if len(self.card_predictor.inter_data) < 3:
                 message = "⚠️ Données insuffisantes (Min 3 enregistrements Dame Q) pour l'analyse intelligente."
            else:
                analysis_summary = self.card_predictor.analyze_and_set_smart_rules()
                self.card_predictor._save_all_data()
                message = "**🧠 MODE INTELLIGENT ACTIF!**\nDéclencheurs choisis:\n" + "\n".join(analysis_summary)
                
        elif args and args[0].lower() == 'default':
            self.card_predictor.is_inter_mode_active = False
            self.card_predictor.smart_rules = []
            self.card_predictor._save_all_data()
            message = "**❌ MODE PAR DÉFAUT ACTIF.** Les règles prédéfinies sont utilisées."
        else:
            # Gère l'affichage du grand volume de données par résumé
            message = self.card_predictor.get_inter_status()
            message += "\n\n*Pour appliquer les règles, utilisez `/inter apply`.*"
            message += "\n*Pour revenir au mode par défaut, utilisez `/inter default`.*"
    
        self.send_message(chat_id, message)

    # --- GESTION DES UPDATES PRINCIPALES ---

    def _handle_message(self, message: Dict[str, Any]) -> None:
        """Gère les messages normaux, de canal, et les commandes."""
        try:
            chat_id = message['chat']['id']
            user_id = message.get('from', {}).get('id')
            sender_chat_id = message['chat'].get('id', chat_id) # Utilise chat_id pour les groupes/canaux
            
            chat_type = message['chat'].get('type', 'private')
            if user_id and chat_type == 'private' and is_rate_limited(user_id):
                self.send_message(chat_id, "⏰ Veuillez patienter avant d'envoyer une autre commande.")
                return

            if 'text' in message:
                text = message['text'].strip()
                
                # 1. GESTION DES COMMANDES
                if text.startswith('/'):
                    if text == '/start':
                        self._handle_start_command(chat_id, user_id)
                    elif text == '/stat':
                        self._handle_stat_command(chat_id, user_id)
                    elif text == '/bilan':
                        self._handle_bilan_command(chat_id, user_id)
                    elif text.startswith('/inter'):
                        self._handle_inter_command(chat_id, text, user_id)
                    else:
                        self.send_message(chat_id, "⚠️ **Commande inconnue.** Utilisez `/start` pour voir les commandes disponibles.")
                    return 

                # 2. TRAITEMENT DU CANAL SOURCE (Prédiction/Vérification)
                if sender_chat_id == TARGET_CHANNEL_ID: 
                    self._process_channel_message(message, is_edited=False)

            # Handle new chat members
            if 'new_chat_members' in message:
                self._handle_new_chat_members(message)

        except Exception as e:
            logger.error(f"❌ Erreur de traitement du message: {e}")

    def _handle_edited_message(self, message: Dict[str, Any]) -> None:
        """Gère les messages édités (essentiel pour la vérification)."""
        try:
            chat_id = message['chat']['id']
            sender_chat_id = message['chat'].get('id', chat_id)
            
            if sender_chat_id == TARGET_CHANNEL_ID:
                self._process_channel_message(message, is_edited=True)

        except Exception as e:
            logger.error(f"❌ Erreur de traitement du message édité: {e}")

    def _process_channel_message(self, message: Dict[str, Any], is_edited: bool) -> None:
        """Logique unifiée de prédiction et de vérification pour les messages de canal."""
        if not self.card_predictor: return

        message_text = message.get('text', '')
        if not message_text: return

        # VÉRIFICATION (Prioritaire)
        verification_action = self.card_predictor._verify_prediction_common(message_text, is_edited=is_edited)
        if verification_action:
            self.process_prediction_action(verification_action)
            # Si c'est un résultat final (✅ ou ❌), on arrête.
            if verification_action.get('new_message', '').endswith(('✅0️⃣', '✅1️⃣', '✅2️⃣', '❌')):
                return
        
        # PRÉDICTION
        should_predict, game_number, predicted_value = self.card_predictor.should_predict(message_text)

        if should_predict:
            new_prediction_message = self.card_predictor.make_prediction(game_number, predicted_value)
            
            action = {
                'type': 'new_prediction',
                'predicted_game': game_number + 2,
                'new_message': new_prediction_message
            }
            self.process_prediction_action(action)
            
    def _handle_new_chat_members(self, message: Dict[str, Any]) -> None:
        """Gère l'ajout de nouveaux membres au chat (pour le message de bienvenue)."""
        new_members = message['new_chat_members']
        chat_id = message['chat']['id']
        
        for member in new_members:
            if member.get('is_bot'):
                 self.send_message(chat_id, GREETING_MESSAGE)
                 break

    def handle_update(self, update: Dict[str, Any]) -> None:
        """Point d'entrée principal pour traiter une mise à jour Telegram."""
        try:
            if 'message' in update:
                self._handle_message(update['message'])
            elif 'edited_message' in update:
                self._handle_edited_message(update['edited_message'])
            elif 'channel_post' in update:
                self._handle_message(update['channel_post'])
            elif 'edited_channel_post' in update:
                self._handle_edited_message(update['edited_channel_post'])
            # Note: pas de gestion explicite de 'sender_chat' car nous utilisons chat['id']
            # qui est l'ID du canal/groupe pour les messages de canal.

        except Exception as e:
            logger.error(f"❌ Erreur critique lors du traitement de l'update: {e}")
