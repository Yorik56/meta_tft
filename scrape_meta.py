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
    
    # Heuristique basée sur la suggestion de l'utilisateur
    # On cherche des titres (h3, h4) qui ressemblent à des noms de compo
    for title_el in soup.find_all(['h3', 'h4', 'div']):
        text = title_el.get_text(strip=True)
        # Les noms de compo sur tactics.tools contiennent souvent '&' ou plusieurs mots
        # et sont dans des conteneurs spécifiques.
        if '&' in text and len(text) < 60:
            # On remonte au parent pour avoir le bloc complet (unités + stats)
            container = title_el.find_parent('div', class_=lambda x: x and 'p-2' in x) or title_el.parent
            
            # Récupérer tous les alts d'images (champions, items, traits)
            imgs = container.find_all('img', alt=True)
            alts = [img['alt'] for img in imgs if img['alt']]
            
            # On évite les doublons de compo
            if any(c['name'] == text for c in comps):
                continue
                
            comps.append({
                "name": text,
                "elements": list(dict.fromkeys(alts)) # Conserver l'ordre sans doublons
            })
            
            if len(comps) >= 8: # On en prend les 8 meilleures
                break
                
    return comps

def generate_yaml_with_openai(raw_data, current_format_example):
    """Utilise OpenAI pour formater les données brutes selon le schéma du fichier meta.yaml."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = f"""
Tu es un expert TFT (Teamfight Tactics). Voici des données brutes de compositions meta extraites de tactics.tools.
Ta mission est de les transformer en un fichier YAML en suivant STRICTEMENT le format fourni dans l'exemple.

### DONNÉES BRUTES (Composition et éléments associés) :
{json.dumps(raw_data, indent=2)}

### EXEMPLE DE FORMAT CIBLE (meta.yaml actuel) :
```yaml
{current_format_example}
```

### INSTRUCTIONS :
1. Produis un YAML avec deux clés racines : `meta` (liste) et `meilleurs_items` (dictionnaire).
2. Pour `classement`, évalue selon l'ordre des données (le premier est "S" ou "A (top)", puis "A", "A-", "B").
3. Pour `early_chercher`, suggère 3-4 champions du set actuel qui sont bons en early/mid pour cette compo.
4. Pour `carries`, identifie les 1-2 champions principaux (ceux qui ont généralement des items).
5. Pour `synergies`, identifie les traits principaux affichés dans le nom ou les unités.
6. Pour `compo_complete`, liste les 7-8 champions finaux séparés par des virgules.
7. Pour `champions`, liste les noms des champions dans un tableau JSON.
        8. Dans `meilleurs_items`, pour chaque champion carry important, liste 3 items optimaux basés sur les éléments fournis ou tes connaissances du set actuel affiché.
9. Réponds UNIQUEMENT avec le contenu du fichier YAML. Pas de blabla, pas de blocs de code markdown (pas de ```yaml).

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
    # 1. Lire le format actuel pour l'exemple
    meta_path = "/home/wsl/workspace/meta_tft/meta.yaml"
    with open(meta_path, 'r', encoding='utf-8') as f:
        current_meta = f.read()
    
    # 2. Scraper les données
    try:
        raw_comps = scrape_tactics_tools()
        if not raw_comps:
            print("Aucune composition trouvée. Vérifiez les sélecteurs.")
            return
            
        print(f"Trouvé {len(raw_comps)} compositions.")
        for i, c in enumerate(raw_comps):
            print(f"[{i}] {c['name']} - Elements: {len(c['elements'])}")
        
        # 3. Transformer via OpenAI
        new_yaml_content = generate_yaml_with_openai(raw_comps, current_meta)
        
        # Nettoyage si OpenAI a mis des backticks (sécurité)
        if new_yaml_content.startswith("```"):
            new_yaml_content = "\n".join(new_yaml_content.split("\n")[1:-1])
            
        # 4. Sauvegarder
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(new_yaml_content)
            
        print("Mise à jour de meta.yaml réussie !")
        
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    main()

