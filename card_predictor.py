# card_predictor.py

"""
Card prediction logic for Joker's Telegram Bot - simplified for webhook deployment
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import time
import os
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"] 
CARD_SYMBOLS = [r"♠️", r"♥️", r"♦️", r"♣️", r"❤️"] # Inclure les deux variantes pour le pattern regex

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
        # Stocke les cartes de tous les jeux, en attendant que Q arrive à N pour relier à N-2
        self.sequential_history: Dict[int, Dict] = self._load_data('sequential_history.json') 
        # Données officielles des déclencheurs
        self.inter_data: List[Dict] = self._load_data('inter_data.json') 
        
        # Statut et Règles
        self.is_inter_mode_active = self._load_data('inter_mode_status.json', is_scalar=True)
        self.smart_rules = self._load_data('smart_rules.json') # Stocke les Top 3 actifs
        self.prediction_cooldown = 30 
        
        if self.inter_data and not self.is_inter_mode_active:
             self.analyze_and_set_smart_rules(initial_load=True) # Analyse à l'initialisation si l'historique existe

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
                    return int(data) if isinstance(data, (int, float)) else data
                
                # Gestion des types
                if filename == 'inter_data.json': return data
                if filename == 'sequential_history.json': 
                    # Convertir les clés string en int si elles représentent le numéro de jeu
                    return {int(k): v for k, v in data.items()}
                if filename == 'smart_rules.json': return data
                
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"⚠️ Fichier {filename} non trouvé ou vide. Initialisation par défaut.")
            if is_set: return set()
            if is_scalar and filename == 'inter_mode_status.json': return False
            if is_scalar: return 0.0
            if filename == 'inter_data.json': return []
            if filename == 'sequential_history.json': return {}
            if filename == 'smart_rules.json': return []
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
        """Met à jour les IDs de canal et sauvegarde."""
        if channel_type == 'source':
            self.target_channel_id = channel_id
            logger.info(f"💾 Canal SOURCE mis à jour: {channel_id}")
        elif channel_type == 'prediction':
            self.prediction_channel_id = channel_id
            logger.info(f"💾 Canal PRÉDICTION mis à jour: {channel_id}")
        else:
            return False
            
        self._save_channels_config()
        return True

    # --- Logique d'Extraction (Inchangée) ---
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
            return match.group(1).strip()
        return None

    def extract_card_details(self, content: str) -> List[Tuple[str, str]]:
        """Extrait la valeur et le costume des cartes."""
        card_details = []
        normalized_content = content.replace("❤️", "♥️") # Normalise le cœur
        # Pattern pour capturer la valeur (chiffre ou lettre) et le symbole
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
                logger.info(f"🔍 Détection Q: Dame (Q) trouvée dans le premier groupe: {value}{costume}")
                return (value, costume)
                
        return None

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
            # Si Dame Q trouvée à N, le déclencheur est N-2
            n_minus_2_game = game_number - 2
            
            # 3. CHERCHER LE DÉCLENCHEUR (N-2) DANS L'HISTORIQUE EN ATTENTE
            trigger_entry = self.sequential_history.get(n_minus_2_game)
            
            if trigger_entry:
                trigger_cards = trigger_entry['cartes']
                
                new_entry = {
                    'numero_resultat': game_number,
                    'declencheur': trigger_cards,
                    'numero_declencheur': n_minus_2_game,
                    'carte_q': f"{q_card_details[0]}{q_card_details[1]}",
                    'date_resultat': datetime.now().isoformat()
                }
                self.inter_data.append(new_entry)
                self._save_all_data() 
                logger.info(f"💾 INTER Data Saved: Q à N={game_number} déclenché par N-2={n_minus_2_game} ({trigger_cards})")
        
        # 4. NETTOYAGE: Supprimer les entrées très anciennes (par exemple, plus de 50 jeux avant)
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
        
        # Activer le mode si des règles sont trouvées ou s'il s'agit d'un chargement initial
        if top_3:
            self.is_inter_mode_active = True
        elif not initial_load:
            self.is_inter_mode_active = False 

        # Sauvegarder le statut et les règles
        self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        self._save_data(self.smart_rules, 'smart_rules.json')
            
        return [f"{cards['cards'][0]} {cards['cards'][1]} (x{cards['count']})" for cards in top_3]

    def get_inter_status(self) -> Tuple[str, Optional[Dict]]:
        """Génère le statut pour la commande /inter avec l'historique et les boutons."""
        status_lines = ["**📋 HISTORIQUE D'APPRENTISSAGE INTER 🧠**\n"]
        total_collected = len(self.inter_data) 
        
        status_lines.append(f"**Mode Intelligent Actif:** {'✅ OUI' if self.is_inter_mode_active else '❌ NON'}")
        status_lines.append(f"**Historique Q collecté:** **{total_collected} entrées.**\n")

        # Afficher la liste complète des enregistrements récents (Max 10)
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
        
        # Afficher les règles actuelles si actives
        if self.is_inter_mode_active and self.smart_rules:
            status_lines.append("**🎯 Règles Actives (Top 3 Déclencheurs):**")
            for rule in self.smart_rules:
                status_lines.append(f"- {rule['cards'][0]} {rule['cards'][1]} (x{rule['count']})")
            status_lines.append("\n---")


        # PRÉSENTER LES BOUTONS
        if total_collected > 0:
            # Si déjà actif, proposer de re-analyser ou de désactiver
            if self.is_inter_mode_active:
                 apply_button_text = f"🔄 Re-analyser et appliquer (Actif)"
            else:
                 # Si inactif mais données disponibles, proposer l'activation
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

    def has_pending_indicators(self, message: str) -> bool:
        """Vérifie la présence d'indicateurs de confirmation (R, X)."""
        return '#R' in message or '#X' in message

    def should_predict(self, message: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Détermine si une prédiction doit être faite."""
        if not self.target_channel_id:
             return False, None, None
             
        game_number = self.extract_game_number(message)
        if not game_number:
            return False, None, None

        # --- ÉTAPE CRITIQUE: Collecte de données pour INTER ---
        self.collect_inter_data(game_number, message) 
        # ----------------------------------------------------
        
        # Ne pas prédire si c'est une confirmation ou un échec
        if self.has_pending_indicators(message):
            return False, None, None
            
        predicted_value = None
        first_group_content = self.extract_first_parentheses_content(message)

        if first_group_content:
            card_details = self.extract_card_details(first_group_content)
            
            # 1. LOGIQUE INTER (PRIORITÉ)
            if self.is_inter_mode_active and self.smart_rules:
                current_trigger_cards = self.get_first_two_cards(first_group_content)
                current_trigger_tuple = tuple(current_trigger_cards)
                
                # Vérifie si le déclencheur actuel correspond à une règle intelligente
                if any(tuple(rule['cards']) == current_trigger_tuple for rule in self.smart_rules):
                    predicted_value = "Q"
                    logger.info(f"🔮 PRÉDICTION INTER: Déclencheur {current_trigger_cards} trouvé dans les règles intelligentes.")
            
            # 2. LOGIQUE STATIQUE (SEULEMENT SI INTER N'A PAS DÉJÀ PRÉDIT)
            if not predicted_value:
                card_values = [v for v, c in card_details]
                
                # Règle Statique 1: Deux Valets (J)
                if card_values.count('J') >= 2:
                    predicted_value = "Q"
                    logger.info("🔮 PRÉDICTION STATIQUE: Deux Valets (J) trouvés.")

                # Règle Statique 2: Un Valet (J) + pas de carte forte dans le 2e groupe
                elif card_values.count('J') == 1:
                    second_parentheses_pattern = r'\(([^)]*)\)'
                    all_matches = re.findall(second_parentheses_pattern, message)
                    second_group_content = all_matches[1] if len(all_matches) > 1 else ""

                    second_group_details = self.extract_card_details(second_group_content)
                    second_group_values = [v for v, c in second_group_details]

                    has_high_value_in_second = any(v in HIGH_VALUE_CARDS for v in second_group_values)
                    
                    if not has_high_value_in_second:
                        predicted_value = "Q"
                        logger.info("🔮 PRÉDICTION STATIQUE: Un Valet (J) sans carte forte dans le 2e groupe.")

        if predicted_value and not self.can_make_prediction():
            logger.warning("⏳ PRÉDICTION ÉVITÉE: En période de 'cooldown'.")
            return False, None, None

        if predicted_value:
            message_hash = hash(message)
            if message_hash not in self.processed_messages:
                self.processed_messages.add(message_hash)
                self.last_prediction_time = time.time()
                self._save_all_data()
                return True, game_number, predicted_value

        return False, None, None
        
    def make_prediction(self, game_number: int, predicted_value: str) -> str:
        """Génère le message de prédiction et l'enregistre."""
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
        
    def _verify_prediction_common(self, text: str, is_edited: bool = False) -> Optional[Dict]:
        """Vérifie si le message contient le résultat pour une prédiction en attente (Q)."""
        game_number = self.extract_game_number(text)
        if not game_number or not self.predictions:
            return None

        # Vérifie uniquement les prédictions N, N-1, N-2 par rapport au message entrant
        for predicted_game in sorted(self.predictions.keys()):
            prediction = self.predictions[predicted_game]

            if prediction.get('status') != 'pending' or prediction.get('predicted_costume') != 'Q':
                continue

            verification_offset = game_number - predicted_game
            
            # Vérification pour N, N+1, N+2 par rapport à la prédiction
            if 0 <= verification_offset <= 2:
                status_symbol_map = {0: "✅0️⃣", 1: "✅1️⃣", 2: "✅2️⃣"}
                q_found = self.check_value_Q_in_first_parentheses(text)
                
                if q_found:
                    # SUCCÈS - Dame (Q) trouvée
                    status_symbol = status_symbol_map[verification_offset]
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :{status_symbol}"
                    
                    prediction['status'] = f'correct_offset_{verification_offset}'
                    prediction['verification_count'] = verification_offset
                    prediction['final_message'] = updated_message
                    self._save_all_data()
                    
                    logger.info(f"🔍 ✅ SUCCÈS OFFSET +{verification_offset} - Dame (Q) trouvée au jeu {game_number}")
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'new_message': updated_message,
                    }
                elif verification_offset == 2 and not q_found:
                    # ÉCHEC à offset +2 - MARQUER ❌ (RIEN TROUVÉ)
                    updated_message = f"🔵{predicted_game}🔵:Valeur Q statut :❌"

                    prediction['status'] = 'failed'
                    prediction['final_message'] = updated_message
                    self._save_all_data()
                    
                    logger.info(f"🔍 ❌ ÉCHEC OFFSET +2 - Rien trouvé, prédiction marquée: ❌")

                    return {
                        'type': 'edit_message',
                        'predicted_game': predicted_game,
                        'new_message': updated_message,
                    }
        return None
