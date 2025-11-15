"""
Logique de prédiction et gestion de l'état (Mode Intelligent, Historique)
Ce module contient l'objet CardPredictor, le cœur de la stratégie.
"""

import re
import logging
from typing import Optional, Dict, Tuple
import time
import os

logger = logging.getLogger(__name__)

# --- Configuration de l'État ---

class CardPredictor:
    """Handles card prediction logic and state management."""

    def __init__(self):
        self.predictions = {} 
        self.processed_messages = set() 
        self.last_prediction_time = 0.0
        self.last_dame_prediction = None 

        # État du mode intelligent
        self.consecutive_failures = 0
        self.intelligent_mode_active = False
        self.MAX_FAILURES_BEFORE_INTELLIGENT_MODE = 2

        # Gestion de l'historique
        self.draw_history = {} 
        self.history_limit = 10

        # Suivi des messages en attente (⏰)
        self.pending_messages = {}  # {game_number: message_data} 

    # --- Utilitaires d'Extraction ---

    def extract_game_number(self, message: str) -> Optional[int]:
        """Extrait le numéro de jeu du message comme #n744 ou #N744."""
        pattern = r'#[nN](\d+)\.?' 
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
        return None

    def extract_first_group_content(self, message: str) -> Optional[str]:
        """Extrait le contenu à l'intérieur du premier groupe de parenthèses."""
        pattern = r'\(.*?\)'
        match = re.search(pattern, message)
        if match:
            return match.group(0).strip('()')
        return None

    def extract_second_group_content(self, message: str) -> Optional[str]:
        """Extrait le contenu du deuxième groupe de parenthèses."""
        pattern = r'\(.*?\)'
        matches = re.findall(pattern, message)
        if len(matches) >= 2:
            return matches[1].strip('()')
        return None

    def extract_first_two_cards_with_value(self, message: str) -> Optional[str]:
        """Extrait les deux premières cartes avec leur couleur/valeur du premier groupe."""
        pattern_group = r'\(.*?\)'
        match_group = re.search(pattern_group, message)
        if not match_group:
            return None

        content = match_group.group(0).strip('()')
        card_pattern = r'[AKQJ\d]+[♥️♠️♦️♣️❤️]'
        cards = re.findall(card_pattern, content)

        if len(cards) >= 2:
            return cards[0] + cards[1]

        return None

    def extract_figure_signals(self, message: str) -> Dict[str, bool]:
        """Détecte la présence de figures (J, K, A)."""
        signals = {'J': False, 'K': False, 'A': False}
        if re.search(r'\b[JjVv]\b', message) or 'Valet' in message: 
             signals['J'] = True
        if re.search(r'\b[KkRr]\b', message) or 'Roi' in message:
             signals['K'] = True
        if re.search(r'\b[Aa]\b', message) or 'As' in message: 
             signals['A'] = True
        return signals

    def check_dame_in_first_group(self, message: str) -> bool:
        """Vérifie la présence de la Dame (Q) dans le premier groupe."""
        first_group_content = self.extract_first_group_content(message)
        if not first_group_content:
            return False
        return bool(re.search(r'\b[Qq]\b|Dame', first_group_content))

    def is_pending_message(self, text: str) -> bool:
        """Vérifie si le message est en attente (contient ⏰)."""
        return '⏰' in text

    def has_completion_indicators(self, text: str) -> bool:
        """Vérifie si le message source est finalisé (contient des indicateurs de fin)."""
        # Messages finalisés
        COMPLETION_INDICATORS = ['✅', '🔰']

        # Vérifier si le message est finalisé
        return any(indicator in text for indicator in COMPLETION_INDICATORS)

    # --- Logique de Prédiction ---

    def check_dame_rule(self, signals: Dict[str, bool], first_group_content: str) -> Optional[str]:
        """Applique la Stratégie de Mise Dame (Q) : détermine la règle à appliquer.
        Mode Intelligent : utilise 2 déclencheurs fréquents les plus performants.
        """

        J, K, A = signals['J'], signals['K'], signals['A']

        # DÉCLENCHEUR 1 : Double Valet (JJ) → N+2 (le plus fréquent)
        if re.search(r'J.*J', first_group_content, re.IGNORECASE):
             return "Q_INTELLIGENT_JJ" 

        # DÉCLENCHEUR 2 : Valet seul (J sans K ni A) → N+2
        if J and not K and not A:
            return "Q_INTELLIGENT_J" 

        return None 

    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Vérifie si une prédiction de Dame doit être faite."""
        game_number = self.extract_game_number(message)
        if not game_number: return False, None, None

        signals = self.extract_figure_signals(message)
        first_group = self.extract_first_group_content(message)

        if not first_group: return False, None, None

        # MODE INTELLIGENT ACTIF : Utiliser 2 déclencheurs fréquents
        if self.intelligent_mode_active:
            dame_prediction = self.check_dame_rule(signals, first_group)

            if dame_prediction:
                predicted_value = f"Q:{dame_prediction}"
                message_hash = hash(message)
                if message_hash not in self.processed_messages:
                    self.processed_messages.add(message_hash)
                    self.last_prediction_time = time.time()
                    self.last_dame_prediction = predicted_value
                    return True, game_number, predicted_value

        # MODE PAR DÉFAUT : 2 règles uniquement
        else:
            should_predict_default = False
            predicted_rule = None

            # Extraire le contenu du deuxième groupe
            second_group = self.extract_second_group_content(message)
            
            # Vérifier l'absence de figures (A, K, Q, J) dans le deuxième groupe
            has_figures_in_second_group = False
            if second_group:
                has_figures_in_second_group = bool(re.search(r'[AKQJ]', second_group, re.IGNORECASE))

            # RÈGLE 1: Deux J dans le premier groupe → Q au N+2
            if re.search(r'J.*J', first_group, re.IGNORECASE):
                should_predict_default = True
                predicted_rule = "Q_DEFAULT_JJ"
            
            # RÈGLE 2: Un seul J dans le premier groupe ET absence de A,K,Q,J dans le deuxième groupe
            elif re.search(r'\bJ\b', first_group, re.IGNORECASE) and not has_figures_in_second_group:
                # Vérifier qu'il n'y a qu'un seul J dans le premier groupe
                j_count = len(re.findall(r'\bJ\b', first_group, re.IGNORECASE))
                if j_count == 1:
                    should_predict_default = True
                    predicted_rule = "Q_DEFAULT_J_CLEAN"

            if should_predict_default and predicted_rule:
                predicted_value = f"Q:{predicted_rule}"
                message_hash = hash(message)
                if message_hash not in self.processed_messages:
                    self.processed_messages.add(message_hash)
                    self.last_prediction_time = time.time()
                    self.last_dame_prediction = predicted_value
                    return True, game_number, predicted_value

        return False, None, None

    def make_prediction(self, game_number: int, predicted_value_or_costume: str) -> Dict:
        """Crée l'objet de prédiction et génère le message."""
        dame_rule = predicted_value_or_costume.split(':')[1]

        # Règles du Mode Intelligent - 2 Déclencheurs Fréquents
        if dame_rule == "Q_INTELLIGENT_JJ":
             target_game = game_number + 2  # Double Valet → N+2
             prediction_text = f"🎯{target_game}🎯: Dame (Q) statut :⏳"

        elif dame_rule == "Q_INTELLIGENT_J":
             target_game = game_number + 2  # Valet seul → N+2
             prediction_text = f"🎯{target_game}🎯: Dame (Q) statut :⏳"

        # Règles par Défaut - 2 règles uniquement
        elif dame_rule == "Q_DEFAULT_JJ":
             target_game = game_number + 2  # Deux J dans le premier groupe → N+2
             prediction_text = f"🎯{target_game}🎯: Dame (Q) statut :⏳"

        elif dame_rule == "Q_DEFAULT_J_CLEAN":
             target_game = game_number + 2  # Un J dans 1er groupe, pas de figures dans 2ème → N+2
             prediction_text = f"🎯{target_game}🎯: Dame (Q) statut :⏳"

        else:
             target_game = game_number + 2
             prediction_text = f"🎯{target_game}🎯: Dame (Q) statut :⏳"

        self.predictions[target_game] = {
            'predicted_costume_or_value': predicted_value_or_costume,
            'status': 'pending',
            'predicted_from': game_number,
            'message_text': prediction_text,
            'is_dame_prediction': predicted_value_or_costume.startswith('Q:'),
            'verification_stopped': False,  # Flag pour arrêter la vérification
            'prediction_message_id': None # Initialisé à None, sera mis à jour par le bot
        }

        return {'text': prediction_text, 'target_game': target_game}


    def verify_prediction(self, text: str, message_id: Optional[int] = None) -> Optional[Dict]:
        """Vérifie si une prédiction en attente correspond au tirage actuel.
        ARRÊT immédiat après chaque succès ou échec final.
        La Dame (Q) est recherchée UNIQUEMENT dans le premier groupe.
        """
        game_number = self.extract_game_number(text)
        if not game_number: return None

        if not self.has_completion_indicators(text):
            return None

        if not self.predictions: return None

        for predicted_game in sorted(self.predictions.keys()):
            prediction = self.predictions[predicted_game]

            # Si la vérification a déjà été arrêtée pour cette prédiction, passer
            if prediction.get('verification_stopped', False):
                continue

            if prediction.get('status') != 'pending': 
                continue

            verification_offset = game_number - predicted_game
            is_dame_prediction = prediction.get('is_dame_prediction', False) 

            # Traitement uniquement si c'est une prédiction de Dame
            if not is_dame_prediction: continue

            if verification_offset < 0: continue # Le tirage n'est pas encore arrivé

            # Vérifier la présence de Q UNIQUEMENT dans le premier groupe
            costume_or_value_found = self.check_dame_in_first_group(text)
            original_message = prediction.get('message_text')

            # Séquence de vérification avec ARRÊT après chaque succès
            if verification_offset == 0:
                # Numéro prédit exact (N)
                if costume_or_value_found:
                    # Q trouvée → ✅0️⃣ et ARRÊT
                    updated_message = original_message.replace("statut :⏳", "statut :✅0️⃣")
                    prediction['status'] = 'correct'
                    prediction['verification_stopped'] = True  # ARRÊT
                    self.consecutive_failures = 0
                    return {
                        'type': 'edit_message', 'predicted_game': predicted_game, 
                        'new_message': updated_message, 'original_message': original_message,
                        'prediction_message_id': message_id
                    }
                # Pas trouvé, continuer à N+1
                continue

            elif verification_offset == 1:
                # Prédit +1 (N+1)
                if costume_or_value_found:
                    # Q trouvée → ✅1️⃣ et ARRÊT
                    updated_message = original_message.replace("statut :⏳", "statut :✅1️⃣")
                    prediction['status'] = 'correct'
                    prediction['verification_stopped'] = True  # ARRÊT
                    self.consecutive_failures = 0
                    return {
                        'type': 'edit_message', 'predicted_game': predicted_game, 
                        'new_message': updated_message, 'original_message': original_message,
                        'prediction_message_id': message_id
                    }
                # Pas trouvé, continuer à N+2
                continue

            elif verification_offset == 2:
                # Prédit +2 (N+2)
                if costume_or_value_found:
                    # Q trouvée → ✅2️⃣ et ARRÊT
                    updated_message = original_message.replace("statut :⏳", "statut :✅2️⃣")
                    prediction['status'] = 'correct'
                    prediction['verification_stopped'] = True  # ARRÊT
                    self.consecutive_failures = 0
                    return {
                        'type': 'edit_message', 'predicted_game': predicted_game, 
                        'new_message': updated_message, 'original_message': original_message,
                        'prediction_message_id': message_id
                    }
                # Pas trouvé, continuer à N+3
                continue

            elif verification_offset == 3:
                # Prédit +3 (dernière chance)
                if costume_or_value_found:
                    # Q trouvée → ✅3️⃣ et ARRÊT
                    updated_message = original_message.replace("statut :⏳", "statut :✅3️⃣")
                    prediction['status'] = 'correct'
                    prediction['verification_stopped'] = True  # ARRÊT
                    self.consecutive_failures = 0
                    return {
                        'type': 'edit_message', 'predicted_game': predicted_game, 
                        'new_message': updated_message, 'original_message': original_message,
                        'prediction_message_id': message_id
                    }
                else:
                    # ÉCHEC FINAL → ❌ et ARRÊT
                    updated_message = original_message.replace("statut :⏳", "statut :❌")
                    prediction['status'] = 'failed'
                    prediction['verification_stopped'] = True  # ARRÊT
                    self.consecutive_failures += 1

                    # Déclenchement du prompt /inter pour l'administrateur
                    if self.consecutive_failures == self.MAX_FAILURES_BEFORE_INTELLIGENT_MODE:
                        return {'type': 'fail_threshold_reached'} 

                    return {
                        'type': 'edit_message', 'predicted_game': predicted_game, 
                        'new_message': updated_message, 'original_message': original_message,
                        'prediction_message_id': message_id
                    }

            elif verification_offset > 3:
                # Au-delà de +3, marquer comme échec et ARRÊT
                updated_message = original_message.replace("statut :⏳", "statut :❌")
                prediction['status'] = 'failed'
                prediction['verification_stopped'] = True  # ARRÊT
                self.consecutive_failures += 1

                if self.consecutive_failures == self.MAX_FAILURES_BEFORE_INTELLIGENT_MODE:
                    return {'type': 'fail_threshold_reached'}

                return {
                    'type': 'edit_message', 'predicted_game': predicted_game, 
                    'new_message': updated_message, 'original_message': original_message,
                    'prediction_message_id': message_id
                }

        return None

card_predictor = CardPredictor()