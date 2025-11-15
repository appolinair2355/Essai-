# 🤖 Bot Telegram DAME - Déploiement Render.com

## 📋 Variables d'Environnement REQUISES

Configurez ces 4 variables sur Render.com :

1. **BOT_TOKEN** : Votre token Telegram (depuis @BotFather)
2. **ADMIN_CHAT_ID** : Votre ID Telegram personnel
3. **TARGET_CHANNEL_ID** : ID du canal source (format: -1003424179389)
4. **PREDICTION_CHANNEL_ID** : ID du canal de prédiction (format: -1003362820311)

## 🚀 Instructions de Déploiement

### 1. Uploadez les fichiers sur GitHub
- Créez un nouveau dépôt GitHub
- Uploadez TOUS les fichiers du ZIP
- Commitez et poussez

### 2. Créez un Web Service sur Render.com
- Allez sur https://render.com
- Cliquez sur "New +" → "Web Service"
- Connectez votre dépôt GitHub
- Render détectera automatiquement render.yaml

### 3. Configurez les 4 variables d'environnement
- Dans la section "Environment"
- Ajoutez les 4 variables listées ci-dessus
- Cliquez sur "Create Web Service"

### 4. Vérification
- Le déploiement prendra 2-3 minutes
- Dans les logs, vous devriez voir :
  ```
  🤖 BOT TELEGRAM DAME PRÉDICTION - MODE POLLING
  ✅ Bot Token configuré
  ✅ Admin Chat ID: VOTRE_ID
  🚀 Démarrage du polling...
  ```

### 5. Testez le bot
- Envoyez `/start` au bot sur Telegram
- Le bot devrait répondre immédiatement

## ✅ Fonctionnalités

- ✅ Mode Polling (pas de webhook nécessaire)
- ✅ Port dynamique géré par Render
- ✅ 2 règles de prédiction automatique
- ✅ 2 déclencheurs intelligents
- ✅ Vérification automatique des prédictions
- ✅ Logs détaillés

## 🔧 Commandes Disponibles

- `/start` - Démarrer le bot
- `/status` - Voir l'état du mode intelligent
- `/inter` - Analyser les déclencheurs et activer le mode intelligent
- `/defaut` - Désactiver le mode intelligent
- `/deploy` - Générer un nouveau package de déploiement

## ⚠️ Problèmes Courants

**Le bot ne répond pas :**
- Vérifiez que les 4 variables d'environnement sont configurées
- Vérifiez les logs dans Render.com
- Assurez-vous que le BOT_TOKEN est valide

**Erreur 409 Conflict :**
- Le webhook est encore actif
- Le bot supprime automatiquement le webhook au démarrage

**Le bot ne reçoit pas les messages des canaux :**
- Vérifiez que le bot est ajouté aux canaux avec les permissions d'administrateur
- Vérifiez que les IDs de canaux sont au bon format (négatifs)
