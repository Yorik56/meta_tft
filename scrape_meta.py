import requests
from bs4 import BeautifulSoup
import yaml
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

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
            
            imgs = container.find_all('img', alt=True)
            elements = []
            for img in imgs:
                alt = img['alt']
                if not alt: continue
                elements.append(alt)
                
                # Essayer de trouver le coût via la classe de bordure
                classes = img.get('class', [])
                for cls in classes:
                    if 'border-[' in cls:
                        hex_color = cls.replace('border-[', '').replace(']', '')
                        if hex_color in COLOR_TO_COST:
                            champion_costs[alt] = COLOR_TO_COST[hex_color]

            if any(c['name'] == text for c in comps):
                continue
                
            comps.append({
                "name": text,
                "elements": list(dict.fromkeys(elements))
            })
            
            if len(comps) >= 8:
                break
                
    return comps, champion_costs

def generate_yaml_with_openai(raw_data, cost_mapping):
    """Utilise OpenAI pour formater les données brutes selon le nouveau schéma avec champions_db."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = f"""
Tu es un expert TFT (Teamfight Tactics). Voici des données brutes de compositions meta extraites de tactics.tools.
Ta mission est de les transformer en un fichier YAML structuré.

### DONNÉES BRUTES (Composition et éléments associés) :
{json.dumps(raw_data, indent=2)}

### MAPPAGE DES COÛTS (IMPORTANT : Utilise ces coûts en priorité !) :
{json.dumps(cost_mapping, indent=2)}

### FORMAT ATTENDU :
Le YAML doit avoir deux clés racines : `meta` et `champions_db`.

```yaml
meta:
  - classement: "S"
    compo: "Nom de la compo"
    early_chercher: "Champion1 / Champion2 / ..."
    carries: "Champion1 / Champion2"
    synergies: ["Trait1", "Trait2"]
    compo_complete: "Liste des 7-8 champions"
    champions: 
      - name: "Nom"
        stars: 2

champions_db:
  "Nom":
    cost: prix_gold (1 à 5)
    traits: ["Trait1", "Trait2"]
    items: ["Item1", "Item2", "Item3"]
```

### INSTRUCTIONS :
1. Dans `meta`, la liste `champions` doit contenir le nom et le niveau d'étoiles VISE (généralement 2, mais 3 pour les champions clés dans les compositions "Reroll").
2. Identifie les compositions "Reroll" (celles qui se basent sur des champions à 1, 2 ou 3 golds passés en 3 étoiles). Pour ces compos, mets `stars: 3` pour les champions principaux (carries et tanks principaux).
3. Dans `champions_db`, liste TOUS les champions uniques rencontrés dans les compositions.
4. Utilise IMPÉRATIVEMENT les coûts fournis dans le 'MAPPAGE DES COÛTS'. Si un champion n'est pas dans le mappage, utilise tes connaissances mais en priorité le mappage.
5. Pour les items, choisis les 3 meilleurs items classiques pour ce champion dans cette compo.
6. Réponds UNIQUEMENT avec le contenu du fichier YAML. Pas de blabla.

Réponse (YAML uniquement) :
"""

    print("Appel à OpenAI pour le formatage...")
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
            print("Aucune composition trouvée. Vérifiez les sélecteurs.")
            return
            
        print(f"Trouvé {len(raw_comps)} compositions.")
        
        # Transformer via OpenAI avec le nouveau format
        new_yaml_content = generate_yaml_with_openai(raw_comps, cost_mapping)
        
        if new_yaml_content.startswith("```"):
            new_yaml_content = "\n".join(new_yaml_content.split("\n")[1:-1])
            
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(new_yaml_content)
            
        print("Mise à jour de meta.yaml réussie avec la base de données champions !")
        
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    main()
