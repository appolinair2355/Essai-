# card_predictor.py (Partie 1/2)
import json
import re
import time
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- CONSTANTES ---
HIGH_VALUE_CARDS = ["A", "K", "Q", "J"]

# ---------- FONCTIONS UTILITAIRES JSON ----------
def jload(file: str, is_set: bool = False, scalar: bool = False) -> Any:
    """Charge les données depuis un fichier JSON."""
    try:
        with open(file) as f:
            data = json.load(f)
            if is_set: return set(data)
            if scalar: return (data.get("active", False) if file == "inter_mode_status.json" else float(data))
            if file == "sequential_history.json": return {int(k): v for k, v in data.items()}
            return data
    except (FileNotFoundError, ValueError):
        if is_set: return set()
        if scalar: return (False if file == "inter_mode_status.json" else 0.0)
        return [] if "inter_data" in file else {}
    except Exception as e:
        logger.error(f"❌ Erreur jload {file} : {e}")
        return set() if is_set else (False if file == "inter_mode_status.json" else ([] if "inter_data" in file else {}))

def jsave(data: Any, file: str):
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
        logger.error(f"❌ Erreur jsave {file} : {e}")

# ---------- FONCTIONS D'EXTRACTION DE CARTES ----------
def extract_game_number(msg: str) -> Optional[int]:
    """Extrait le numéro du jeu, reconnaissant #N ou #n (insensible à la casse)."""
    # re.I = re.IGNORECASE
    m = re.search(r'#N(\d+)\.', msg, re.I) or re.search(r'🔵(\d+)🔵', msg)
    return int(m.group(1)) if m else None

def extract_total_points(msg: str) -> Optional[int]:
    """Extrait le total des points #T."""
    m = re.search(r'#T(\d+)', msg)
    return int(m.group(1)) if m else None

def extract_first_parentheses(msg: str) -> Optional[str]:
    """Extrait le contenu de la première parenthèse."""
    m = re.search(r'\(([^)]*)\)', msg)
    return m.group(1).strip() if m else None

def card_details(content: str) -> List[Tuple[str, str]]:
    """Extrait la valeur et le costume des cartes."""
    card_details = []
    content = content.replace("❤️", "♥️")
    # Pattern pour capturer la valeur (chiffre ou lettre) et le symbole
    card_pattern = r'(\d+|[AKQJ])(♠️|♥️|♦️|♣️)'
    matches = re.findall(card_pattern, content, re.I)
    for value, costume in matches:
        card_details.append((value.upper(), costume))
    return card_details

def first_two_cards(content: str) -> List[str]:
    """Renvoie les deux premières cartes pour le déclencheur INTER."""
    return [f"{v}{c}" for v, c in card_details(content)[:2]]

def q_in_first_paren(msg: str) -> bool:
    """Vérifie si la Dame (Q) est dans le premier groupe."""
    content = extract_first_parentheses(msg)
    if not content: return False
    return any(v.upper() == "Q" for v, _ in card_details(content))

# ---------- CLASSE CARDPREDICTOR ----------
class CardPredictor:
    """Gère la logique de prédiction de carte Dame (Q) et la vérification."""

    def __init__(self):
        # Données de persistance
        self.pred     : Dict[int, Dict] = jload("predictions.json")
        self.proc     : Set[int]        = jload("processed.json", is_set=True)
        self.last     : float           = jload("last_prediction_time.json", scalar=True)
        self.seq_hist : Dict[int, Dict] = jload("sequential_history.json") # Historique séquentiel
        self.inter    : List[Dict]      = jload("inter_data.json")         # Historique des déclencheurs Q
        self.active   : bool            = jload("inter_mode_status.json", scalar=True)
        self.rules    : List[Dict]      = jload("smart_rules.json")       # Règles INTER actives
        self.cooldown = 30
        
        self.save_all = self._save_all_data

    def _save_all_data(self):
        """Sauvegarde tous les états persistants."""
        for attr, file in [
            (self.pred, "predictions.json"),
            (self.proc, "processed.json"),
            (self.last, "last_prediction_time.json"),
            (self.seq_hist, "sequential_history.json"),
            (self.inter, "inter_data.json"),
            (self.active, "inter_mode_status.json"),
            (self.rules, "smart_rules.json"),
        ]: jsave(attr, file)

    # ---------- INTER COLLECT (Avec Anti-doublon) ----------
    def collect(self, game: int, msg: str):
        """Collecte les données pour l'analyse INTER (N-2 -> Q à N) avec anti-doublon."""
        content = extract_first_parentheses(msg)
        if not content: return
        f2 = first_two_cards(content)
        
        # 1. Enregistrer le jeu actuel dans l'historique séquentiel
        if len(f2) == 2:
            self.seq_hist[game] = {"cartes": f2, "date": datetime.now().isoformat()}
            
        # 2. Vérifier si ce jeu (N) est un résultat Q
        if q_in_first_paren(msg):
            n2 = game - 2
            trig = self.seq_hist.get(n2)
            
            # 3. Enregistrer le déclencheur N-2, AVEC VÉRIFICATION ANTI-DOUBLON
            if trig and not any(e.get("numero_resultat") == game for e in self.inter):
                self.inter.append({
                    "numero_resultat": game,
                    "declencheur": trig["cartes"],
                    "numero_declencheur": n2,
                    "carte_q": "Q",
                    "date_resultat": datetime.now().isoformat(),
                })
                self.save_all()
                logger.info(f"💾 INTER Data Saved: Q à N={game} déclenché par N-2={n2} ({trig['cartes']})")
            elif trig:
                 logger.warning(f"❌ INTER Data Ignoré: Doublon détecté pour le numéro de résultat N={game}. Non ajouté.")


    # ---------- ANALYSE SMART RULES ----------
    def analyze_and_set_smart_rules(self):
        """Analyse l'historique et définit les 3 règles les plus fréquentes."""
        counts: Dict[tuple, int] = {}
        for e in self.inter:
            counts[tuple(e["declencheur"])] = counts.get(tuple(e["declencheur"]), 0) + 1
            
        top3 = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]
        self.rules = [{"cards": list(k), "count": v} for k, v in top3]
        self.active = bool(self.rules)
        self.save_all()

    # ---------- RÈGLE STATIQUE 4 (Absence de Q) ----------
    def count_absence_q(self) -> int:
        """Compte les jeux consécutifs où Q n'est pas dans le premier groupe."""
        c = 0
        for gn in sorted(self.seq_hist.keys(), reverse=True):
            # L'historique stocke les cartes du G1 à l'enregistrement.
            if self.seq_hist.get(gn) and not any(crd.startswith("Q") for crd in self.seq_hist[gn].get("cartes", [])):
                c += 1
            else:
                break
        return c

    # ---------- COOLDOWN ET FILTRES ----------
    def can_predict(self) -> bool:
        """Vérifie la période de refroidissement."""
        return time.time() > (self.last + self.cooldown)

    def pending(self, msg: str) -> bool:
        """Vérifie les indicateurs d'état temporaire (🕐 ou ⏰)."""
        return "🕐" in msg or "⏰" in msg

    def completed(self, msg: str) -> bool:
        """Vérifie les indicateurs de succès explicites (✅ ou 🔰)."""
        return "✅" in msg or "🔰" in msg

# (La suite de cette partie est dans la Partie 2)
# card_predictor.py (Partie 2/2)

    # --- LOGIQUE DE PRÉDICTION should_predict (8 RÈGLES + CONFIDENCE) ---
    def should_predict(self, msg: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """Détermine si une prédiction doit être faite en appliquant les 8 règles."""
        game = extract_game_number(msg)
        if not game: return False, None, None
        
        # Collecte d'abord, car le message peut être un résultat Q qui met à jour l'historique
        self.collect(game, msg)

        # 1. Garde-fou strict (Message doit être finalisé)
        if self.pending(msg) or not self.completed(msg):
            logger.info("❌ PRÉDICTION BLOQUÉE: Message non finalisé ou en attente (🕐/⏰/Absence ✅/🔰).")
            return False, None, None

        g1_content = extract_first_parentheses(msg)
        if not g1_content: return False, None, None
        
        # Extraction des valeurs pour l'analyse
        g1_details = card_details(g1_content)
        g1_vals = [v.upper() for v, _ in g1_details]
        
        # Extraction du second groupe
        all_paren = re.findall(r'\(([^)]*)\)', msg)
        g2_content = all_paren[1] if len(all_paren) > 1 else ""
        g2_vals = [v.upper() for v, _ in card_details(g2_content)]

        predicted = None
        confidence = ""

        # Pré-calcul des conditions
        has_j_only = g1_vals.count("J") == 1 and not any(h in g1_vals for h in ("A", "Q", "K"))
        two_j = g1_vals.count("J") >= 2
        high_t = (extract_total_points(msg) or 0) > 40
        three_miss = self.count_absence_q() >= 3 # Règle d'absence Q consécutif
        
        # --- 1. LOGIQUE INTER (PRIORITÉ MAX) ---
        if self.active and self.rules:
            trigger = first_two_cards(g1_content)
            if any(tuple(r["cards"]) == tuple(trigger) for r in self.rules):
                predicted, confidence = "Q", "INTER" 
                logger.info("🔮 PRÉDICTION INTER: Déclencheur %s trouvé.", trigger)

        # --- 2. LOGIQUE STATIQUE (8 RÈGLES) ---
        if not predicted:
            
            # Règle 1: J seul (sans A, Q, K) dans G1 (98%)
            if has_j_only:
                predicted, confidence = "Q", "98%"
                logger.info("🔮 PRÉDICTION STATIQUE 1: J seul.")
            
            # Règle 2: Deux Valets (J) dans G1 (57%)
            elif two_j:
                predicted, confidence = "Q", "57%"
                logger.info("🔮 PRÉDICTION STATIQUE 2: Deux J.")
                
            # Règle 3: Total des points élevé (#T > 40) (97%)
            elif high_t:
                predicted, confidence = "Q", "97%"
                logger.info("🔮 PRÉDICTION STATIQUE 3: #T > 40.")
            
            # Règle 4: Absence de Q dans G1 pour 3 jeux consécutifs (60%)
            elif three_miss:
                predicted, confidence = "Q", "60%"
                logger.info("🔮 PRÉDICTION STATIQUE 4: 3 Q manquants.")
                
            # Règle 5: Combinaison 8, 9, 10 dans G1 ou G2 (70%)
            elif {"8", "9", "10"}.issubset(g1_vals) or {"8", "9", "10"}.issubset(g2_vals):
                predicted, confidence = "Q", "70%"
                logger.info("🔮 PRÉDICTION STATIQUE 5: 8, 9, 10 dans G1 ou G2.")
                
            # Règle de blocage (Q déjà présente dans G1)
            elif "Q" in g1_vals:
                logger.info("Q déjà dans G1 → pas de prédiction")
                return False, None, None
                
            # Règle 6, 7, 8 (Combinées pour 70%)
            else:
                # 6. K+J dans G1
                is_k_j_g1 = "K" in g1_vals and "J" in g1_vals
                # 7. Tag O/R dans le message
                is_o_r_tag = re.search(r'\b[OR]\b', msg)
                # 8. Double G1 faible consécutif (N-1 G1 faible ET N G1/G2 faibles)
                g1_g2_weak_n = not any(h in g1_vals or h in g2_vals for h in HIGH_VALUE_CARDS) # G1 & G2 faibles (N)

                is_prev_g1_weak = False
                prev_entry = self.seq_hist.get(game - 1)
                if prev_entry:
                    prev_vals = [re.match(r'(\d+|[AKQJ])', c).group(1) for c in prev_entry['cartes'] if re.match(r'(\d+|[AKQJ])', c)]
                    is_prev_g1_weak = not any(h in prev_vals for h in HIGH_VALUE_CARDS) # G1 faible (N-1)

                is_double_g1_weak = g1_g2_weak_n and is_prev_g1_weak
                
                if is_k_j_g1 or is_o_r_tag or is_double_g1_weak:
                    predicted, confidence = "Q", "70%"
                    logger.info("🔮 PRÉDICTION STATIQUE 6/7/8: Déclencheur multiple.")

        # --- FINALISATION ---
        if predicted and not self.can_predict():
            logger.warning("⏳ PRÉDICTION ÉVITÉE: En période de 'cooldown'.")
            return False, None, None

        if predicted:
            h = hash(msg)
            if h not in self.proc:
                self.proc.add(h)
                self.last = time.time()
                self.save_all()
                # La prédiction inclut la confiance
                return True, game, self.make_prediction(game, predicted, confidence)
                
        return False, None, None

    # ---------- MAKE PREDICTION (Ajout de la Confiance) ----------
    def make_prediction(self, game: int, value: str, confidence: str) -> str:
        """Génère le message de prédiction et l'enregistre avec le niveau de confiance."""
        target = game + 2
        
        text = f"🔵{target}🔵:Valeur Q statut :⏳"
        
        # Ajout du pourcentage de confiance (sauf si c'est INTER)
        if confidence == "INTER":
             text += " (INTER)"
        elif confidence:
             text += f" ({confidence})"

        self.pred[target] = {
            "predicted_costume": value,
            "status": "pending",
            "predicted_from": game,
            "verification_count": 0,
            "message_text": text,
            "message_id": None,
            "confidence": confidence, # Stockage du niveau de confiance
        }
        self.save_all()
        return text

    # ---------- VERIFY (Vérification) ----------
    def verify(self, msg: str) -> Optional[Dict]:
        """Vérifie si le message contient le résultat pour une prédiction en attente (Q)."""
        game = extract_game_number(msg)
        if not game or not self.pred: return None
        
        for pred_game, pred in self.pred.items():
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
                    # On retire le pourcentage de confiance/INTER dans le message final
                    new_text = f"🔵{pred_game}🔵:Valeur Q statut :{symbol}"

                    pred["status"] = f"correct_offset_{offset}"
                    pred["final_message"] = new_text
                    self.save_all()
                    
                    logger.info("Verification SUCCÈS +%s N=%s", offset, game)
                    return {"type": "edit_message", "predicted_game": pred_game, "new_message": new_text}
                    
                if offset == 2 and not q_found:
                    # ÉCHEC à offset +2 - MARQUER ❌
                    new_text = f"🔵{pred_game}🔵:Valeur Q statut :❌"
                    
                    pred["status"] = "failed"
                    pred["final_message"] = new_text
                    self.save_all()
                    
                    logger.info("Verification ÉCHEC +2 N=%s", game)
                    return {"type": "edit_message", "predicted_game": pred_game, "new_message": new_text}
        return None
        
