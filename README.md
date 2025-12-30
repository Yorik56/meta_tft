# Meta TFT - Mise à jour Google Sheet

Programme Python pour mettre à jour automatiquement un Google Sheet avec les données de méta TFT depuis un fichier YAML.

## Installation

1. Créer un environnement virtuel Python :
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
# Installer manuellement les nouveaux outils si nécessaire
pip install beautifulsoup4 openai python-dotenv pyyaml requests
```

2. Configurer les credentials Google Cloud :
   - Allez sur [Google Cloud Console](https://console.cloud.google.com/)
   - Créez un nouveau projet ou sélectionnez un projet existant
   - Activez l'API Google Sheets et Google Drive
   - Créez un compte de service et téléchargez la clé JSON
   - Renommez le fichier téléchargé en `credentials.json` et placez-le à la racine du projet

3. Partager le Google Sheet avec le compte de service :
   - Ouvrez votre Google Sheet
   - Cliquez sur "Partager" et ajoutez l'email du compte de service (trouvable dans credentials.json, champ `client_email`)

## Configuration

### Variables d'environnement

Créez un fichier `.env` à la racine pour stocker vos clés :

```env
OPENAI_API_KEY="votre_cle_openai"
GOOGLE_SHEET_ID="votre_id_google_sheet"
GOOGLE_SHEET_NAME="Meta TFT"  # Optionnel
```

### Fichier YAML

Le fichier `meta.yaml` contient les données de méta. Structure :

```yaml
meta:
  - classement: "A (top)"
    compo: "Ionian Slayers"
    early_chercher: "Yasuo / Yone / Shen / Aphelios"
    carries: "Yasuo / Yone"
    synergies: "Ionia / Slayers"
    compo_complete: "Shen, Aphelios, Yasuo, Yone"
    champions: ["Shen", "Aphelios", "Yasuo", "Yone"]

meilleurs_items:
  "Yasuo": ["Infinity Edge", "Bloodthirster", "Guardian Angel"]
  # ...
```

## Utilisation

Assurez-vous que l'environnement virtuel est activé, puis lancez les scripts :

### 1. Scraper la Meta (Tactics.tools)
Ce script récupère les dernières compositions sur Tactics.tools et met à jour `meta.yaml` via OpenAI.
```bash
python scrape_meta.py
```

### 2. Mettre à jour Google Sheets
Ce script prend les données de `meta.yaml` et les injecte dans votre Google Sheet.
```bash
python update_google_sheet.py
```

## Structure du Google Sheet

Le Google Sheet contiendra les colonnes suivantes :
- Classement méta
- Compo
- Early à chercher
- Carries
- Synergies
- Compo complète
- Icônes champions (URLs des images)
- Meilleurs items (champions avec leurs items recommandés)

## Notes

- Les images des champions utilisent les URLs de Data Dragon de Riot Games
- Vous pouvez modifier les URLs d'images dans le script `update_google_sheet.py` si nécessaire
- Le script efface le contenu existant de la feuille avant d'ajouter les nouvelles données

