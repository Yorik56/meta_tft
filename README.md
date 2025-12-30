# Meta TFT - Scraper & Google Sheet

Outil d'automatisation pour scraper les meilleures compositions TFT de `tactics.tools` et les injecter dans un Google Sheet formaté.

## 🛠️ Installation

```bash
# Environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Dépendances
pip install -r requirements.txt
```

## ⚙️ Configuration

1. **Google Sheets** : Placez `credentials.json` à la racine et partagez votre Sheet avec l'email du compte de service.
2. **Environnement** : Créez un fichier `.env` :

```env
OPENAI_API_KEY="votre_cle"
GOOGLE_SHEET_ID="votre_id_sheet"
META_MIN_CHAMPIONS="8"
```

## 📂 Fonctionnement

- **`scrape_meta.py`** : Scrape `tactics.tools`, extrait les coûts/items réels, identifie les compos Reroll (3⭐) et dédoublonne les variantes via GPT-4o. Met à jour `meta.yaml`.
- **`update_google_sheet.py`** : Formate et injecte les données de `meta.yaml` dans Google Sheets (couleurs par coût, images, alignements).

## 🎮 Utilisation

Mise à jour complète (recommandé) :
```bash
./venv/bin/python scrape_meta.py && ./venv/bin/python update_google_sheet.py
```

Lancement individuel :
```bash
./venv/bin/python scrape_meta.py          # Scraper uniquement
./venv/bin/python update_google_sheet.py  # Mise à jour Sheet uniquement
```
