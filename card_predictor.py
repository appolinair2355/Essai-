# card_predictor.py (Partie 1/2)

import re
import logging
import time
import json
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONFIGURATION (À MODIFIER PAR VOS IDs) ---
# NOTE: Remplacer ces valeurs par les IDs réels de vos canaux (commencent par -100...)
TARGET_CHANNEL_ID = -1003424179389  # Canal Source (Baccarat Kouamé)
PREDICTION_CHANNEL_ID = -1003362820311 # Canal de destination pour les prédictions

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"] 

class CardPredictor:
    """Gère la logique de prédiction de carte Dame (Q) et la vérification."""

    def __init__(self):
        self.predictions = self._load_data('predictions.json') 
        self.processed_messages = self._load_data('processed.json', is_set=True) 
        self.is_inter_mode_active = False
        self.inter_data = self._load_data('inter_data.json')
        self.last_two_cards_n_minus_2 = {} 
        self.smart_rules = []
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True)
        self.prediction_cooldown = 30 
        self.target_channel_id = TARGET_CHANNEL_ID
        self.prediction_channel_id = PREDICTION_CHANNEL_ID
        
        if self.inter_data:
            self.analyze_and_set_smart_rules()

    # --- Persistance des Données (JSON) ---
    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False):
        """Charge les données depuis un fichier JSON."""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                if is_set:
                    return set(data)
                if is_scalar:
                    return data
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return set() if is_set else (0 if is_scalar else {})

    def _save_data(self, data, filename: str):
        """Sauvegarde les données dans un fichier JSON."""
        data_to_save = list(data) if isinstance(data, set) else data
        try:
            with open(filename, 'w') as f:
                json.dump(data_to_save, f)
        except Exception as e:
            logger.error(f"Erreur de sauvegarde de {filename}: {e}")

    def _save_all_data(self):
        """Sauvegarde tous les états persistants."""
        self._save_data(self.predictions, 'predictions.json')
        self._save_data(self.processed_messages, 'processed.json')
        self._save_data(self.inter_data, 'inter_data.json')
        self._save_data(self.last_prediction_time, 'last_prediction_time.json')

    # --- Méthodes Utilitaires ---
    def can_make_prediction(self) -> bool:
        """Vérifie le cooldown."""
        return (time.time() - self.last_prediction_time) > self.prediction_cooldown

    def has_pending_indicators(self, message: str) -> bool:
        """Vérifie si le message est en cours d'édition (⏰, 🕐, ▶, ➡️)."""
        pending_symbols = ['⏰', '🕐', '▶', '➡️'] 
        return any(symbol in message for symbol in pending_symbols)

    def extract_game_number(self, message: str) -> Optional[int]:
        """Extrait le numéro du jeu."""
        match = re.search(r'#N(\d+)\.', message)
        if not match:
            match = re.search(r'🔵(\d+)🔵', message)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def extract_first_parentheses_content(self, message: str) -> Optional[str]:
        """Extrait le contenu de la première parenthèse."""
        pattern = r'\(([^)]*)\)' 
        match = re.search(pattern, message)
        if match:
            return match.group(1)
        return None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Extrait la valeur et le costume des cartes."""
        card_details = []
        normalized_content = content.replace("❤️", "♥️")
        card_pattern = r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)'
        matches = re.findall(card_pattern, normalized_content)
        for value, costume in matches:
            card_details.append((value, costume))
        return card_details

    def get_first_two_cards(self, content: str) -> List[str]:
        """Renvoie les deux premières cartes pour le déclencheur INTER."""
        card_details = self.extract_card_details(content)
        first_two = card_details[:2]
        return [f"{v}{c}" for v, c in first_two]

    def check_value_Q_in_first_parentheses(self, message: str) -> bool:
        """Vérifie si la Dame (Q) est dans le premier groupe."""
        normalized_message = message.replace("❤️", "♥️")
        first_parentheses_content = self.extract_first_parentheses_content(normalized_message)
        if not first_parentheses_content:
            return False
        card_details = self.extract_card_details(first_parentheses_content)
        card_values = [v for v, c in card_details]
        return "Q" in card_values
        # card_predictor.py (Partie 2/2) - Continuation de la classe CardPredictor

    # --- Logique INTER (Mode Intelligent) ---
    
    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (Déclencheur à N-2, Dame Q à N)."""
        first_group_content = self.extract_first_parentheses_content(message)
        if not first_group_content:
            return

        first_two_cards = self.get_first_two_cards(first_group_content)
        if len(first_two_cards) == 2:
            self.last_two_cards_n_minus_2[game_number] = first_two_cards

        if self.check_value_Q_in_first_parentheses(message):
            n_minus_2_game = game_number - 2
            trigger_cards = self.last_two_cards_n_minus_2.get(n_minus_2_game)
            
            if trigger_cards:
                new_entry = {
                    'numero': game_number,
                    'declencheur': trigger_cards,
                    'date': datetime.now().isoformat()
                }
                self.inter_data.append(new_entry)
                self._save_all_data()
                
            if n_minus_2_game in self.last_two_cards_n_minus_2:
                del self.last_two_cards_n_minus_2[n_minus_2_game]

    def analyze_and_set_smart_rules(self) -> List[str]:
        """Analyse les données INTER pour trouver les 3 déclencheurs les plus fréquents."""
        declencheur_counts = {}
        for data in self.inter_data:
            declencheur_key = tuple(data['declencheur']) 
            declencheur_counts[declencheur_key] = declencheur_counts.get(declencheur_key, 0) + 1

        sorted_declencheurs = sorted(
            declencheur_counts.items(), 
            key=lambda item: item[1], 
            reverse=True
        )

        top_3 = [list(declencheur) for declencheur, count in sorted_declencheurs[:3]]
        self.smart_rules = top_3
        self.is_inter_mode_active = True
        return [f"{cards[0]} {cards[1]} (x{declencheur_counts[tuple(cards)]})" for cards in top_3]

    def get_inter_status(self) -> str:
        """Génère le statut pour la commande /inter."""
        status_lines = ["**📊 STATUT COMMANDE /INTER 🧠**\n"]
        status_lines.append(f"**Mode Intelligent Actif:** {'✅ OUI' if self.is_inter_mode_active else '❌ NON'}")
        status_lines.append(f"**Historique des Dames (Q) collecté:** {len(self.inter_data)} entrées.")
        
        if self.smart_rules:
            status_lines.append("\n**🎯 Règles Actives (Top 3 Déclencheurs):**")
            for rule in self.smart_rules:
                status_lines.append(f"- {rule[0]} {rule[1]}")
        else:
             status_lines.append("\n*Aucune règle intelligente active ou données insuffisantes (Min 3).*")

        return "\n".join(status_lines)


    # --- Logique de Prédiction ---

    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Détermine si une prédiction de Dame (Q) doit être faite à N+2."""
        game_number = self.extract_game_number(message)
        if not game_number:
            return False, None, None

        if self.has_pending_indicators(message):
            return False, None, None
        
        if '#R' in message or '#X' in message:
            return False, None, None
            
        self.collect_inter_data(game_number, message)

        target_game = game_number + 2
        if target_game in self.predictions and self.predictions[target_game].get('status') == 'pending':
             return False, None, None
        
        predicted_value = None
        first_group_content = self.extract_first_parentheses_content(message)

        if first_group_content:
            card_details = self.extract_card_details(first_group_content)
            
            # 1. RÈGLE N°1: MODE INTELLIGENT (Prioritaire)
            if self.is_inter_mode_active and self.smart_rules:
                current_trigger = self.get_first_two_cards(first_group_content)
                if current_trigger and current_trigger in self.smart_rules:
                    predicted_value = "Q"
            
            # 2. RÈGLES PAR DÉFAUT
            if not predicted_value:
                card_values = [v for v, c in card_details]
                
                if card_values.count('J') >= 2:
                    predicted_value = "Q"

                elif card_values.count('J') == 1:
                    second_parentheses_pattern = r'\(([^)]*)\)'
                    all_matches = re.findall(second_parentheses_pattern, message)
                    second_group_content = all_matches[1] if len(all_matches) > 1 else ""

                    second_group_details = self.extract_card_details(second_group_content)
                    second_group_values = [v for v, c in second_group_details]

                    has_high_value_in_second = any(v in HIGH_VALUE_CARDS for v in second_group_values)
                    
                    if not has_high_value_in_second:
                        predicted_value = "Q"

        if predicted_value and not self.can_make_prediction():
            return False, None, None

        if predicted_value:
            message_hash = hash(message)
            if message_hash not in self.processed_messages:
                self.processed_messages.add(message_hash)
                self.last_prediction_time = time.time()
                self._save_all_data()
                return True, game_number, predicted_value

        return False, None, None

    def make_prediction(self, game_number: int, predicted_costume: str) -> str:
        """Crée et stocke le message de prédiction."""
        target_game = game_number + 2
        prediction_text = f"🔵{target_game}🔵:Valeur Q statut :⏳"

        self.predictions[target_game] = {
            'predicted_costume': 'Q',
            'status': 'pending',
            'predicted_from': game_number,
            'verification_count': 0,
            'message_text': prediction_text,
            'message_id': None 
        }
        self._save_all_data()
        return prediction_text

    # --- Logique de Vérification ---

    def _verify_prediction_common(self, text: str, is_edited: bool = False) -> Optional[Dict]:
        """Vérifie la prédiction de la Dame (Q) à offsets 0, 1, 2."""
        game_number = self.extract_game_number(text)
        if not game_number:
            return None

        if self.has_pending_indicators(text):
            return None

        if not self.predictions:
            return None

        for predicted_game in sorted(self.predictions.keys()):
            prediction = self.predictions[predicted_game]

            if prediction.get('status') != 'pending' or prediction.get('predicted_costume') != 'Q':
                continue

            verification_offset = game_number - predicted_game
            
            if 0 <= verification_offset <= 2:
                status_symbol_map = {0: "✅0️⃣", 1: "✅1️⃣", 2: "✅2️⃣"}
                q_found = self.check_value_Q_in_first_parentheses(text)
                
                if q_found:
                    status_symbol = status_symbol_map[verification_offset]
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :{status_symbol}"
                    
                    prediction['status'] = 'correct'
                    prediction['verification_count'] = verification_offset
                    prediction['final_message'] = updated_message
                    self._save_all_data()
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'new_message': updated_message,
                    }
                elif verification_offset == 2 and not q_found:
                    # ÉCHEC à offset +2 - MARQUER ❌
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :❌"

                    prediction['status'] = 'failed'
                    prediction['final_message'] = updated_message
                    self._save_all_data()

                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'new_message': updated_message,
            }
        
