# Meta TFT - Mise à jour Google Sheet

Programme Python pour mettre à jour automatiquement un Google Sheet avec les données de méta TFT depuis un fichier YAML.

## Installation

1. Créer un environnement virtuel Python (recommandé) :
```bash
python3 -m venv venv
source venv/bin/activate  # Sur Linux/Mac
# ou
venv\Scripts\activate  # Sur Windows
```

2. Installer les dépendances Python :
```bash
pip install -r requirements.txt
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

### Variables d'environnement (optionnel)

Vous pouvez définir ces variables d'environnement pour éviter de les saisir à chaque exécution :

```bash
export GOOGLE_SHEET_ID="votre_id_google_sheet"
export GOOGLE_SHEET_NAME="Meta TFT"  # Optionnel, "Meta TFT" par défaut
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

Assurez-vous que l'environnement virtuel est activé, puis lancez le script :

```bash
source venv/bin/activate  # Si ce n'est pas déjà fait
python update_google_sheet.py
```

Le programme :
1. Charge le fichier `meta.yaml`
2. Se connecte à Google Sheets
3. Met à jour le Google Sheet avec les données
4. Ajoute les URLs des images des champions et leurs meilleurs items

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

