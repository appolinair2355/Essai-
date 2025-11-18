# card_predictor (4).py

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
# CARD_SYMBOLS n'est pas nécessaire car il est géré dans card_details

# ---------- FONCTIONS UTILITAIRES D'EXTRACTION (NÉCESSAIRES AU FONCTIONNEMENT DES RÈGLES) ----------

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
    # Pattern pour capturer la valeur (chiffre ou lettre) et le symbole
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
    """Gère la logique de prédiction de carte Dame (Q) et la vérification."""

    def __init__(self):
        # Données de persistance (Init de card_predictor (4).py)
        self.predictions = self._load_data('predictions.json') 
        self.processed_messages = self._load_data('processed.json', is_set=True) 
        self.last_prediction_time = self._load_data('last_prediction_time.json', is_scalar=True)
        
        # --- Logique INTER & Historique (Ajoutée/Modifiée) ---
        self.seq_hist : Dict[int, Dict] = self._load_data("sequential_history.json", is_sequential_history=True)
        self.inter    : List[Dict]      = self._load_data("inter_data.json", is_list=True)
        self.active   : bool            = self._load_data("inter_mode_status.json", is_inter_active=True)
        self.rules    : List[Dict]      = self._load_data("smart_rules.json", is_list=True)
        self.cooldown = 30


    # ---------- GESTION DES DONNÉES (Adaptation de la structure fournie) ----------

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
        # Mise à jour des noms des attributs pour correspondre au fichier card_predictor (4).py
        for attr, file in [
            (self.predictions, "predictions.json"),
            (self.processed_messages, "processed.json"),
            (self.last_prediction_time, "last_prediction_time.json"),
            (self.seq_hist, "sequential_history.json"),
            (self.inter, "inter_data.json"),
            (self.active, "inter_mode_status.json"),
            (self.rules, "smart_rules.json"),
        ]: self._save_data(attr, file)
        
    # ---------- INTER COLLECT (Avec Anti-doublon) ----------
    def collect(self, game: int, msg: str):
        """Collecte les données pour l'analyse INTER (N-2 -> Q à N) avec anti-doublon."""
        content = extract_first_parentheses(msg)
        if not content: return
        f2 = first_two_cards(content)
        
        # Enregistrer le jeu actuel dans l'historique séquentiel
        if len(f2) == 2:
            self.seq_hist[game] = {"cards": f2, "date": datetime.now().isoformat()}
            
        # Vérifier si ce jeu (N) est un résultat Q
        if q_in_first_paren(msg):
            n2 = game - 2
            trig = self.seq_hist.get(n2)
            
            # Enregistrer le déclencheur N-2, AVEC VÉRIFICATION ANTI-DOUBLON
            if trig and not any(e.get("numero_resultat") == game for e in self.inter):
                self.inter.append({
                    "numero_resultat": game,
                    "declencheur": trig["cards"],
                    "numero_declencheur": n2,
                    "carte_q": "Q",
                    "date_resultat": datetime.now().isoformat(),
                })
                self._save_all_data()

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
    def should_predict(self, msg: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Détermine si une prédiction doit être faite en appliquant les 8 règles avec confiance."""
        game = extract_game_number(msg)
        if not game: return False, None, None
        self.collect(game, msg)

        # Filtre de finalisation (✅ ou 🔰) et d'attente (🕐 ou ⏰)
        if "🕐" in msg or "⏰" in msg or not any(s in msg for s in ["✅", "🔰"]):
            logger.info("Message non finalisé → aucune règle")
            return False, None, None

        g1_content = extract_first_parentheses(msg)
        if not g1_content: return False, None, None
        
        # Extraction des valeurs G1 et G2
        g1_vals = [v.upper() for v, _ in card_details(g1_content)]
        all_paren = re.findall(r'\(([^)]*)\)', msg)
        g2_vals = [v.upper() for v, _ in card_details(all_paren[1])] if len(all_paren) > 1 else []

        predicted = None
        confidence = ""

        # Pré-calcul des conditions
        has_j_only = g1_vals.count("J") == 1 and not any(h in g1_vals for h in ("A", "Q", "K"))
        two_j = g1_vals.count("J") >= 2
        high_t = (extract_total_points(msg) or 0) > 40
        three_miss = self.count_absence_q() >= 3
        set_8_9_10 = {"8", "9", "10"}
        is_8_9_10_combo = set_8_9_10.issubset(g1_vals) or set_8_9_10.issubset(g2_vals)

        # --- DÉBUT DES 8 RÈGLES DE PRÉDICTION ---

        # Règle 1 (INTER - Priorité Max)
        if self.active and self.rules:
            trigger = first_two_cards(g1_content)
            if any(tuple(r["cards"]) == tuple(trigger) for r in self.rules):
                predicted, confidence = "Q", "INTER" 

        # Règle 2: J seul (98%)
        if not predicted and has_j_only:
            predicted, confidence = "Q", "98%"
        
        # Règle 3: Deux Valets (57%)
        elif not predicted and two_j:
            predicted, confidence = "Q", "57%"
            
        # Règle 4: Total des points élevé (97%)
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
            return False, None, None
            
        # Règle 7 & 8 (Combinées pour 70%)
        elif not predicted:
            # Règle 7: K+J dans G1
            is_k_j_g1 = "K" in g1_vals and "J" in g1_vals
            # Règle 8a: Tag O/R dans le message
            is_o_r_tag = re.search(r'\b[OR]\b', msg)
            
            # Règle 8b: Double G1 faible consécutif
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
            logger.warning("⏳ PRÉDICTION ÉVITÉE: En période de 'cooldown'.")
            return False, None, None

        if predicted:
            h = hash(msg)
            if h not in self.processed_messages:
                self.processed_messages.add(h)
                self.last_prediction_time = time.time()
                self._save_all_data()
                # Appel à make_prediction pour construire le message avec la confiance
                return True, game, self._make_prediction(game, predicted, confidence)
                
        return False, None, None

    # ---------- MAKE PREDICTION (Ajout de la Confiance) ----------
    def _make_prediction(self, game: int, value: str, confidence: str) -> str:
        """Génère le message de prédiction et l'enregistre avec le niveau de confiance."""
        target = game + 2
        
        text = f"🔵{target}🔵:Valeur Q statut :⏳"
        
        # Ajout du pourcentage de confiance
        if confidence == "INTER":
             text += " (INTER)"
        elif confidence:
             text += f" ({confidence})"

        self.predictions[target] = {
            "predicted_costume": value,
            "status": "pending",
            "predicted_from": game,
            "verification_count": 0,
            "message_text": text,
            "message_id": None,
            "confidence": confidence, # Stockage du niveau de confiance
        }
        self._save_all_data()
        return text

    # ---------- VERIFY (Vérification) ----------
    def verify(self, msg: str) -> Optional[Dict]:
        """Vérifie si le message contient le résultat pour une prédiction en attente (Q)."""
        game = extract_game_number(msg)
        if not game or not self.predictions: return None
        
        for pred_game, pred in self.predictions.items():
            if pred.get("status") != "pending" or pred.get("predicted_costume") != "Q":
                continue
                
            offset = game - pred_game
            
            # Vérification pour N, N+1, N+2 par rapport à la prédiction
            if 0 <= offset <= 2:
                symbol_map = {0: "✅0️⃣", 1: "✅1️⃣", 2: "✅2️⃣"}
                q_found = q_in_first_paren(msg)
                
                if q_found:
                    # SUCCÈS - Dame (Q) trouvée
                    symbol = symbol_map[offset]
                    new_text = f"🔵{pred_game}🔵:Valeur Q statut :{symbol}"

                    pred["status"] = f"correct_offset_{offset}"
                    pred["final_message"] = new_text
                    self._save_all_data()
                    
                    logger.info("Verification SUCCÈS +%s N=%s", offset, game)
                    return {"type": "edit_message", "predicted_game": pred_game, "new_message": new_text}
                    
                if offset == 2 and not q_found:
                    # ÉCHEC à offset +2 - MARQUER ❌
                    new_text = f"🔵{pred_game}🔵:Valeur Q statut :❌"
                    
                    pred["status"] = "failed"
                    pred["final_message"] = new_text
                    self._save_all_data()
                    
                    logger.info("Verification ÉCHEC +2 N=%s", game)
                    return {"type": "edit_message", "predicted_game": pred_game, "new_message": new_text}
        return None
