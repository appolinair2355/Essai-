# card_predictor.py

"""
Logique de prédiction de carte Joker pour Bot Telegram
Ce fichier contient la classe CardPredictor complète.
"""
import re
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set
import time
import os
import json

# Configuration du logger pour le débogage
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"] 

# ---------- FONCTIONS UTILITAIRES D'EXTRACTION (Hors classe) ----------

def extract_total_points(msg: str) -> Optional[int]:
    """Extrait le total des points #T."""
    m = re.search(r'#T(\d+)', msg)
    return int(m.group(1)) if m else None

# ---------- CLASSE CARDPREDICTOR ----------

class CardPredictor:
    
    def __init__(self):
        # Données de persistance
        self.predictions : Dict[int, Dict] = self._load_data('predictions.json') 
        self.processed_messages : Set[int] = self._load_data('processed.json', is_set=True) 
        self.last_prediction_time : float = self._load_data('last_prediction_time.json', is_scalar=True)
        
        # Configuration des canaux (Fix pour les attributs manquants)
        self.config_data = self._load_data('channels_config.json')
        self.target_channel_id : Optional[int] = self.config_data.get('target_channel_id', None)
        self.prediction_channel_id : Optional[int] = self.config_data.get('prediction_channel_id', None)
        
        # Logique INTER & Historique
        self.sequential_history : Dict[int, Dict] = self._load_data("sequential_history.json", is_sequential_history=True)
        self.inter_data : List[Dict]      = self._load_data("inter_data.json", is_list=True)
        self.is_inter_mode_active : bool = self._load_data("inter_mode_status.json", is_inter_active=True)
        self.smart_rules : List[Dict]      = self._load_data("smart_rules.json", is_list=True)
        self.prediction_cooldown = 30
        
        # Initialisation ou recalcul des règles si nécessaire
        if not os.path.exists('channels_config.json') and (self.target_channel_id is None or self.prediction_channel_id is None):
            self._save_data(self.config_data, 'channels_config.json')

        if self.is_inter_mode_active and not self.smart_rules and self.inter_data:
             self.analyze_and_set_smart_rules(initial_load=True) 

    # ---------- GESTION DES DONNÉES (Persistance JSON) ----------

    def _load_data(self, file: str, is_set: bool = False, is_scalar: bool = False, is_list: bool = False, is_inter_active: bool = False, is_sequential_history: bool = False) -> Any:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                if is_set: return set(data)
                if is_scalar: 
                    if file == 'inter_mode_status.json':
                        return data.get("active", False)
                    return float(data)
                if is_inter_active: return data.get("active", False)
                if is_sequential_history: return {int(k): v for k, v in data.items()}
                return data
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            if is_set: return set()
            if is_scalar: return 0.0
            if is_inter_active: return False
            if is_list: return []
            if file == 'channels_config.json': return {}
            return {}
        except Exception as e:
            logger.error(f"❌ Erreur _load_data {file} : {e}")
            return set() if is_set else (False if is_inter_active else ([] if is_list else ({})))

    def _save_data(self, data: Any, file: str):
        if file == 'inter_mode_status.json':
            out = {'active': data}
        elif isinstance(data, set):
            out = list(data)
        else:
            out = data
                
        try:
            with open(file, "w") as f: 
                json.dump(out, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Erreur _save_data {file} : {e}")

    def _save_all_data(self):
        for attr_name, file in [
            ("predictions", "predictions.json"),
            ("processed_messages", "processed.json"),
            ("last_prediction_time", "last_prediction_time.json"),
            ("sequential_history", "sequential_history.json"),
            ("inter_data", "inter_data.json"),
            ("is_inter_mode_active", "inter_mode_status.json"),
            ("smart_rules", "smart_rules.json"),
        ]: 
            self._save_data(getattr(self, attr_name), file)
            
        self.config_data['target_channel_id'] = self.target_channel_id
        self.config_data['prediction_channel_id'] = self.prediction_channel_id
        self._save_data(self.config_data, 'channels_config.json')

    def can_make_prediction(self) -> bool:
        """Vérifie la période de refroidissement."""
        if not self.last_prediction_time:
            return True
        return time.time() > (self.last_prediction_time + self.prediction_cooldown)

    # --- COMMANDES D'ADMINISTRATION (CORRECTION DES ATTRIBUTS MANQUANTS) ---
    
    def set_channel_id(self, channel_id: int, channel_type: str) -> bool:
        """Définit les IDs de canal Source ou Prédiction."""
        if channel_type == 'source':
            self.target_channel_id = channel_id
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
        else:
            return False
            
        self._save_all_data()
        return True

    def get_inter_status(self) -> Tuple[str, Optional[Dict]]:
        """Génère le message et le clavier pour la commande /inter."""
        status_lines = ["**📋 STATUT D'APPRENTISSAGE INTER (N-2 → Q à N) 🧠**\n"]
        total_collected = len(self.inter_data) 
        
        status_lines.append(f"**Mode Intelligent Actif:** {'✅ OUI' if self.is_inter_mode_active else '❌ NON'}")
        status_lines.append(f"**Historique Q collecté:** **{total_collected} entrées.**\n")

        # Affichage des règles actives
        if self.is_inter_mode_active and self.smart_rules:
            status_lines.append("**🎯 Règles Actives (Top 3 Déclencheurs):**")
            for rule in self.smart_rules:
                cards_str = f"{rule['cards'][0]} {rule['cards'][1]}" if len(rule['cards']) == 2 else "Inconnu"
                status_lines.append(f"- {cards_str} (x{rule['count']})")
            status_lines.append("\n---\n")
        
        # Affichage des enregistrements récents
        if total_collected > 0:
            status_lines.append("**Derniers Enregistrements (N-2 → Q à N):**")
            for entry in self.inter_data[-10:]:
                declencheur = entry.get('declencheur', [])
                # La logique d'affichage est simplifiée ici pour éviter les erreurs
                declencheur_str = f"{declencheur[0]} {declencheur[1]}" if len(declencheur) == 2 else "Inconnu"
                
                line = (
                    f"• N{entry['numero_resultat']} ← Déclencheur N{entry['numero_declencheur']} ({declencheur_str})"
                )
                status_lines.append(line)
        else:
             status_lines.append("\n*Aucun historique de Dame (Q) collecté.*")

        # GENERATION DU CLAVIER
        keyboard = None 
        if total_collected > 0:
            if self.is_inter_mode_active:
                apply_button_text = f"🔄 Re-analyser et Appliquer ({len(self.smart_rules)} règles)"
                default_button_text = "❌ Désactiver le mode INTER (Passer en Statique)"
            else:
                apply_button_text = f"✅ Activer Mode Intelligent ({total_collected} entrées)"
                default_button_text = "➡️ Règle par Défaut (Actif)"

            keyboard = {'inline_keyboard': [
                [{'text': apply_button_text, 'callback_data': 'inter_apply'}],
                [{'text': default_button_text, 'callback_data': 'inter_default'}]
            ]}
        else:
             # Si total_collected == 0
             status_lines.append("\n*Aucune action disponible. Attendez plus de données.*")

        return "\n".join(status_lines), keyboard

    # --- Logique d'Extraction & Utilitaires ---
    def extract_game_number(self, message: str) -> Optional[int]:
        match = re.search(r'#N(\d+)\.', message, re.IGNORECASE) or re.search(r'🔵(\d+)🔵', message)
        return int(match.group(1)) if match else None

    def extract_first_parentheses_content(self, message: str) -> Optional[str]:
        pattern = r'\(([^)]*)\)' 
        match = re.search(pattern, message)
        return match.group(1).strip() if match else None
        
    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        card_details = []
        normalized_content = content.replace("❤️", "♥️")
        card_pattern = r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)'
        matches = re.findall(card_pattern, normalized_content, re.IGNORECASE)
        for value, costume in matches:
            card_details.append((value.upper(), costume))
        return card_details

    def get_first_two_cards(self, content: str) -> List[str]:
        card_details = self.extract_card_details(content)
        first_two = card_details[:2]
        return [f"{v}{c}" for v, c in first_two]

    def check_value_Q_in_first_parentheses(self, message: str) -> Optional[bool]:
        first_parentheses_content = self.extract_first_parentheses_content(message)
        if not first_parentheses_content: return None
        card_details = self.extract_card_details(first_parentheses_content)
        return any(value == "Q" for value, _ in card_details)
        
    def count_absence_q(self) -> int:
        if not self.inter_data:
            # Si aucune donnée INTER n'existe, on compte depuis le dernier jeu enregistré
            return len(self.sequential_history)
        
        # Récupère le numéro du dernier jeu où Q a été trouvé
        last_q_game = max((e['numero_resultat'] for e in self.inter_data), default=0)
        
        # Compte le nombre de jeux enregistrés depuis ce dernier Q
        recent_games_count = len([g for g in self.sequential_history if g > last_q_game])
        return recent_games_count

    # --- Logique INTER (Apprentissage) ---
    def collect_inter_data(self, game_number: int, message: str):
        """Collecte les données (Déclencheur à N-2, Dame Q à N) selon la logique séquentielle."""
        first_group_content = self.extract_first_parentheses_content(message)
        if not first_group_content: return

        # 1. ENREGISTRER LE JEU ACTUEL DANS L'HISTORIQUE SÉQUENTIEL (N)
        first_two_cards = self.get_first_two_cards(first_group_content)
        if len(first_two_cards) == 2:
            self.sequential_history[game_number] = {
                'cartes': first_two_cards,
                'date': datetime.now().isoformat()
            }
        
        # 2. VÉRIFIER SI CE JEU (N) EST LE RÉSULTAT (Dame Q)
        q_found = self.check_value_Q_in_first_parentheses(message)
        
        if q_found:
            n_minus_2_game = game_number - 2
            trigger_entry = self.sequential_history.get(n_minus_2_game)
            
            # 3. CONDIITIONS D'ENREGISTREMENT
            # - Le déclencheur N-2 doit exister dans l'historique (sinon 0 entrées)
            # - Ce jeu N ne doit pas déjà être dans les données INTER
            if trigger_entry:
                is_duplicate = any(entry.get('numero_resultat') == game_number for entry in self.inter_data)
                
                if not is_duplicate:
                    new_entry = {
                        'numero_resultat': game_number,
                        'declencheur': trigger_entry['cartes'],
                        'numero_declencheur': n_minus_2_game,
                        'carte_q': "Q", 
                        'date_resultat': datetime.now().isoformat()
                    }
                    self.inter_data.append(new_entry)
                    self._save_all_data() 
                    logger.info(f"💾 INTER DATA SUCCESS: Q à N={game_number} enregistré. Déclencheur N-2 trouvé: {trigger_entry['cartes']}")
        
        # 4. NETTOYAGE: Supprimer les entrées très anciennes (par exemple, plus de 50 jeux)
        obsolete_game_limit = game_number - 50 
        self.sequential_history = {
            num: entry for num, entry in self.sequential_history.items() if num >= obsolete_game_limit
        }


    def analyze_and_set_smart_rules(self, initial_load: bool = False):
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
        
        if not initial_load:
            self.is_inter_mode_active = True if top_3 else False

        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')
        
    def set_inter_mode(self, status: bool):
        """Active ou désactive le mode INTER."""
        self.is_inter_mode_active = status
        if status:
            self.analyze_and_set_smart_rules() 
        else:
             self.smart_rules = [] 
        
        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')

    # --- LOGIQUE DE PREDICTION (Les 8 règles) ---
    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """Détermine si une prédiction doit être faite."""
        game_number = self.extract_game_number(message)
        if not game_number: return False, None, None, None

        # --- ÉTAPE CRITIQUE: Collecte de données pour INTER ---
        self.collect_inter_data(game_number, message) 
        
        # 1. FILTRAGE STRICT (Messages en attente ou non finalisés)
        if '🕐' in message or '⏰' in message or not ('✅' in message or '🔰' in message):
            return False, None, None, None
            
        predicted_value = None
        confidence = None 
        
        first_group_content = self.extract_first_parentheses_content(message)
        total_points = extract_total_points(message) 

        if not first_group_content: return False, None, None, None
            
        # Extraction des valeurs des deux groupes
        card_details = self.extract_card_details(first_group_content)
        card_values = [v for v, c in card_details]
        
        second_parentheses_pattern = r'\(([^)]*)\)'
        all_matches = re.findall(second_parentheses_pattern, message)
        second_group_content = all_matches[1] if len(all_matches) > 1 else ""
        second_group_details = self.extract_card_details(second_group_content)
        second_group_values = [v for v, c in second_group_details]
        
        
        # --- LOGIQUE DES 8 RÈGLES ---
        
        # Règle 1: LOGIQUE INTER (PRIORITÉ MAX)
        if self.is_inter_mode_active and self.smart_rules:
            current_trigger_cards = self.get_first_two_cards(first_group_content)
            current_trigger_tuple = tuple(current_trigger_cards)
            
            if any(tuple(rule['cards']) == current_trigger_tuple for rule in self.smart_rules):
                predicted_value, confidence = "Q", "INTER"
        
        # Règle 2: Valet (J) Solitaire (98%)
        elif card_values.count('J') == 1 and not any(v in ("A", "K", "Q") for v in card_values):
            predicted_value, confidence = "Q", "98%"
        
        # Règle 3: Deux Valets (J) (57%)
        elif card_values.count('J') >= 2:
            predicted_value, confidence = "Q", "57%"

        # Règle 4: Total des points élevé (#T > 40) (97%)
        elif total_points is not None and total_points > 40:
             predicted_value, confidence = "Q", "97%"
        
        # Règle 5: Manque Consécutif de Q (Absence >= 3) (60%)
        elif self.count_absence_q() >= 3:
             predicted_value, confidence = "Q", "60%"
        
        # Règle 6: Combinaison 8-9-10 (70%)
        else:
            set_8_9_10 = {"8", "9", "10"}
            is_8_9_10_combo = set_8_9_10.issubset(card_values) or set_8_9_10.issubset(second_group_values)
            if is_8_9_10_combo:
                predicted_value, confidence = "Q", "70%"
        
        # Règle 7 & 8 (Bloc 70%)
        if not predicted_value:
            # 7a: K et J dans G1
            has_k_j_g1 = 'K' in card_values and 'J' in card_values
            # 7b: Tag O ou R
            is_o_r_tag = re.search(r'\b[OR]\b', message)
            
            # 8: Deux groupes faibles consécutifs
            is_current_g1_weak = not any(v in HIGH_VALUE_CARDS for v in card_values)
            is_prev_g1_weak = False
            previous_entry = self.sequential_history.get(game_number - 1)

            if is_current_g1_weak and previous_entry:
                # Extraction des valeurs des cartes N-1
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
            # Utilisation de l'ID du jeu au lieu du hash du message pour l'unicité
            if game_number not in self.processed_messages:
                self.processed_messages.add(game_number)
                self.last_prediction_time = time.time()
                self._save_all_data()
                # On retourne le texte de prédiction formaté avec la confiance
                prediction_text = self.make_prediction(game_number, predicted_value, confidence)
                return True, game_number, predicted_value, prediction_text # On retourne le texte à envoyer
        
        return False, None, None, None
        
    def make_prediction(self, game_number: int, predicted_value: str, confidence: str) -> str:
        """Génère le message de prédiction et l'enregistre avec la confiance."""
        target_game = game_number + 2
        
        confidence_tag = f" ({confidence})" if confidence else "" 
        prediction_text = f"🔵{target_game}🔵:Valeur Q statut :⏳{confidence_tag}" # <-- AJOUTE l'étiquette

        self.predictions[target_game] = {
            'predicted_costume': 'Q',
            'status': 'pending',
            'predicted_from': game_number,
            'verification_count': 0,
            'message_text': prediction_text,
            'message_id': None, 
            'confidence': confidence # <-- STOCKAGE de la CONFIANCE
        }
        self._save_all_data()
        return prediction_text
        
        def verify(self, text: str) -> Optional[Dict]:
        """Vérifie si le message contient le résultat pour une prédiction en attente (Q)."""
        game_number = self.extract_game_number(text)
        if not game_number or not self.predictions:
            return None

        # Filtrage des messages en attente ou non finalisés
        if '🕐' in text or '⏰' in text or not ('✅' in text or '🔰' in text):
            return None

        # Tri par clé pour vérifier les plus anciennes d'abord (meilleure pratique)
        for predicted_game in sorted(self.predictions.keys()):
            prediction = self.predictions[predicted_game]

            if prediction.get('status') != 'pending' or prediction.get('predicted_costume') != 'Q':
                continue

            verification_offset = game_number - predicted_game
            
            confidence = prediction.get('confidence', '') # <-- RÉCUPÈRE la CONFIANCE
            confidence_tag = f" ({confidence})" if confidence else "" 

            # Vérification pour N, N+1, N+2 par rapport à la prédiction
            if 0 <= verification_offset <= 2:
                status_symbol_map = {0: "✅0️⃣", 1: "✅1️⃣", 2: "✅2️⃣"}
                q_found = self.check_value_Q_in_first_parentheses(text)
                
                if q_found:
                    # SUCCÈS - Dame (Q) trouvée
                    status_symbol = status_symbol_map[verification_offset]
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :{status_symbol}{confidence_tag}" # <-- AJOUTE la CONFIANCE
                    
                    prediction['status'] = f'correct_offset_{verification_offset}'
                    prediction['verification_count'] = verification_offset
                    prediction['final_message'] = updated_message
                    self.predictions.pop(predicted_game, None) # Nettoyage après succès
                    self._save_all_data()
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'message_id': prediction.get('message_id'),
                        'new_message': updated_message,
                        # Le canal de prédiction est géré par le bot appelant
                    }
                elif verification_offset == 2 and not q_found:
                    # ÉCHEC à offset +2 - MARQUER ❌ (RIEN TROUVÉ)
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :❌{confidence_tag}" # <-- AJOUTE la CONFIANCE

                    prediction['status'] = 'failed'
                    prediction['final_message'] = updated_message
                    self.predictions.pop(predicted_game, None) # Nettoyage après échec final
                    self._save_all_data()
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'message_id': prediction.get('message_id'),
                        'new_message': updated_message,
                        # Le canal de prédiction est géré par le bot appelant
                    }
        return None
