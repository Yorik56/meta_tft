# Meta TFT - Mise à jour Google Sheet Automatisée

Ce projet permet de scraper automatiquement les meilleures compositions Teamfight Tactics (TFT) depuis `tactics.tools` et de les injecter dans un Google Sheet avec un design professionnel et moderne.

## 🚀 Fonctionnalités

- **Scraping Intelligent** : Récupère le top 20 des compositions et utilise l'IA (GPT-4o) pour dédoublonner les variantes et ne garder que les meilleures compos uniques.
- **Données Réelles** : Extraction automatique des coûts en gold (via la couleur des bordures) et des items exacts recommandés pour chaque champion.
- **Conseils de Jeu** : Identification automatique des compositions "Reroll" avec recommandation des champions à passer en 3 étoiles (⭐⭐⭐).
- **Design Premium** : 
  - Mode sombre (Slate-900).
  - Alignement parfait (tout est centré).
  - Couleurs de fond dynamiques selon le coût en gold (Gris, Vert, Bleu, Violet, Or).
  - Icônes de synergies nettes (40x40px) avec colonnes larges pour la lisibilité.
- **Base de données centralisée** : Utilisation d'un `champions_db` dans le YAML pour garantir la cohérence des items et des coûts.

## 🛠️ Installation

1. Créer un environnement virtuel Python :
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. Configurer les credentials Google Cloud :
   - Placez votre fichier `credentials.json` (compte de service) à la racine du projet.
   - Partagez votre Google Sheet avec l'adresse email du compte de service.

## ⚙️ Configuration (.env)

Créez un fichier `.env` à la racine :

```env
OPENAI_API_KEY="votre_cle_openai"
GOOGLE_SHEET_ID="votre_id_google_sheet"
META_MIN_CHAMPIONS="8"  # Largeur minimale du tableau (en colonnes champions)
```

## 📂 Structure des données (meta.yaml)

Le fichier est géré automatiquement mais suit cette structure :
- `meta` : Liste des compositions (classement, carry, synergies, liste des champions).
- `champions_db` : Base de données unique par champion (coût, items réels, traits).

## 🎮 Utilisation

### 1. Mise à jour complète (Scraping + Sheet)
C'est la commande recommandée pour tout rafraîchir d'un coup :
```bash
./venv/bin/python scrape_meta.py && ./venv/bin/python update_google_sheet.py
```

### 2. Scraper uniquement
Récupère les données de `tactics.tools` et met à jour `meta.yaml`.
```bash
./venv/bin/python scrape_meta.py
```

### 3. Mettre à jour le Sheet uniquement
Injecte les données actuelles de `meta.yaml` dans Google Sheets.
```bash
./venv/bin/python update_google_sheet.py
```

## 🎨 Design du Google Sheet

Le tableau est structuré ainsi :
- **A** : Classement méta (S, A, etc.) en Or.
- **B..D** : Infos de compo (Nom, Early, Carries).
- **E** : Synergies (Icônes nettes + noms).
- **F..N** : Champions & Items (Triés par coût, colorés par rareté, avec étoiles ⭐).

---
*Note : Les images sont récupérées dynamiquement via les CDNs de CommunityDragon, MetaTFT et Data Dragon.*
