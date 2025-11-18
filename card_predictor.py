# card_predictor.py

"""
Card prediction logic for Joker's Telegram Bot - simplified for webhook deployment
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any, Set
import time
import os
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"] 
CARD_SYMBOLS = [r"♠️", r"♥️", r"♦️", r"♣️", r"❤️"] 

# ---------- FONCTIONS UTILITAIRES ----------

def extract_total_points(msg: str) -> Optional[int]:
    """Extrait le total des points #T."""
    m = re.search(r'#T(\d+)', msg)
    return int(m.group(1)) if m else None

# ---------- CLASSE CARDPREDICTOR ----------

class CardPredictor:
    """Gère la logique de prédiction de carte Dame (Q) et la vérification."""

    def __init__(self):
        # Données de persistance (Prédictions et messages)
        self.predictions = self._load_data('predictions.json') 
        self.processed_messages = self._load_data('processed.json', is_set=True) 
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True)
        
        # Configuration dynamique des canaux
        self.config_data = self._load_data('channels_config.json')
        self.target_channel_id = self.config_data.get('target_channel_id', None)
        self.prediction_channel_id = self.config_data.get('prediction_channel_id', None)
        
        # --- Logique INTER (N-2 -> Q à N) ---
        self.sequential_history: Dict[int, Dict] = self._load_data('sequential_history.json') 
        self.inter_data: List[Dict] = self._load_data('inter_data.json') 
        
        # Statut et Règles
        self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True)
        self.smart_rules = self._load_data('smart_rules.json') # Stocke les Top 3 actifs
        self.prediction_cooldown = 30 
        
        # Correction: Assurer que les règles sont recalculées si INTER est actif
        if self.is_inter_mode_active and not self.smart_rules:
             self.analyze_and_set_smart_rules(initial_load=True) 

    # --- Persistance des Données (JSON) ---
    def _load_data(self, filename: str, is_set: bool = False, is_scalar: bool = False) -> Any:
        """Charge les données depuis un fichier JSON."""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                if is_set:
                    return set(data)
                if is_scalar:
                    if filename == 'inter_mode_status.json':
                        return data.get('active', False)
                    return float(data) if isinstance(data, (int, float)) else data
                
                if filename == 'sequential_history.json': 
                    return {int(k): v for k, v in data.items()}
                
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            if is_set: return set()
            if is_scalar and filename == 'inter_mode_status.json': return False
            if is_scalar: return 0.0
            if filename == 'inter_data.json' or filename == 'smart_rules.json': return []
            if filename == 'sequential_history.json' or filename == 'predictions.json': return {}
            return {}
        except Exception as e:
             logger.error(f"❌ Erreur critique de chargement de {filename}: {e}")
             return set() if is_set else (False if filename == 'inter_mode_status.json' else ([] if filename == 'inter_data.json' else {}))

    def _save_data(self, data: Any, filename: str):
        """Sauvegarde les données dans un fichier JSON."""
        if filename == 'inter_mode_status.json':
            data_to_save = {'active': self.is_inter_mode_active}
        elif isinstance(data, set):
            data_to_save = list(data)
        else:
            data_to_save = data
            
        try:
            with open(filename, 'w') as f:
                json.dump(data_to_save, f, indent=4)
        except Exception as e:
            logger.error(f"❌ Erreur critique de sauvegarde de {filename}: {e}. Problème de permissions ou de disque.")

    def _save_all_data(self):
        """Sauvegarde tous les états persistants."""
        self._save_data(self.predictions, 'predictions.json')
        self._save_data(self.processed_messages, 'processed.json')
        self._save_data(self.last_prediction_time, 'last_prediction_time.json')
        self._save_data(self.inter_data, 'inter_data.json')
        self._save_data(self.sequential_history, 'sequential_history.json')
        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')

    def _save_channels_config(self):
        """Sauvegarde les IDs de canaux dans channels_config.json."""
        self.config_data['target_channel_id'] = self.target_channel_id
        self.config_data['prediction_channel_id'] = self.prediction_channel_id
        self._save_data(self.config_data, 'channels_config.json')

    def set_channel_id(self, channel_id: int, channel_type: str):
        if channel_type == 'source':
            self.target_channel_id = channel_id
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
        else:
            return False
            
        self._save_channels_config()
        return True

    # --- Logique d'Extraction ---
    def extract_game_number(self, message: str) -> Optional[int]:
        """Extrait le numéro du jeu, reconnaissant #N et #n."""
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE) or re.search(r'🔵(\d+)🔵', message)
        return int(match.group(1)) if match else None

    def extract_first_parentheses_content(self, message: str) -> Optional[str]:
        """Extrait le contenu de la première parenthèse."""
        pattern = r'\(([^)]*)\)' 
        match = re.search(pattern, message)
        return match.group(1).strip() if match else None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Extrait la valeur et le costume des cartes."""
        card_details = []
        normalized_content = content.replace("❤️", "♥️")
        card_pattern = r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)'
        matches = re.findall(card_pattern, normalized_content, re.IGNORECASE)
        for value, costume in matches:
            card_details.append((value.upper(), costume))
        return card_details

    def get_first_two_cards(self, content: str) -> List[str]:
        """Renvoie les deux premières cartes pour le déclencheur INTER."""
        card_details = self.extract_card_details(content)
        first_two = card_details[:2]
        return [f"{v}{c}" for v, c in first_two]

    def check_value_Q_in_first_parentheses(self, message: str) -> Optional[Tuple[str, str]]:
        """Vérifie si la Dame (Q) est dans le premier groupe et retourne sa valeur/couleur."""
        first_parentheses_content = self.extract_first_parentheses_content(message)
        if not first_parentheses_content:
            return None
        card_details = self.extract_card_details(first_parentheses_content)
        for value, costume in card_details:
            if value == "Q":
                return (value, costume)
        return None
    
    def count_absence_q(self) -> int:
        """Règle 5: Compte le nombre de jeux consécutifs sans résultat Q depuis le dernier Q."""
        if not self.inter_data:
            return len(self.sequential_history)
        
        # Trouver le numéro du dernier jeu où Q a été trouvé
        last_q_game = max(e['numero_resultat'] for e in self.inter_data)
        
        # Compte le nombre d'entrées dans l'historique séquentiel (jeux joués)
        # dont le numéro est supérieur au dernier résultat Q connu.
        recent_games = [g for g in self.sequential_history if g > last_q_game]
        return len(recent_games)

    # --- Logique INTER (Mode Intelligent) ---
    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (Déclencheur à N-2, Dame Q à N) selon la logique séquentielle."""
        first_group_content = self.extract_first_parentheses_content(message)
        if not first_group_content:
            return

        # 1. ENREGISTRER LE JEU ACTUEL DANS L'HISTORIQUE SÉQUENTIEL (N)
        first_two_cards = self.get_first_two_cards(first_group_content)
        if len(first_two_cards) == 2:
            self.sequential_history[game_number] = {
                'cartes': first_two_cards,
                'date': datetime.now().isoformat()
            }
        
        # 2. VÉRIFIER SI CE JEU (N) EST LE RÉSULTAT (Dame Q)
        q_card_details = self.check_value_Q_in_first_parentheses(message)
        
        if q_card_details:
            n_minus_2_game = game_number - 2
            trigger_entry = self.sequential_history.get(n_minus_2_game)
            
            if trigger_entry:
                trigger_cards = trigger_entry['cartes']
                is_duplicate = any(entry.get('numero_resultat') == game_number for entry in self.inter_data)
                
                if not is_duplicate:
                    new_entry = {
                        'numero_resultat': game_number,
                        'declencheur': trigger_cards,
                        'numero_declencheur': n_minus_2_game,
                        'carte_q': f"{q_card_details[0]}{q_card_details[1]}",
                        'date_resultat': datetime.now().isoformat()
                    }
                    self.inter_data.append(new_entry)
                    self._save_all_data() 
        
        # 4. NETTOYAGE: Supprimer les entrées très anciennes
        obsolete_game_limit = game_number - 50 
        self.sequential_history = {
            num: entry for num, entry in self.sequential_history.items() if num >= obsolete_game_limit
        }

    def analyze_and_set_smart_rules(self, initial_load: bool = False) -> List[str]:
        """Analyse l'historique et définit les 3 règles les plus fréquentes."""
        declencheur_counts = {}
        for data in self.inter_data:
            declencheur_key = tuple(data['declencheur']) 
            declencheur_counts[declencheur_key] = declencheur_counts.get(declencheur_key, 0) + 1

        sorted_declencheurs = sorted(
            declencheur_counts.items(), 
            key=lambda item: item[1], 
            reverse=True
        )

        top_3 = [
            {'cards': list(declencheur), 'count': count} 
            for declencheur, count in sorted_declencheurs[:3]
        ]
        self.smart_rules = top_3
        
        if top_3:
            self.is_inter_mode_active = True
        elif not initial_load:
            self.is_inter_mode_active = False 

        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')
            
        return [f"{cards['cards'][0]} {cards['cards'][1]} (x{cards['count']})" for cards in top_3]

    def get_inter_status(self) -> Tuple[str, Optional[Dict]]:
        # ... (Logique de get_inter_status inchangée par la demande de modification) ...
        # (J'ai conservé cette méthode telle qu'elle est dans le fichier pour l'exhaustivité)
        status_lines = ["**📋 HISTORIQUE D'APPRENTISSAGE INTER 🧠**\n"]
        total_collected = len(self.inter_data) 
        
        status_lines.append(f"**Mode Intelligent Actif:** {'✅ OUI' if self.is_inter_mode_active else '❌ NON'}")
        status_lines.append(f"**Historique Q collecté:** **{total_collected} entrées.**\n")

        if total_collected > 0:
            status_lines.append("**Derniers Enregistrements (N-2 → Q à N):**")
            for entry in self.inter_data[-10:]:
                declencheur_str = f"{entry['declencheur'][0]} {entry['declencheur'][1]}"
                line = (
                    f"• N{entry['numero_resultat']} ({entry['carte_q']}) "
                    f"→ Déclencheur N{entry['numero_declencheur']} ({declencheur_str})"
                )
                status_lines.append(line)
        else:
             status_lines.append("\n*Aucun historique de Dame (Q) collecté. Le bot ne peut pas créer de règles intelligentes.*")

        status_lines.append("\n---\n")
        
        if self.is_inter_mode_active and self.smart_rules:
            status_lines.append("**🎯 Règles Actives (Top 3 Déclencheurs):**")
            for rule in self.smart_rules:
                status_lines.append(f"- {rule['cards'][0]} {rule['cards'][1]} (x{rule['count']})")
            status_lines.append("\n---")


        if total_collected > 0:
            if self.is_inter_mode_active:
                 apply_button_text = f"🔄 Re-analyser et appliquer (Actif)"
            else:
                 apply_button_text = f"✅ Appliquer Règle Intelligente ({total_collected} entrées)"

            keyboard = {'inline_keyboard': [
                [{'text': apply_button_text, 'callback_data': 'inter_apply'}],
                [{'text': "➡️ Règle par Défaut (Ignorer l'historique)", 'callback_data': 'inter_default'}]
            ]}
        else:
            keyboard = None 
            status_lines.append("*Aucune action disponible. Attendez plus de données.*")

        return "\n".join(status_lines), keyboard

    def can_make_prediction(self) -> bool:
        """Vérifie la période de refroidissement."""
        if not self.last_prediction_time:
            return True
        return time.time() > (self.last_prediction_time + self.prediction_cooldown)

    # --- MÉTHODES DE FILTRAGE ---
    def has_pending_indicators(self, message: str) -> bool:
        return '🕐' in message or '⏰' in message
        
    def has_completion_indicators(self, message: str) -> bool:
        return '✅' in message or '🔰' in message
    # ----------------------------


    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """Détermine si une prédiction doit être faite. Retourne (doit_prédire, numéro_jeu, valeur_prédite, confiance)."""
        if not self.target_channel_id:
             return False, None, None, None
             
        game_number = self.extract_game_number(message)
        if not game_number:
            return False, None, None, None

        # --- ÉTAPE CRITIQUE: Collecte de données pour INTER ---
        self.collect_inter_data(game_number, message) 
        # ----------------------------------------------------
        
        # 1. BLOCAGE IMMEDIAT si le message est en attente (🕐/⏰)
        if self.has_pending_indicators(message):
            return False, None, None, None
        
        # 2. VÉRIFICATION STRICTE DE FINALISATION (Doit avoir ✅ ou 🔰)
        if not self.has_completion_indicators(message):
            return False, None, None, None
            
        predicted_value = None
        confidence = None # <-- NOUVEAU: Initialisation de la confiance
        
        first_group_content = self.extract_first_parentheses_content(message)
        total_points = extract_total_points(message) # <-- Utilitaire pour Règle 4

        if first_group_content:
            card_details = self.extract_card_details(first_group_content)
            card_values = [v for v, c in card_details]
            
            # Extraction du second groupe
            second_parentheses_pattern = r'\(([^)]*)\)'
            all_matches = re.findall(second_parentheses_pattern, message)
            second_group_content = all_matches[1] if len(all_matches) > 1 else ""
            second_group_details = self.extract_card_details(second_group_content)
            second_group_values = [v for v, c in second_group_details]
            
            
            # --- LOGIQUE DE PRÉDICTION (8 RÈGLES) ---
            
            # Règle 1: LOGIQUE INTER (PRIORITÉ MAX)
            if self.is_inter_mode_active and self.smart_rules:
                current_trigger_cards = self.get_first_two_cards(first_group_content)
                current_trigger_tuple = tuple(current_trigger_cards)
                
                if any(tuple(rule['cards']) == current_trigger_tuple for rule in self.smart_rules):
                    predicted_value, confidence = "Q", "INTER"
            
            # Règle 2: Valet (J) Solitaire (98%)
            elif not predicted_value and card_values.count('J') == 1 and not any(v in ("A", "K", "Q") for v in card_values):
                predicted_value, confidence = "Q", "98%"
            
            # Règle 3: Deux Valets (J) (57%)
            elif not predicted_value and card_values.count('J') >= 2:
                predicted_value, confidence = "Q", "57%"

            # Règle 4: Total des points élevé (#T > 40) (97%)
            elif not predicted_value and total_points is not None and total_points > 40:
                 predicted_value, confidence = "Q", "97%"
            
            # Règle 5: Manque Consécutif de Q (Absence >= 3) (60%)
            elif not predicted_value and self.count_absence_q() >= 3:
                 predicted_value, confidence = "Q", "60%"
            
            # Règle 6: Combinaison 8-9-10 (70%)
            elif not predicted_value:
                set_8_9_10 = {"8", "9", "10"}
                is_8_9_10_combo = set_8_9_10.issubset(card_values) or set_8_9_10.issubset(second_group_values)
                if is_8_9_10_combo:
                    predicted_value, confidence = "Q", "70%"
            
            # Règle 7 & 8 (Bloc 70%)
            elif not predicted_value:
                # 7a: K et J dans G1
                has_k_j_g1 = 'K' in card_values and 'J' in card_values
                # 7b: Tag O ou R
                is_o_r_tag = re.search(r'\b[OR]\b', message)
                
                # 8: Deux groupes faibles consécutifs
                is_current_g1_weak = not any(v in HIGH_VALUE_CARDS for v in card_values)
                is_prev_g1_weak = False
                previous_game_number = game_number - 1
                previous_entry = self.sequential_history.get(previous_game_number)

                if is_current_g1_weak and previous_entry:
                    previous_cards = previous_entry['cartes'] 
                    previous_values = [re.match(r'(\d+|[AKQJ])', c).group(1) for c in previous_cards if re.match(r'(\d+|[AKQJ])', c)]
                    is_prev_g1_weak = not any(v in HIGH_VALUE_CARDS for v in previous_values)

                if has_k_j_g1 or is_o_r_tag or (is_current_g1_weak and is_prev_g1_weak):
                     predicted_value, confidence = "Q", "70%"

        # --- FILTRE FINAL: Q déjà présente ---
        if "Q" in card_values:
            return False, None, None, None

        # --- FILTRE FINAL: Cooldown ---
        if predicted_value and not self.can_make_prediction():
            return False, None, None, None

        if predicted_value:
            message_hash = hash(message)
            if message_hash not in self.processed_messages:
                self.processed_messages.add(message_hash)
                self.last_prediction_time = time.time()
                self._save_all_data()
                return True, game_number, predicted_value, confidence # <-- RETOURNE LA CONFIANCE

        return False, None, None, None
        
        def make_prediction(self, game: int, value: str, confidence: str) -> str:
        target = game + 2
        text = f"🔵{target}🔵:Valeur Q statut :⏳" + (f" ({confidence})" if confidence else "")
        self.pred[target] = {
            "predicted_costume": value,
            "status": "pending",
            "predicted_from": game,
            "verification_count": 0,
            "message_text": text,
            "message_id": None,
            "confidence": confidence, # <-- Assurez-vous qu'il y a une virgule AVANT cette ligne si elle est présente
        } # <-- **C'est ce crochet qui doit être présent et qui a probablement été oublié**
        # ...
