import requests
from bs4 import BeautifulSoup
import yaml
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
import re

# Charger les variables d'environnement (.env contient OPENAI_API_KEY)
load_dotenv()

def scrape_tactics_tools():
    """Scrape les compositions top meta de tactics.tools."""
    url = "https://tactics.tools/team-compositions"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
    }
    
    print(f"Chargement de {url}...")
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    comps = []
    champion_costs = {}

    # Mappage des couleurs de bordure vers les coûts
    COLOR_TO_COST = {
        "#bbbbbbe0": 1, # Gris
        "#14cc73e0": 2, # Vert
        "#54c3ffe0": 3, # Bleu
        "#de0ebde0": 4, # Violet
        "#ffc430e0": 5  # Or
    }
    
    for title_el in soup.find_all(['h3', 'h4', 'div']):
        text = title_el.get_text(strip=True)
        if '&' in text and len(text) < 60:
            container = title_el.find_parent('div', class_=lambda x: x and 'p-2' in x) or title_el.parent
            
            # Extraire les champions et leurs items de manière structurée
            champion_data = []
            
            # Tenter d'extraire le placement moyen pour le classement dynamique
            avg_place = "4.5" # Valeur par défaut (B)
            # On cherche tous les divs dans le container
            all_divs = container.find_all('div')
            for i, d in enumerate(all_divs):
                txt = d.get_text(strip=True)
                if txt == 'Place' and i + 1 < len(all_divs):
                    # Le placement est souvent le div juste après
                    avg_place = all_divs[i+1].get_text(strip=True)
                    # Vérifier que c'est bien un nombre
                    if not re.match(r'^\d\.\d+$', avg_place):
                        # Si c'est pas le div suivant, on cherche un peu plus loin
                        for j in range(i+1, min(i+4, len(all_divs))):
                            potential = all_divs[j].get_text(strip=True)
                            if re.match(r'^\d\.\d+$', potential):
                                avg_place = potential
                                break
                    break
            unit_containers = container.find_all('div', class_=lambda x: x and 'items-center' in x and 'flex-col' in x)
            
            if not unit_containers:
                unit_containers = container.find_all('div', class_=lambda x: x and 'relative' in x and 'flex-shrink-0' in x)

            for unit_div in unit_containers:
                img = unit_div.find('img', alt=True)
                if not img or len(img['alt']) > 25: continue
                
                champ_name = img['alt']
                
                # Coût via bordure
                classes = img.get('class', [])
                for cls in classes:
                    if 'border-[' in cls:
                        hex_color = cls.replace('border-[', '').replace(']', '')
                        if hex_color in COLOR_TO_COST:
                            champion_costs[champ_name] = COLOR_TO_COST[hex_color]
                
                # Items du champion dans la compo
                items = []
                item_imgs = unit_div.find_all('img', alt=True)
                for item_img in item_imgs:
                    item_alt = item_img['alt']
                    if item_alt != champ_name and len(item_alt) > 3:
                        items.append(item_alt)
                
                champion_data.append({
                    "name": champ_name,
                    "items": items
                })

            if any(c['name'] == text for c in comps):
                continue
                
            comps.append({
                "name": text,
                "champions": champion_data,
                "avg_place": avg_place
            })
            
            if len(comps) >= 20:
                break
                
    return comps, champion_costs

def generate_yaml_with_openai(raw_data, cost_mapping):
    """Utilise OpenAI pour formater les données brutes selon le nouveau schéma avec champions_db."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = f"""
Tu es un expert TFT (Teamfight Tactics). Voici des données brutes de compositions meta.
Ta mission est de les transformer en un fichier YAML structuré.

### DONNÉES BRUTES (Compositions et champions avec items scrappés) :
{json.dumps(raw_data, indent=2)}

### MAPPAGE DES COÛTS (IMPORTANT) :
{json.dumps(cost_mapping, indent=2)}

### FORMAT ATTENDU :
```yaml
meta:
  - classement: "S" (ou S+, A+, A, B selon l'avg_place)
    compo: "Nom de la compo"
    early_chercher: "Champion1 / Champion2 / ..."
    carries: "Champion1 / Champion2"
    synergies: ["Trait1", "Trait2"]
    compo_complete: "Liste des 7-9 champions"
    champions: 
      - name: "Champ1"
        stars: 2
      - name: "Champ2"
        stars: 2
      - name: "Champ3"
        stars: 3
      - name: "Champ4"
        stars: 2
      - name: "Champ5"
        stars: 2
      - name: "Champ6"
        stars: 2
      - name: "Champ7"
        stars: 2
      - name: "Champ8"
        stars: 2

champions_db:
  "Nom":
    cost: prix_gold (1 à 5)
    traits: ["Trait1", "Trait2"]
    items: ["Item1", "Item2", "Item3"]
```

### INSTRUCTIONS CRITIQUES :
1. **CLASSEMENT DYNAMIQUE** : Utilise le champ `avg_place` pour déterminer le `classement` (Tier) :
   - `avg_place` < 4.15  => **S+**
   - `avg_place` 4.15 - 4.25 => **S**
   - `avg_place` 4.25 - 4.35 => **A+**
   - `avg_place` 4.35 - 4.45 => **A**
   - `avg_place` > 4.45 => **B**
2. **DÉDOUBLONNAGE** : Ne garde qu'une seule variante par synergie principale (le meilleur classé).
2. **SYNERGIES** : La liste `synergies` ne doit contenir QUE des noms de traits (ex: "Noxus", "Void"), JAMAIS de noms de champions.
3. **EARLY GAME (STRICT)** : Le champ `early_chercher` doit aider le joueur à savoir quoi acheter aux niveaux 3, 4 et 5 (Stage 2). 
   - Choisis UNIQUEMENT des champions de coût 1, 2 ou 3.
   - **INTERDICTION ABSOLUE** de mettre des champions à 4 ou 5 golds dans `early_chercher`. 
   - Ces champions DOIVENT avoir un rapport direct avec la compo (partager les mêmes traits principaux). Si la compo n'a que des champions chers, invente un début de partie cohérent avec les traits.
4. **LISTE DES CHAMPIONS (CRITIQUE)** : La clé `champions` dans `meta` doit contenir **TOUS** les champions de la composition finale (généralement 7 à 9 champions). C'est ce qui définit le nombre de portraits affichés !
   - Pour chaque champion, mets `stars: 2`.
   - Pour les compos "Reroll", mets `stars: 3` pour les champions carries/tanks clés (coût 1, 2 ou 3).
5. **CHAMPIONS_DB** : Liste TOUS les champions uniques rencontrés.
6. **ITEMS (LE PLUS IMPORTANT)** : 
   - Utilise les items scrappés comme base.
   - **CORRECTION STATISTIQUE** : Si les items scrappés pour un champion carry semblent incomplets ou bizarres, utilise tes connaissances d'expert pour mettre les 3 REELS MEILLEURS ITEMS BIBS (Best In Slot) du set actuel.
   - Un carry AD doit avoir des items AD (Infinity Edge, Last Whisper, etc.).
   - Un carry AP doit avoir des items AP (Jeweled Gauntlet, Spear of Shojin, etc.).
   - Un tank doit avoir des items tank (Warmog, Bramble Vest, etc.).
   - NE METS JAMAIS de nom de champion dans la liste des items.
7. Réponds UNIQUEMENT en YAML.
"""

    print("Appel à OpenAI pour le formatage et la correction des items...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    
    return response.choices[0].message.content.strip()

def main():
    meta_path = "/home/wsl/workspace/meta_tft/meta.yaml"
    
    try:
        raw_comps, cost_mapping = scrape_tactics_tools()
        if not raw_comps:
            print("Aucune composition trouvée.")
            return
            
        print(f"Trouvé {len(raw_comps)} compositions. Nettoyage via OpenAI...")
        
        new_yaml_content = generate_yaml_with_openai(raw_comps, cost_mapping)
        
        if new_yaml_content.startswith("```"):
            new_yaml_content = "\n".join(new_yaml_content.split("\n")[1:-1])
            
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(new_yaml_content)
            
        # Post-nettoyage manuel de sécurité pour l'early_chercher
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                final_data = yaml.safe_load(f)
            
            if final_data and 'meta' in final_data and 'champions_db' in final_data:
                db = final_data['champions_db']
                for comp in final_data['meta']:
                    early_champs = [c.strip() for c in comp.get('early_chercher', '').split('/')]
                    cleaned_early = []
                    for name in early_champs:
                        # Si le champion est dans la DB, on check son coût
                        cost = db.get(name, {}).get('cost', 0)
                        if cost > 0 and cost < 4:
                            cleaned_early.append(name)
                        elif cost == 0:
                            # Si pas dans la DB, on le garde par défaut ou on pourrait l'ignorer
                            # Mais normalement OpenAI l'a mis dans la DB
                            cleaned_early.append(name)
                    
                    if cleaned_early:
                        comp['early_chercher'] = " / ".join(cleaned_early)
                    else:
                        # Fallback : si tout a été supprimé, on cherche des 1-2 golds dans la compo
                        fallback = [c['name'] for c in comp.get('champions', []) if db.get(c['name'], {}).get('cost', 5) < 3]
                        comp['early_chercher'] = " / ".join(fallback[:3]) if fallback else "Early Units"

                with open(meta_path, 'w', encoding='utf-8') as f:
                    yaml.dump(final_data, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Erreur lors du post-nettoyage : {e}")

        print("Mise à jour de meta.yaml réussie !")
        
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    main()
