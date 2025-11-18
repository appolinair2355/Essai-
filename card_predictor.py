# card_predictor.py

"""
Card prediction logic for Joker's Telegram Bot - simplified for webhook deployment
"""
import re
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set
import time
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"] 

# ---------- FONCTIONS UTILITAIRES D'EXTRACTION ----------

def extract_game_number(msg: str) -> Optional[int]:
    """Extrait le numéro du jeu, reconnaissant #N ou #n (insensible à la casse)."""
    m = re.search(r'#N(\d+)\.', msg, re.I) or re.search(r'🔵(\d+)🔵', msg)
    return int(m.group(1)) if m else None

def extract_total_points(msg: str) -> Optional[int]:
    """Extrait le total des points #T."""
    m = re.search(r'#T(\d+)', msg)
    return int(m.group(1)) if m else None

def extract_first_parentheses(msg: str) -> Optional[str]:
    """Extrait le contenu de la première parenthèse (G1)."""
    m = re.search(r'\(([^)]*)\)', msg)
    return m.group(1).strip() if m else None

def card_details(content: str) -> List[Tuple[str, str]]:
    """Extrait la valeur et le costume des cartes."""
    content = content.replace("❤️", "♥️")
    return re.findall(r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)', content, re.I)

def first_two_cards(content: str) -> List[str]:
    """Renvoie les deux premières cartes pour le déclencheur INTER."""
    return [f"{v}{c}" for v, c in card_details(content)[:2]]

def q_in_first_paren(msg: str) -> bool:
    """Vérifie si la Dame (Q) est dans le premier groupe (G1)."""
    content = extract_first_parentheses(msg)
    if not content: return False
    return any(v.upper() == "Q" for v, _ in card_details(content))


# ---------- CLASSE CARDPREDICTOR ----------
class CardPredictor:
    """Gère la logique de prédiction de carte Dame (Q), la vérification et les commandes."""

    def __init__(self):
        # Données de persistance
        self.predictions : Dict[int, Dict] = self._load_data('predictions.json') 
        self.processed_messages : Set[int] = self._load_data('processed.json', is_set=True) 
        self.last_prediction_time : float = self._load_data('last_prediction_time.json', is_scalar=True)
        
        # Configuration des canaux
        self.config_data = self._load_data('channels_config.json')
        self.target_channel_id : Optional[int] = self.config_data.get('target_channel_id', None)
        self.prediction_channel_id : Optional[int] = self.config_data.get('prediction_channel_id', None)
        
        # Logique INTER & Historique
        self.seq_hist : Dict[int, Dict] = self._load_data("sequential_history.json", is_sequential_history=True)
        self.inter_data : List[Dict]      = self._load_data("inter_data.json", is_list=True)
        self.is_inter_mode_active : bool = self._load_data("inter_mode_status.json", is_inter_active=True)
        self.smart_rules : List[Dict]      = self._load_data("smart_rules.json", is_list=True)
        self.cooldown = 30 # Période de refroidissement entre deux prédictions

    # ---------- GESTION DES DONNÉES (Persistance JSON) ----------

    def _load_data(self, file: str, is_set: bool = False, is_scalar: bool = False, is_list: bool = False, is_inter_active: bool = False, is_sequential_history: bool = False) -> Any:
        """Charge les données depuis un fichier JSON."""
        try:
            with open(file) as f:
                data = json.load(f)
                if is_set: return set(data)
                if is_scalar: return float(data)
                if is_inter_active: return data.get("active", False)
                if is_sequential_history: return {int(k): v for k, v in data.items()}
                return data
        except (FileNotFoundError, ValueError):
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
        """Sauvegarde les données dans un fichier JSON."""
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
        """Sauvegarde tous les états persistants."""
        for attr_name, file in [
            ("predictions", "predictions.json"),
            ("processed_messages", "processed.json"),
            ("last_prediction_time", "last_prediction_time.json"),
            ("seq_hist", "sequential_history.json"),
            ("inter_data", "inter_data.json"),
            ("is_inter_mode_active", "inter_mode_status.json"),
            ("smart_rules", "smart_rules.json"),
        ]: 
            self._save_data(getattr(self, attr_name), file)
        
    # ---------- COMMANDES & LOGIQUE INTER ----------

    def collect_inter_data(self, game: int, msg: str):
        """Collecte les données pour l'analyse INTER (N-2 -> Q à N) avec anti-doublon."""
        content = extract_first_parentheses(msg)
        if not content: return
        f2 = first_two_cards(content)
        
        # Enregistrer le jeu actuel dans l'historique séquentiel
        if len(f2) == 2:
            self.seq_hist[game] = {"cards": f2, "date": datetime.now().isoformat()}
            
        # Vérifier si ce jeu est le résultat (Q) et enregistrer le déclencheur N-2
        if q_in_first_paren(msg):
            n2 = game - 2
            trig = self.seq_hist.get(n2)
            
            if trig and not any(e.get("numero_resultat") == game for e in self.inter_data):
                self.inter_data.append({
                    "numero_resultat": game,
                    "declencheur": trig["cards"],
                    "numero_declencheur": n2,
                    "carte_q": "Q",
                    "date_resultat": datetime.now().isoformat(),
                })
                self._save_all_data()

    def analyze_and_set_smart_rules(self) -> List[Dict]:
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
        # L'activation est gérée par set_inter_mode, mais on sauve les règles
        self._save_all_data()
        return self.smart_rules
        
    def set_inter_mode(self, status: bool):
        """
        Met à jour le statut du mode INTER. 
        Si True, recalcule et applique les règles. Si False, désactive l'utilisation des règles INTER.
        """
        self.is_inter_mode_active = status
        if status:
            self.analyze_and_set_smart_rules() 
        else:
            # Conserver l'historique, mais ne plus utiliser les règles
            self._save_data(self.is_inter_mode_active, 'inter_mode_status.json')
        logger.info(f"Mode INTER mis à jour: {'ACTIF' if status else 'INACTIF'}")

    def get_status_response(self) -> Tuple[str, Optional[Dict]]:
        """Génère le message et le clavier pour la commande /inter ou /status."""
        status_lines = ["**📋 STATUT D'APPRENTISSAGE INTER (N-2 → Q à N) 🧠**\n"]
        total_collected = len(self.inter_data) 
        
        status_lines.append(f"**Mode Intelligent Actif:** {'✅ OUI' if self.is_inter_mode_active else '❌ NON'}")
        status_lines.append(f"**Historique Q collecté:** **{total_collected} entrées.**\n")

        # Afficher les règles actuelles si actives
        if self.smart_rules:
            status_lines.append("**🎯 Règles Actives (Top 3 Déclencheurs):**")
            for rule in self.smart_rules:
                status_lines.append(f"- {rule['cards'][0]} {rule['cards'][1]} (x{rule['count']})")
            status_lines.append("\n---\n")
        
        # Afficher la liste complète des enregistrements récents (Max 10)
        if total_collected > 0:
            status_lines.append("**Derniers Enregistrements (N-2 → Q à N):**")
            for entry in self.inter_data[-10:]:
                declencheur_str = f"{entry['declencheur'][0]} {entry['declencheur'][1]}"
                line = (
                    f"• N{entry['numero_resultat']} ({entry['carte_q']}) "
                    f"← Déclencheur N{entry['numero_declencheur']} ({declencheur_str})"
                )
                status_lines.append(line)
        else:
             status_lines.append("\n*Aucun historique de Dame (Q) collecté.*")

        # PRÉSENTER LES BOUTONS
        keyboard = None
        if total_collected > 0:
            apply_button_text = f"🔄 Re-analyser et Appliquer ({len(self.smart_rules)} règles)" if self.is_inter_mode_active else f"✅ Activer Mode Intelligent ({total_collected} entrées)"
            
            keyboard = {'inline_keyboard': [
                [{'text': apply_button_text, 'callback_data': 'inter_apply'}],
                [{'text': "❌ Désactiver le mode INTER", 'callback_data': 'inter_default'}]
            ]}
        else:
            status_lines.append("\n*Aucune action d'activation/désactivation INTER disponible.*")


        return "\n".join(status_lines), keyboard

    # ---------- Règle d'absence Q ----------
    def count_absence_q(self) -> int:
        """Compte les jeux consécutifs où Q n'est pas dans le premier groupe."""
        c = 0
        for gn in sorted(self.seq_hist.keys(), reverse=True):
            if self.seq_hist.get(gn) and "cards" in self.seq_hist[gn] and not any(crd.startswith("Q") for crd in self.seq_hist[gn].get("cards", [])):
                c += 1
            else:
                break
        return c

    # ---------- SHOULD PREDICT (8 RÈGLES + CONFIDENCE) ----------
    def should_predict(self, msg: str) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """
        Détermine si une prédiction doit être faite en appliquant les 8 règles avec confiance.
        Retourne (Bool, Game_Number, Predicted_Value, Confidence_String)
        """
        game = extract_game_number(msg)
        if not game: return False, None, None, None
        self.collect_inter_data(game, msg)

        # 1. FILTRE DE FINALISATION CRITIQUE : Bloquer si le message n'est pas finalisé
        # DOIT être finalisé (✅ ou 🔰) ET NE DOIT PAS être en attente (🕐 ou ⏰)
        if "🕐" in msg or "⏰" in msg or not any(s in msg for s in ["✅", "🔰"]):
            return False, None, None, None

        g1_content = extract_first_parentheses(msg)
        if not g1_content: return False, None, None, None
        
        g1_vals = [v.upper() for v, _ in card_details(g1_content)]
        all_paren = re.findall(r'\(([^)]*)\)', msg)
        g2_vals = [v.upper() for v, _ in card_details(all_paren[1])] if len(all_paren) > 1 else []

        predicted = None
        confidence = ""

        # Pré-calcul des conditions
        set_8_9_10 = {"8", "9", "10"}
        is_8_9_10_combo = set_8_9_10.issubset(g1_vals) or set_8_9_10.issubset(g2_vals)
        has_j_only = g1_vals.count("J") == 1 and not any(h in g1_vals for h in ("A", "Q", "K"))
        two_j = g1_vals.count("J") >= 2
        high_t = (extract_total_points(msg) or 0) >= 45 # Règle 4 MODIFIÉE: Total >= 45
        three_miss = self.count_absence_q() >= 3
        
        # 8 RÈGLES DE PRÉDICTION AVEC POURCENTAGE DE CONFIANCE

        # Règle 1: INTER (Priorité Max)
        if self.is_inter_mode_active and self.smart_rules:
            trigger = first_two_cards(g1_content)
            if any(tuple(r["cards"]) == tuple(trigger) for r in self.smart_rules):
                predicted, confidence = "Q", "INTER" 

        # Règle 2: J seul (98%)
        if not predicted and has_j_only:
            predicted, confidence = "Q", "98%"
        
        # Règle 3: Deux Valets (57%)
        elif not predicted and two_j:
            predicted, confidence = "Q", "57%"
            
        # Règle 4: Total des points élevé (97%) <-- DÉCLENCHE SI #T >= 45
        elif not predicted and high_t:
            predicted, confidence = "Q", "97%"
        
        # Règle 5: 3 Q manquants (60%)
        elif not predicted and three_miss:
            predicted, confidence = "Q", "60%"
            
        # Règle 6: 8, 9, 10 (70%)
        elif not predicted and is_8_9_10_combo:
            predicted, confidence = "Q", "70%"
            
        # Blocage si Q est déjà dans G1
        elif "Q" in g1_vals:
            return False, None, None, None
            
        # Règle 7 & 8 (Combinées pour 70%): K+J / O,R Tag / Double Faible
        elif not predicted:
            is_k_j_g1 = "K" in g1_vals and "J" in g1_vals
            is_o_r_tag = re.search(r'\b[OR]\b', msg) # Cherche les tags O ou R

            # Logique Règle 8 (Double Faible)
            g1_g2_weak_n = not any(h in g1_vals or h in g2_vals for h in HIGH_VALUE_CARDS)
            is_prev_g1_weak = False
            prev_entry = self.seq_hist.get(game - 1)
            if prev_entry and "cards" in prev_entry:
                prev_vals = [re.match(r'(\d+|[AKQJ])', c).group(1) for c in prev_entry['cards'] if re.match(r'(\d+|[AKQJ])', c)]
                is_prev_g1_weak = not any(h in prev_vals for h in HIGH_VALUE_CARDS)

            is_double_g1_weak = g1_g2_weak_n and is_prev_g1_weak
            
            if is_k_j_g1 or is_o_r_tag or is_double_g1_weak:
                predicted, confidence = "Q", "70%"

        # --- COOLDOWN ET ENREGISTREMENT ---
        if predicted and not (time.time() > (self.last_prediction_time + self.cooldown)):
            return False, None, None, None

        if predicted:
            h = hash(msg)
            if h not in self.processed_messages:
                self.processed_messages.add(h)
                self.last_prediction_time = time.time()
                self._save_all_data()
                return True, game, predicted, confidence
                
        return False, None, None, None

    # ---------- MAKE PREDICTION (Ajout de la Confiance) ----------
    def make_prediction(self, game: int, predicted_value: str, confidence: str) -> str:
        """Génère le message de prédiction et l'enregistre avec le niveau de confiance."""
        target = game + 2
        
        text = f"🔵{target}🔵:Valeur Q statut :⏳"
        
        # Ajout du pourcentage de confiance
        if confidence == "INTER":
             text += " (INTER)"
        elif confidence:
             text += f" ({confidence})"

        self.predictions[target] = {
            "predicted_costume": predicted_value,
            "status": "pending",
            "predicted_from": game,
            "verification_count": 0,
            "message_text": text,
            "message_id": None,
            "confidence": confidence, # Stockage du niveau de confiance
        }
        self._save_all_data()
        return text

    # ---------- VERIFY (Vérification et conservation de la confiance) ----------
    def verify(self, msg: str) -> Optional[Dict]:
        """Vérifie si le message contient le résultat pour une prédiction en attente (Q)."""
        game = extract_game_number(msg)
        if not game or not self.predictions: return None
        
        # FILTRE DE FINALISATION CRITIQUE : Assurez-vous que le message source est finalisé
        if "🕐" in msg or "⏰" in msg or not any(s in msg for s in ["✅", "🔰"]):
            return None 

        for pred_game, pred in self.predictions.items():
            if pred.get("status") != "pending" or pred.get("predicted_costume") != "Q":
                continue
                
            offset = game - pred_game
            
            # Récupération de la confiance pour la réintégration
            confidence = pred.get("confidence", "")
            confidence_tag = f" ({confidence})" if confidence else ""
            
            # Vérification pour N, N+1, N+2 par rapport à la prédiction
            if 0 <= offset <= 2:
                symbol_map = {0: "✅0️⃣", 1: "✅1️⃣", 2: "✅2️⃣"}
                q_found = q_in_first_paren(msg)
                
                if q_found:
                    # SUCCÈS
                    status_symbol = symbol_map[offset]
                    updated_message = f"🔵{pred_game}🔵:Valeur Q statut :{status_symbol}{confidence_tag}"

                    pred["status"] = f"correct_offset_{offset}"
                    pred["verification_count"] = offset
                    pred["final_message"] = updated_message
                    self._save_all_data()
                    
                    logger.info(f"🔍 ✅ SUCCÈS OFFSET +{offset} - Dame (Q) trouvée au jeu {game}")
                    
                    return {
                        'type': 'edit_message',
                        'predicted_game': pred_game,
                        'new_message': updated_message,
                    }
                    
                elif offset == 2 and not q_found:
                    # ÉCHEC à offset +2
                    updated_message = f"🔵{pred_game}🔵:Valeur Q statut :❌{confidence_tag}"
                    
                    pred["status"] = 'failed'
                    pred["final_message"] = updated_message
                    self._save_all_data()
                    
                    logger.info(f"🔍 ❌ ÉCHEC OFFSET +2 - Rien trouvé, prédiction marquée: ❌")

                    return {
                        'type': 'edit_message',
                        'predicted_game': pred_game,
                        'new_message': updated_message,
                    }
        return None
