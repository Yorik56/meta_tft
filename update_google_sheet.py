#!/usr/bin/env python3
"""
Script pour mettre à jour un Google Sheet avec les données de méta TFT depuis un fichier YAML.
Version corrigée avec structure de colonnes dynamique.
"""

import yaml
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import unicodedata
import difflib

import requests
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
YAML_FILE = "meta.yaml"
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
]

DD_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DD_CDN_BASE = "https://ddragon.leagueoflegends.com/cdn"
METATFT_CHAMPION_CDN_BASE = "https://cdn.metatft.com/file/metatft/champions/"
CDRAGON_TFT_TEAMPLANNER_URL = (
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/tftchampions-teamplanner.json"
)

# Mini table FR -> EN pour éviter des "erreurs bêtes" quand le YAML est en français.
# (On garde volontairement petit; tu peux l'étendre si besoin.)
ITEM_ALIASES: Dict[str, str] = {
    "Archange": "Archangel's Staff",
    "Lame d'infini": "Infinity Edge",
    "Pistolame Hextech": "Hextech Gunblade",
    "Cape solaire": "Sunfire Cape",
    "Armure roncière": "Bramble Vest",
    # NOTE: dans tft-item.json, l'ID `TFT_Item_Redemption` est affiché comme "Spirit Visage"
    "Rédemption": "TFT_Item_Redemption",
    "Redemption": "TFT_Item_Redemption",
    "Warmog": "Warmog's Armor",
    "Guinsoo": "Guinsoo's Rageblade",
    "Morello": "Morellonomicon",
    "Rabadon": "Rabadon's Deathcap",
    "BT": "Bloodthirster",
    # alias FR courants
    "Lame funeste": "Deathblade",
    # Items LoL -> TFT (noms différents)
    "Guardian Angel": "TFT_Item_GuardianAngel",  # = Edge of Night
    "Thornmail": "TFT_Item_BrambleVest",         # = Bramble Vest
}


_MISSING_ITEMS_LOGGED: set[str] = set()

def load_yaml(file_path: str) -> Dict[str, Any]:
    """Charge le fichier YAML."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def init_google_sheets(credentials_file: str = "credentials.json") -> Tuple[gspread.Client, Any, Any]:
    """Initialise la connexion à Google Sheets."""
    if not os.path.exists(credentials_file):
        raise FileNotFoundError(
            f"Le fichier {credentials_file} est introuvable. "
            "Veuillez télécharger vos credentials Google Cloud et les sauvegarder dans credentials.json"
        )
    
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPE)
    client = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)
    return client, service


def _cache_dir() -> Path:
    p = Path(".cache") / "meta_tft"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm_key(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("’", "'").replace("`", "'")
    s = _strip_accents(s)
    s = s.lower()
    # garde alphanum uniquement (supprime espaces, apostrophes, tirets, etc.)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _dd_latest_version() -> str:
    """
    Récupère la dernière version Data Dragon (cache local).
    """
    cache_path = _cache_dir() / "dd_latest_version.txt"
    if cache_path.exists():
        v = cache_path.read_text(encoding="utf-8").strip()
        if v:
            return v
    versions = requests.get(DD_VERSIONS_URL, timeout=30).json()
    v = versions[0]
    cache_path.write_text(v, encoding="utf-8")
    return v


def _dd_lol_champion_index(version: str) -> Dict[str, str]:
    """
    Retourne un mapping normalisé -> champion_id (ex: 'missfortune' -> 'MissFortune')
    pour construire l'URL d'icône LoL en fallback.
    """
    cache_path = _cache_dir() / f"dd_champion_index_{version}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    url = f"{DD_CDN_BASE}/{version}/data/en_US/champion.json"
    data = requests.get(url, timeout=30).json()
    champs = (data or {}).get("data") or {}
    idx: Dict[str, str] = {}
    for _, c in champs.items():
        if not isinstance(c, dict):
            continue
        champ_id = c.get("id")  # ex: MissFortune
        champ_name = c.get("name")  # ex: Miss Fortune
        if isinstance(champ_id, str):
            idx[_norm_key(champ_id)] = champ_id
        if isinstance(champ_name, str) and isinstance(champ_id, str):
            idx[_norm_key(champ_name)] = champ_id

    cache_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx


def _tft_name_to_character_id() -> Dict[str, str]:
    """
    Mapping display_name TFT -> character_id (ex: 'Kennen' -> 'TFT16_Kennen')
    via CommunityDragon teamplanner. Cache local.
    """
    forced_set = os.getenv("TFT_SET_KEY", "").strip()
    cache_suffix = forced_set if forced_set else "ALL"
    cache_path = _cache_dir() / f"tft_name_to_character_id_{cache_suffix}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    raw = requests.get(CDRAGON_TFT_TEAMPLANNER_URL, timeout=45).json()
    idx: Dict[str, str] = {}
    if isinstance(raw, dict):
        items = raw.items()
        if forced_set and forced_set in raw:
            items = [(forced_set, raw[forced_set])]

        for _, entries in items:
            if not isinstance(entries, list):
                continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                name = e.get("display_name")
                cid = e.get("character_id")
                if isinstance(name, str) and isinstance(cid, str):
                    idx[_norm_key(name)] = cid

    cache_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx


def get_champion_image_url(champion: str) -> str:
    """
    Construit dynamiquement l'URL d'icône champion.
    - Priorité: icônes TFT via CDN MetaTFT (fiable, inclut les champions TFT-only)
      grâce au mapping display_name -> character_id.
    - Fallback: icônes LoL Data Dragon (si le champion est un champion LoL classique).
    """
    champ = (champion or "").strip()
    if not champ:
        return ""

    # 1) TFT icons via MetaTFT CDN (tft16_kennen.png, etc.)
    tft_idx = _tft_name_to_character_id()
    cid = tft_idx.get(_norm_key(champ))
    if cid:
        return f"{METATFT_CHAMPION_CDN_BASE}{cid.lower()}.png"

    # 2) LoL icons via Data Dragon
    ver = _dd_latest_version()
    dd_idx = _dd_lol_champion_index(ver)
    champ_id = dd_idx.get(_norm_key(champ))
    if champ_id:
        return f"{DD_CDN_BASE}/{ver}/img/champion/{champ_id}.png"
    return ""


def _dd_tft_item_index(version: str) -> Dict[str, str]:
    """
    Mapping normalisé nom d'item -> image.full (png) à partir de tft-item.json.
    """
    cache_path = _cache_dir() / f"dd_tft_item_index_{version}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    url = f"{DD_CDN_BASE}/{version}/data/en_US/tft-item.json"
    data = requests.get(url, timeout=30).json()
    items = (data or {}).get("data") or {}
    idx: Dict[str, str] = {}
    for _, it in items.items():
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        image = it.get("image") or {}
        full = image.get("full") if isinstance(image, dict) else None
        if isinstance(name, str) and isinstance(full, str):
            idx[_norm_key(name)] = full
        # aussi indexer par id (souvent plus stable)
        it_id = it.get("id")
        if isinstance(it_id, str) and isinstance(full, str):
            idx[_norm_key(it_id)] = full

    cache_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx


def get_item_image_url(item_name: str) -> str:
    """
    Construit dynamiquement l'URL d'icône item TFT via Data Dragon (tft-item),
    avec un petit fallback d'aliases FR -> EN.
    """
    name = (item_name or "").strip()
    if not name:
        return ""

    # alias FR -> EN si applicable
    name = ITEM_ALIASES.get(name, name)

    ver = _dd_latest_version()
    idx = _dd_tft_item_index(ver)
    k = _norm_key(name)
    full = idx.get(k)
    if not full:
        # Fallback: tentative "fuzzy match" (utile quand le YAML a des variations de noms).
        # Exemple: "Giant Slayer" existe mais l'ID TFT est différent; "Rédemption" est un cas spécial, etc.
        matches = difflib.get_close_matches(k, list(idx.keys()), n=1, cutoff=0.88)
        if matches:
            full = idx.get(matches[0])
    if not full:
        # Log une seule fois par item pour aider à nettoyer meta.yaml
        if name not in _MISSING_ITEMS_LOGGED:
            _MISSING_ITEMS_LOGGED.add(name)
            print(f"⚠️  Item introuvable (pas d'icône): {name!r}")
        return ""
    return f"{DD_CDN_BASE}/{ver}/img/tft-item/{full}"


def get_synergy_image_url(synergy_name: str) -> str:
    """
    Construit l'URL de l'icône de synergie via MetaTFT.
    """
    name = (synergy_name or "").strip().lower()
    if not name:
        return ""
    # Nettoyage basique du nom (ex: "Slayer" -> "slayer")
    name = _norm_key(name)
    return f"https://cdn.metatft.com/file/metatft/traits/{name}.png"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_champion_names(text: str) -> List[str]:
    """Parse une chaîne de texte pour extraire les noms de champions."""
    if not text:
        return []
    for separator in ["/", ","]:
        if separator in text:
            return [c.strip() for c in text.split(separator) if c.strip()]
    return [text.strip()] if text.strip() else []

def create_image_formula(url: str, size: int = None) -> str:
    """Crée une formule IMAGE() pour Google Sheets avec une taille optionnelle."""
    if size:
        return f'=IMAGE("{url}"; 4; {size}; {size})'
    return f'=IMAGE("{url}")'

def col_num_to_letter(col_num: int) -> str:
    """Convertit un numéro de colonne (1-indexed) en lettre de colonne (A, B, C, etc.)."""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + (col_num % 26)) + result
        col_num //= 26
    return result

def extract_sheet_id(sheet_input: str) -> str:
    """Extrait l'ID du Google Sheet depuis une URL ou retourne l'ID directement."""
    sheet_input = sheet_input.strip()
    if re.match(r'^[a-zA-Z0-9_-]{30,}$', sheet_input):
        return sheet_input
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', sheet_input)
    if match:
        return match.group(1)
    match = re.match(r'^([a-zA-Z0-9_-]{30,})[/?#]', sheet_input)
    if match:
        return match.group(1)
    return sheet_input

def update_google_sheet(
    client: gspread.Client,
    service: Any,
    spreadsheet_id: str,
    sheet_name: str = "Meta TFT",
    data: Dict[str, Any] = None
):
    """Met à jour le Google Sheet avec les données."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=50)
        
        sheet_id = worksheet.id
        
        # Redimensionner la feuille si nécessaire
        try:
            sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheet_props = None
            for sheet in sheet_metadata.get('sheets', []):
                if sheet['properties']['sheetId'] == sheet_id:
                    sheet_props = sheet['properties']
                    break
            
            if sheet_props:
                current_cols = sheet_props.get('gridProperties', {}).get('columnCount', 0)
                if current_cols < 50:
                    requests = [{
                        'updateSheetProperties': {
                            'properties': {
                                'sheetId': sheet_id,
                                'gridProperties': {'rowCount': 100, 'columnCount': 50}
                            },
                            'fields': 'gridProperties'
                        }
                    }]
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={'requests': requests}
                    ).execute()
                    print(f"✅ Feuille redimensionnée à 50 colonnes")
        except Exception as e:
            print(f"⚠️  Erreur lors du redimensionnement: {e}")
        
        # La nouvelle base de données des champions
        champions_db = data.get("champions_db", {})
        meta_list = data.get("meta", [])
        
        worksheet.clear()

        # --- Structure "Excel-like" dans Google Sheets ---
        items_per_champ = 3
        
        # On récupère le minimum du .env (floor) mais on ne limite pas le maximum (dynamique)
        min_champs_floor = int(os.getenv("META_MIN_CHAMPIONS", "8"))
        max_champs_data = max([len(item.get("champions", [])) for item in meta_list], default=0)
        max_champs = max(max_champs_data, min_champs_floor)
        
        # Colonnes fixes (1-indexed)
        col_classement = 1  # A
        col_compo = 2       # B
        col_early = 3       # C (texte)
        col_carries = 4     # D (texte)
        col_synergies = 5   # E (texte)
        col_champions_start = 6  # F (1 colonne par champion)
        total_cols = col_champions_start + max_champs - 1

        # Construire les lignes à écrire
        header = [""] * total_cols
        header[col_classement - 1] = "Classement méta"
        header[col_compo - 1] = "Compo"
        header[col_early - 1] = "Early à chercher"
        header[col_carries - 1] = "Carries"
        header[col_synergies - 1] = "Synergies"
        header[col_champions_start - 1] = "Champions / Items préférés"

        all_rows: List[List[str]] = [header]
        blocks: List[Tuple[int, int]] = []

        current_row = 2  # 1-indexed (ligne dans Sheets)
        for entry in meta_list:
            champions_data = entry.get("champions", [])
            
            # Enrichir et trier les champions via la DB
            enriched_champs = []
            for c in champions_data:
                name = c["name"]
                db_info = champions_db.get(name, {})
                enriched_champs.append({
                    "name": name,
                    "cost": db_info.get("cost", 1),
                    "stars": c.get("stars", 2),
                    "items": db_info.get("items", [])
                })
            
            # Tri forcé par coût
            enriched_champs.sort(key=lambda x: x["cost"])
            enriched_champs = enriched_champs[:max_champs]

            # Calcul du max items pour la hauteur du bloc
            max_items_in_comp = max((len(c["items"]) for c in enriched_champs), default=0)
            
            # Gestion des synergies (logos + noms)
            synergies_list = entry.get("synergies", [])
            if isinstance(synergies_list, str):
                synergies_list = [s.strip() for s in synergies_list.split("/") if s.strip()]
            
            # Hauteur du bloc
            block_height = max(2 + max_items_in_comp, len(synergies_list) * 2)

            # Ligne d'images (champions + 1ère synergie logo)
            row_image = [""] * total_cols
            row_image[col_classement - 1] = entry.get("classement", "")
            row_image[col_compo - 1] = entry.get("compo", "")
            row_image[col_early - 1] = entry.get("early_chercher", "")
            row_image[col_carries - 1] = entry.get("carries", "")
            
            if synergies_list:
                s_url = get_synergy_image_url(synergies_list[0])
                row_image[col_synergies - 1] = create_image_formula(s_url, size=40) if s_url else ""

            # Portraits champions
            for idx, c in enumerate(enriched_champs):
                url = get_champion_image_url(c["name"])
                if url:
                    row_image[col_champions_start - 1 + idx] = create_image_formula(url)

            # Ligne de noms (+ 1ère synergie nom)
            row_names = [""] * total_cols
            if synergies_list:
                row_names[col_synergies - 1] = synergies_list[0]
                
            for idx, c in enumerate(enriched_champs):
                stars_str = "⭐" * c["stars"]
                name_display = f"{c['name']}\n{stars_str}"
                row_names[col_champions_start - 1 + idx] = name_display

            comp_rows: List[List[str]] = [row_image, row_names]

            # Lignes d'extra (Items et synergies additionnelles)
            for r in range(block_height - 2):
                row_extra = [""] * total_cols
                
                # Synergies suivantes
                syn_idx = (r + 2) // 2
                is_nom = (r % 2 == 1)
                if syn_idx < len(synergies_list):
                    if is_nom:
                        row_extra[col_synergies - 1] = synergies_list[syn_idx]
                    else:
                        s_url = get_synergy_image_url(synergies_list[syn_idx])
                        row_extra[col_synergies - 1] = create_image_formula(s_url, size=40) if s_url else ""
                
                # Items champions
                for idx, c in enumerate(enriched_champs):
                    if r < len(c["items"]):
                        item_url = get_item_image_url(c["items"][r])
                        if item_url:
                            row_extra[col_champions_start - 1 + idx] = create_image_formula(item_url)
                
                comp_rows.append(row_extra)

            all_rows.extend(comp_rows)
            blocks.append((current_row, block_height, enriched_champs))
            current_row += block_height

        # S'assurer que la feuille a assez de lignes/colonnes
        needed_rows = len(all_rows)
        needed_cols = total_cols
        try:
            sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheet_props = None
            for s in sheet_metadata.get("sheets", []):
                if s["properties"]["sheetId"] == sheet_id:
                    sheet_props = s["properties"]
                    break
            if sheet_props:
                gp = sheet_props.get("gridProperties", {})
                cur_r = gp.get("rowCount", 100)
                cur_c = gp.get("columnCount", 26)
                if cur_r < needed_rows or cur_c < needed_cols:
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={
                            "requests": [
                                {
                                    "updateSheetProperties": {
                                        "properties": {
                                            "sheetId": sheet_id,
                                            "gridProperties": {
                                                "rowCount": max(cur_r, needed_rows),
                                                "columnCount": max(cur_c, needed_cols),
                                            },
                                        },
                                        "fields": "gridProperties",
                                    }
                                }
                            ]
                        },
                    ).execute()
        except Exception as e:
            print(f"⚠️  Redimensionnement lignes/colonnes ignoré: {e}")

        # Écriture (texte + formules IMAGE)
        worksheet.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")

        # Style + merges + tailles
        requests: List[Dict[str, Any]] = []

        # --- STYLE GLOBAL (FOND SOMBRE POUR TOUTE LA FEUILLE) ---
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": max(needed_rows + 50, 100),
                    "startColumnIndex": 0,
                    "endColumnIndex": max(needed_cols + 10, 50),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 15/255, "green": 23/255, "blue": 42/255}, # Slate-900
                        "textFormat": {"foregroundColor": {"red": 243/255, "green": 244/255, "blue": 246/255}, "fontSize": 12, "fontFamily": "Roboto"}, # Gray-100, font size increased
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"
            }
        })

        # IMPORTANT: worksheet.clear() n'enlève pas les fusions existantes.
        # On unfuse toute la zone utilisée avant de re-fusionner.
        requests.append({
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": max(needed_rows, 1000),
                    "startColumnIndex": 0,
                    "endColumnIndex": max(needed_cols, 26),
                }
            }
        })

        # Header styling (row 1)
        def _repeat_header(start_col0: int, end_col0: int, rgb: Tuple[int, int, int], text_rgb: Tuple[int, int, int] = (255, 255, 255)) -> None:
            r, g, b = rgb
            tr, tg, tb = text_rgb
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": start_col0,
                        "endColumnIndex": end_col0,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": r/255, "green": g/255, "blue": b/255},
                            "textFormat": {
                                "bold": True, 
                                "foregroundColor": {"red": tr/255, "green": tg/255, "blue": tb/255},
                                "fontSize": 14
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
                }
            })

        # Palette: En-têtes Slate-950 pour un aspect premium
        _repeat_header(0, total_cols, (2, 6, 23)) # Slate-950

        # Fusionner l'en-tête de la colonne F (Champions) jusqu'au bout
        requests.append({
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": col_champions_start - 1,
                    "endColumnIndex": total_cols,
                },
                "mergeType": "MERGE_ALL",
            }
        })

        # Bordures sur l'en-tête (Ligne dorée en bas pour le style TFT)
        requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": total_cols,
                },
                "bottom": {"style": "SOLID_MEDIUM", "width": 3, "color": {"red": 245/255, "green": 158/255, "blue": 11/255}}, # Amber-500
            }
        })

        # Freeze header row
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })

        # Column widths (pixels)
        def col_range(start_col_1: int, end_col_1_excl: int) -> Dict[str, Any]:
            return {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_col_1 - 1,
                "endIndex": end_col_1_excl - 1,
            }

        # A..D
        requests.append({
            "updateDimensionProperties": {
                "range": col_range(1, 2),
                "properties": {"pixelSize": 120}, # Élargi comme demandé
                "fields": "pixelSize",
            }
        })
        requests.append({
            "updateDimensionProperties": {
                "range": col_range(2, 3),
                "properties": {"pixelSize": 180}, # Compo
                "fields": "pixelSize",
            }
        })
        requests.append({
            "updateDimensionProperties": {
                "range": col_range(3, 4),
                "properties": {"pixelSize": 220}, # Early
                "fields": "pixelSize",
            }
        })
        requests.append({
            "updateDimensionProperties": {
                "range": col_range(4, 5),
                "properties": {"pixelSize": 150}, # Carries
                "fields": "pixelSize",
            }
        })
        # E (synergies logos)
        requests.append({
            "updateDimensionProperties": {
                "range": col_range(5, 6),
                "properties": {"pixelSize": 100}, # Augmenté à 100 pour que "Synergies" tienne sur une ligne
                "fields": "pixelSize",
            }
        })
        # Champions (plus compacts)
        if col_champions_start <= total_cols:
            requests.append({
                "updateDimensionProperties": {
                    "range": col_range(col_champions_start, total_cols + 1),
                    "properties": {"pixelSize": 80}, # Réduit de 120 à 80
                    "fields": "pixelSize",
                }
            })

        # Blocks formatting + merges
        for block_idx, (row_start, height, enriched_champs) in enumerate(blocks):
            # Alternance subtile de bleu sombre (Slate-800 vs Slate-900)
            bg = {"red": 30/255, "green": 41/255, "blue": 59/255} if (block_idx % 2 == 0) else {"red": 15/255, "green": 23/255, "blue": 42/255}

            # Style pour le bloc entier (fond par défaut)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start - 1,
                        "endRowIndex": row_start - 1 + height,
                        "startColumnIndex": 0,
                        "endColumnIndex": total_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": bg,
                            "textFormat": {"foregroundColor": {"red": 226/255, "green": 232/255, "blue": 240/255}} # Slate-200
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })

            # --- FOCUS CLASSEMENT (Colonne A) : Texte Doré/Or ---
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start - 1,
                        "endRowIndex": row_start - 1 + height,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "foregroundColor": {"red": 251/255, "green": 191/255, "blue": 36/255}, # Amber-400 (Gold)
                                "bold": True,
                                "fontSize": 12
                            }
                        }
                    },
                    "fields": "userEnteredFormat(textFormat)",
                }
            })

            # --- FOCUS SYNERGIES (Colonne E) : Fond Slate-950 (Plus sombre) ---
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start - 1,
                        "endRowIndex": row_start - 1 + height,
                        "startColumnIndex": 4, # Colonne E
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 2/255, "green": 6/255, "blue": 23/255}, # Slate-950
                            "textFormat": {
                                "foregroundColor": {"red": 248/255, "green": 250/255, "blue": 252/255}, # Slate-50
                                "bold": True,
                                "fontSize": 10 # Remonté à 10px car la colonne est plus large
                            }
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })

            # --- FOCUS CHAMPIONS/ITEMS (Colonnes F+) : Couleur selon le prix en gold (CELLULE PAR CELLULE) ---
            COST_BG_COLORS = {
                1: {"red": 40/255, "green": 55/255, "blue": 75/255}, # Slate-700
                2: {"red": 6/255, "green": 78/255, "blue": 59/255},  # Emerald-900 (Vert)
                3: {"red": 30/255, "green": 58/255, "blue": 138/255}, # Blue-900 (Bleu)
                4: {"red": 88/255, "green": 28/255, "blue": 135/255}, # Purple-900 (Violet)
                5: {"red": 120/255, "green": 53/255, "blue": 15/255},  # Amber-900 (Or)
            }
            
            for idx, c in enumerate(enriched_champs):
                bg_color = COST_BG_COLORS.get(c["cost"], COST_BG_COLORS[1])
                
                # Image champion
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_start - 1,
                            "endRowIndex": row_start,
                            "startColumnIndex": col_champions_start - 1 + idx,
                            "endColumnIndex": col_champions_start + idx,
                        },
                        "cell": {"userEnteredFormat": {"backgroundColor": bg_color}},
                        "fields": "userEnteredFormat(backgroundColor)",
                    }
                })
                # Items
                if height > 2:
                    requests.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_start + 1,
                                "endRowIndex": row_start - 1 + height,
                                "startColumnIndex": col_champions_start - 1 + idx,
                                "endColumnIndex": col_champions_start + idx,
                            },
                            "cell": {"userEnteredFormat": {"backgroundColor": bg_color}},
                    "fields": "userEnteredFormat(backgroundColor)",
                }
            })

            # --- FOCUS NOMS CHAMPIONS (Ligne 2 du bloc) : Texte plus petit et info étoiles ---
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start, # Ligne des noms
                        "endRowIndex": row_start + 1,
                        "startColumnIndex": 5, # Champions start
                        "endColumnIndex": total_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "foregroundColor": {"red": 248/255, "green": 250/255, "blue": 252/255}, # Slate-50
                                "fontSize": 10, # Taille légèrement augmentée pour lisibilité
                                "bold": False # Pas de gras
                            }
                        }
                    },
                    "fields": "userEnteredFormat(textFormat)",
                }
            })

            # Bordures de séparation de bloc (Ligne discrète Slate-700)
            requests.append({
                "updateBorders": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start - 1,
                        "endRowIndex": row_start - 1 + height,
                        "startColumnIndex": 0,
                        "endColumnIndex": total_cols,
                    },
                    "bottom": {"style": "SOLID", "width": 1, "color": {"red": 51/255, "green": 65/255, "blue": 85/255}}, # Slate-700
                    "innerHorizontal": {"style": "DOTTED", "color": {"red": 71/255, "green": 85/255, "blue": 105/255}}, # Slate-600
                }
            })

            # Row heights within block (PLUS COMPACT)
            # image row (champion)
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_start - 1,
                        "endIndex": row_start,
                    },
                    "properties": {"pixelSize": 80}, # Réduit de 110 à 80
                    "fields": "pixelSize",
                }
            })
            # name row (champion + stars) - ON NE LE RÉDUIT PAS
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_start,
                        "endIndex": row_start + 1,
                    },
                    "properties": {"pixelSize": 50}, # Ajusté pour bien voir les étoiles
                    "fields": "pixelSize",
                }
            })
            # item rows (if any)
            if height > 2:
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_start + 1,
                            "endIndex": row_start - 1 + height,
                        },
                        "properties": {"pixelSize": 50}, # Réduit de 70 à 50
                        "fields": "pixelSize",
                    }
                })

            # Merge vertical A..D for the block (no empty under compo)
            for col_idx in range(0, 4):
                requests.append({
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_start - 1,
                            "endRowIndex": row_start - 1 + height,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                })
                # Center text in merged cell
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_start - 1,
                            "endRowIndex": row_start - 1 + height,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,wrapStrategy)",
                    }
                })

            # Formatting pour la colonne E (synergies) sans merge
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_start - 1,
                        "endRowIndex": row_start - 1 + height,
                        "startColumnIndex": 4,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)",
                }
            })

        # --- FINAL TOUCH: Alignement global (Centré partout) ---
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": needed_rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": total_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,wrapStrategy)"
                    }
                })

        if requests:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()
        
        print(f"✅ Google Sheet mis à jour avec succès!")
        print(f"📊 {len(meta_list)} compositions ajoutées")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        raise

def main():
    """Fonction principale."""
    print("🚀 Démarrage de la mise à jour du Google Sheet...")
    print(f"📖 Chargement du fichier {YAML_FILE}...")
    data = load_yaml(YAML_FILE)
    print("✅ Fichier YAML chargé avec succès")
    print("🔐 Connexion à Google Sheets...")
    client, service = init_google_sheets()
    print("✅ Connexion établie")
    # ID par défaut via variable d'environnement
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not spreadsheet_id:
        print("❌ Erreur: GOOGLE_SHEET_ID non défini dans le fichier .env")
        return
        
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Meta TFT")
    print(f"📝 Mise à jour du Google Sheet...")
    update_google_sheet(client, service, spreadsheet_id, sheet_name, data)
    print("✨ Terminé!")

if __name__ == "__main__":
    main()

