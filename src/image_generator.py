"""Génération des illustrations via l'API OpenAI gpt-image-1 / Responses API."""

import base64
import io
import json
import os
import time

from openai import OpenAI
from PIL import Image


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
TEXT_DIR = os.path.join(OUTPUT_DIR, "text")
PROMPTS_LOG_PATH = os.path.join(OUTPUT_DIR, "prompts_log.json")
CHARACTER_DESCRIPTIONS_PATH = os.path.join(TEXT_DIR, "character_descriptions.json")

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]
PAUSE_BETWEEN_CALLS = 2
TIMEOUT = 120
TARGET_SIZE = 2400

# Style header injecté dans tous les prompts pour cohérence visuelle entre pages
STYLE_HEADER = (
    "Soft watercolor children's book illustration, round and gentle art style, "
    "warm and magical atmosphere, square 1:1 format, no text, no letters anywhere in the image. "
)

# Version du cache des descriptions — incrémenter force la régénération
DESCRIPTIONS_VERSION = "2"


def _load_prompts_log() -> list:
    if os.path.exists(PROMPTS_LOG_PATH):
        with open(PROMPTS_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_prompts_log(log: list):
    with open(PROMPTS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _page_to_filename(page) -> str:
    if isinstance(page, str):
        return f"{page}.png"
    return f"page_{int(page):02d}.png"


def _encode_image_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _upscale_image(input_path: str, output_path: str, target_size: int = TARGET_SIZE):
    img = Image.open(input_path)
    img = img.resize((target_size, target_size), Image.LANCZOS)
    img.save(output_path, "PNG", dpi=(300, 300))


def _get_photo_references(config: dict) -> list[str]:
    """
    Retourne les chemins des photos de référence des personnages
    (enfant principal + personnages secondaires).
    """
    refs = []
    child_photo = config.get("child", {}).get("photo", "")
    if child_photo:
        path = os.path.join(PROJECT_DIR, child_photo)
        if os.path.exists(path):
            refs.append(path)

    for char in config.get("secondary_characters", []):
        char_photo = char.get("photo", "")
        if char_photo:
            path = os.path.join(PROJECT_DIR, char_photo)
            if os.path.exists(path):
                refs.append(path)

    return refs


def generate_single_image(
    prompt: str,
    output_path: str,
    reference_images: list[str] | None = None,
    size: str = "1024x1024",
) -> bool:
    """
    Génère une image.

    Si reference_images est fourni : utilise la Responses API d'OpenAI
    qui envoie les photos au modèle comme référence visuelle réelle.

    Sinon : utilise images.generate() classique.

    Returns:
        True si succès, False si échec après retries.
    """
    client = OpenAI()

    for attempt in range(MAX_RETRIES):
        try:
            if reference_images:
                image_b64 = _generate_with_references(client, prompt, reference_images, size)
            else:
                result = client.images.generate(
                    model="gpt-image-1",
                    prompt=STYLE_HEADER + prompt,
                    n=1,
                    size=size,
                    quality="high",
                )
                image_b64 = result.data[0].b64_json

            image_bytes = base64.b64decode(image_b64)
            temp_path = output_path + ".tmp.png"
            with open(temp_path, "wb") as f:
                f.write(image_bytes)
            _upscale_image(temp_path, output_path)
            os.remove(temp_path)
            return True

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"    [warn] Erreur (tentative {attempt + 1}/{MAX_RETRIES}) : {e}")
                print(f"    [...] Nouvelle tentative dans {delay}s...")
                time.sleep(delay)
            else:
                print(f"    [err] Echec apres {MAX_RETRIES} tentatives : {e}")
                return False


def _generate_with_references(
    client: OpenAI,
    prompt: str,
    reference_images: list[str],
    size: str,
) -> str:
    """
    Génération avec photo de référence.

    Deux modes selon si le personnage apparaît dans la scène :
    - images.edit()     : personnage présent → photo envoyée à l'API pour ancrage visuel
    - images.generate() : personnage absent (décor, objet…) → génération sans référence

    Structure du prompt images.edit() (deux couches) :
    Couche 1 — instructions de transformation avec CRITICAL + description physique
    Couche 2 — prompt de scène avec STYLE_HEADER répété pour cohérence de style
    """
    primary_photo = next((p for p in reference_images if os.path.exists(p)), None)

    if not primary_photo:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=STYLE_HEADER + prompt,
            n=1,
            size=size,
            quality="high",
        )
        return result.data[0].b64_json

    # ── Extraire la description physique et la scène depuis le prompt enrichi ──
    physical_desc = ""
    scene_prompt = prompt
    char_names = []

    if "[CHARACTER APPEARANCE" in prompt and "[END REFERENCE]" in prompt:
        brief_start = prompt.index("[CHARACTER APPEARANCE")
        brief_end = prompt.index("[END REFERENCE]") + len("[END REFERENCE]")
        brief_content = prompt[brief_start:brief_end]
        scene_prompt = prompt[brief_end:].strip()

        for line in brief_content.split("\n"):
            line = line.strip()
            if line and not line.startswith("["):
                # Ligne format "Nom: description..." — extraire le nom
                if ":" in line:
                    char_names.append(line.split(":")[0].strip())
                physical_desc += line + " "
        physical_desc = physical_desc.strip()

    # ── Détection : le personnage principal apparaît-il dans cette scène ? ─────
    # Vérification sur le scene_prompt COMPLET (avant nettoyage) pour ne pas
    # rater un nom mentionné uniquement dans [PERSONNAGES].
    character_in_scene = True  # par défaut : utiliser la référence
    if char_names and scene_prompt:
        character_in_scene = any(name.lower() in scene_prompt.lower() for name in char_names)

    if not character_in_scene:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=STYLE_HEADER + scene_prompt,
            n=1,
            size=size,
            quality="high",
        )
        return result.data[0].b64_json

    # ── Supprimer [PERSONNAGES] du prompt de scène ────────────────────────────
    # Quand on utilise une référence visuelle (avatar aquarelle), la section
    # [PERSONNAGES] générée par Claude peut contredire l'avatar et provoquer
    # une dérive du personnage au fil des pages. On la supprime : l'avatar
    # EST la fiche personnage visuelle, inutile de la répéter en texte.
    clean_scene = scene_prompt
    if "[PERSONNAGES]" in clean_scene:
        for next_sec in ["[SCÈNE]", "[DECOR]", "[DÉCOR]", "[AMBIANCE]", "[TECHNIQUE]"]:
            if next_sec in clean_scene:
                clean_scene = clean_scene[clean_scene.index(next_sec):]
                break

    # ── Préparer l'image de référence en PNG 1024x1024 ────────────────────────
    img = Image.open(primary_photo).convert("RGB")
    img = img.resize((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    # ── Construire l'edit_prompt (deux couches) ────────────────────────────────
    # Phrasing neutre "reference illustration" (valide que ce soit une photo
    # réelle ou un avatar aquarelle déjà stylisé).
    if physical_desc:
        layer1 = (
            "Use this reference illustration of the character as the visual base. "
            f"CRITICAL: keep exactly the same character — same face, {physical_desc}, "
            "same physical appearance as shown in the reference. "
            "Generate a completely new illustrated scene with this exact same character. "
            "No text or letters anywhere in the image."
        )
    else:
        layer1 = (
            "Use this reference illustration of the character as the visual base. "
            "CRITICAL: keep exactly the same character — same face, hair color and style, "
            "skin tone, and physical appearance as shown in the reference. "
            "Generate a completely new illustrated scene with this exact same character. "
            "No text or letters anywhere in the image."
        )

    # Couche 2 : scène nettoyée + style header pour cohérence inter-pages
    edit_prompt = f"{layer1}\n\nScene: {STYLE_HEADER}{clean_scene}"

    result = client.images.edit(
        model="gpt-image-1",
        image=("reference.png", buf.getvalue(), "image/png"),
        prompt=edit_prompt,
        n=1,
        size=size,
    )

    return result.data[0].b64_json


def generate_avatar(
    photo_path: str,
    name: str,
    physical_desc: str = "",
    output_path: str = "",
) -> bool:
    """
    Génère l'avatar aquarelle canonique d'un personnage à partir de sa photo.

    Cet avatar est ensuite utilisé comme RÉFÉRENCE pour toutes les illustrations
    du livre (à la place de la photo réelle). Avantage : images.edit() avec une
    aquarelle en entrée → cohérence de style maximale entre toutes les pages.
    """
    client = OpenAI()

    img = Image.open(photo_path).convert("RGB")
    img = img.resize((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    if physical_desc:
        prompt = (
            f"Transform this reference photo into a soft watercolor children's book character portrait. "
            f"CRITICAL: faithfully reproduce the exact facial features, {physical_desc}, "
            f"and physical appearance from the reference photo. "
            f"Full body illustration of {name} on a simple plain white background. "
            f"Natural friendly pose, character clearly visible from head to toe. "
            f"Soft watercolor style, round and gentle art, warm expression. "
            f"No text or letters anywhere in the image."
        )
    else:
        prompt = (
            f"Transform this reference photo into a soft watercolor children's book character portrait. "
            f"CRITICAL: faithfully reproduce the exact facial features, hair color and style, "
            f"skin tone, and physical appearance from the reference photo. "
            f"Full body illustration of {name} on a simple plain white background. "
            f"Natural friendly pose, character clearly visible from head to toe. "
            f"Soft watercolor style, round and gentle art. "
            f"No text or letters anywhere in the image."
        )

    for attempt in range(MAX_RETRIES):
        try:
            result = client.images.edit(
                model="gpt-image-1",
                image=("reference.png", buf.getvalue(), "image/png"),
                prompt=prompt,
                n=1,
                size="1024x1024",
            )
            image_b64 = result.data[0].b64_json
            image_bytes = base64.b64decode(image_b64)

            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                temp_path = output_path + ".tmp.png"
                with open(temp_path, "wb") as f:
                    f.write(image_bytes)
                _upscale_image(temp_path, output_path)
                os.remove(temp_path)
            return True

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
            else:
                print(f"[err] Echec generation avatar {name}: {e}")
                return False
    return False


# ── Descriptions texte (cache, utilisées comme contexte additionnel) ──────────

def _analyze_character_photo(photo_path: str, name: str, role: str) -> str:
    """Analyse une photo avec GPT-4o Vision pour extraire une description physique."""
    client = OpenAI()
    b64 = _encode_image_b64(photo_path)
    ext = os.path.splitext(photo_path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"This image will be used as a visual reference for drawing a fictional character "
                        f"named {name} in a children's book illustration. "
                        f"Describe only the visible physical traits useful for an illustrator: "
                        f"hair color, hair texture and length, hairstyle, skin tone, approximate age, "
                        f"eye color if visible, and any clothing or outfit with specific colors. "
                        f"Write a concise description under 100 words starting with '{name} has...'. "
                        f"Do not identify or name any real person."
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}
                }
            ]
        }],
        max_tokens=200
    )
    return response.choices[0].message.content.strip()


def _load_or_create_character_descriptions(config: dict) -> dict:
    """Charge ou crée les descriptions texte des personnages (cache versionné)."""
    cached = {}
    if os.path.exists(CHARACTER_DESCRIPTIONS_PATH):
        with open(CHARACTER_DESCRIPTIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("_version") == DESCRIPTIONS_VERSION:
            cached = {k: v for k, v in data.items() if k != "_version"}
        else:
            print("  [vision] Cache obsolete — regeneration des descriptions (tenue incluse)...")

    characters_to_analyze = []
    child = config.get("child", {})
    if child.get("photo"):
        path = os.path.join(PROJECT_DIR, child["photo"])
        if os.path.exists(path):
            characters_to_analyze.append({
                "key": "child",
                "name": child.get("first_name", "l'enfant"),
                "role": f"child aged {child.get('age', '?')}, {child.get('gender', '')}",
                "photo": path,
            })

    for char in config.get("secondary_characters", []):
        if char.get("photo"):
            path = os.path.join(PROJECT_DIR, char["photo"])
            if os.path.exists(path):
                characters_to_analyze.append({
                    "key": char.get("display_name", "secondary"),
                    "name": char.get("display_name", "personnage"),
                    "role": char.get("relation", "secondary character"),
                    "photo": path,
                })

    if not characters_to_analyze:
        return {}

    descriptions = dict(cached)
    updated = False

    for char in characters_to_analyze:
        key = char["key"]
        if key not in descriptions:
            print(f"  [vision] Analyse photo de {char['name']}...", end=" ", flush=True)
            try:
                desc = _analyze_character_photo(char["photo"], char["name"], char["role"])
                descriptions[key] = desc
                updated = True
                print("[ok]")
            except Exception as e:
                print(f"[warn] {e}")
        else:
            print(f"  [vision] Description de {char['name']} chargee depuis le cache.")

    if updated:
        os.makedirs(TEXT_DIR, exist_ok=True)
        with open(CHARACTER_DESCRIPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump({"_version": DESCRIPTIONS_VERSION, **descriptions}, f, ensure_ascii=False, indent=2)

    return descriptions


def _build_character_brief(descriptions: dict, config: dict) -> str:
    """Construit le bloc de description texte à prépendre aux prompts."""
    if not descriptions:
        return ""

    lines = ["[CHARACTER APPEARANCE - reproduce exactly in the illustration]"]
    child_name = config.get("child", {}).get("first_name", "")
    if "child" in descriptions and child_name:
        lines.append(f"{child_name}: {descriptions['child']}")
    for char in config.get("secondary_characters", []):
        key = char.get("display_name", "secondary")
        name = char.get("display_name", "")
        if key in descriptions and name:
            lines.append(f"{name}: {descriptions[key]}")
    lines.append("[END REFERENCE]")
    lines.append("")
    return "\n".join(lines)


# ── Génération principale ──────────────────────────────────────────────────────

def generate_all_images(config_path: str):
    """Génère toutes les images du livre."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  [err] book_content.json introuvable. Lancez d'abord --step text")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Photos de référence (envoyées directement à l'API)
    photo_refs = _get_photo_references(config)
    if photo_refs:
        print(f"\n  [ref] {len(photo_refs)} photo(s) de reference trouvee(s) - envoyees a l'API pour chaque illustration.")
    else:
        print("\n  [ref] Aucune photo de reference. Generation sans reference visuelle.")

    # Descriptions texte (contexte additionnel dans le prompt)
    print("  [vision] Preparation des descriptions texte...")
    character_descriptions = _load_or_create_character_descriptions(config)
    character_brief = _build_character_brief(character_descriptions, config)

    # Collecter les pages image
    image_pages = [p for p in content["pages"] if p.get("type") in ("image", "image_and_text")]
    total = len(image_pages)

    # Vérifier les images existantes
    existing = [p for p in image_pages if os.path.exists(os.path.join(IMAGES_DIR, _page_to_filename(p["page"])))]
    missing = [p for p in image_pages if not os.path.exists(os.path.join(IMAGES_DIR, _page_to_filename(p["page"])))]

    if existing and missing:
        print(f"  [info] {len(existing)} images deja generees, {len(missing)} manquantes.")
        pages_to_generate = missing
    elif existing and not missing:
        print(f"  [info] Toutes les {len(existing)} images existent deja.")
        print("  -> Utilisez --regenerate pour refaire une image.")
        return
    else:
        pages_to_generate = image_pages

    def sort_key(p):
        page = p["page"]
        if page == "cover_front": return (0, 0)
        if page == "cover_back": return (1, 0)
        return (2, int(page))

    pages_to_generate.sort(key=sort_key)

    prompts_log = _load_prompts_log()
    success_count = 0
    failed_pages = []

    print(f"\n  [img] Generation de {len(pages_to_generate)}/{total} images...\n")

    for idx, p in enumerate(pages_to_generate, 1):
        page_id = p["page"]
        filepath = os.path.join(IMAGES_DIR, _page_to_filename(page_id))
        original_prompt = p["image_prompt"]
        enriched_prompt = character_brief + original_prompt if character_brief else original_prompt

        print(f"  [{idx}/{len(pages_to_generate)}] Generation {page_id}...", end=" ", flush=True)
        start = time.time()

        success = generate_single_image(
            prompt=enriched_prompt,
            output_path=filepath,
            reference_images=photo_refs if photo_refs else None,
        )

        elapsed = time.time() - start
        prompts_log.append({
            "page": page_id,
            "prompt": enriched_prompt,
            "original_prompt": original_prompt,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(elapsed, 1),
            "used_photo_references": len(photo_refs),
        })

        if success:
            print(f"[ok] ({elapsed:.1f}s)")
            success_count += 1
        else:
            print(f"[err] ({elapsed:.1f}s)")
            failed_pages.append(page_id)

        if idx < len(pages_to_generate):
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)
    print(f"\n  [stats] Resultat : {success_count}/{len(pages_to_generate)} images generees")
    if failed_pages:
        print(f"  [err] Images echouees : {', '.join(str(p) for p in failed_pages)}")
        print("  -> Utilisez --retry-failed pour les relancer")
    print(f"  [save] Log sauvegarde : {PROMPTS_LOG_PATH}")


def retry_failed_images(config_path: str):
    """Relance la génération des images échouées."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  [err] book_content.json introuvable.")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    missing = [
        p for p in content["pages"]
        if p.get("type") in ("image", "image_and_text")
        and not os.path.exists(os.path.join(IMAGES_DIR, _page_to_filename(p["page"])))
    ]

    if not missing:
        print("  [ok] Aucune image echouee a relancer.")
        return

    print(f"  [retry] {len(missing)} images a relancer...")

    photo_refs = _get_photo_references(config)
    character_descriptions = _load_or_create_character_descriptions(config)
    character_brief = _build_character_brief(character_descriptions, config)

    prompts_log = _load_prompts_log()
    success_count = 0

    for idx, p in enumerate(missing, 1):
        page_id = p["page"]
        filepath = os.path.join(IMAGES_DIR, _page_to_filename(page_id))
        original_prompt = p["image_prompt"]
        enriched_prompt = character_brief + original_prompt if character_brief else original_prompt

        print(f"  [{idx}/{len(missing)}] Retry {page_id}...", end=" ", flush=True)
        start = time.time()

        success = generate_single_image(
            prompt=enriched_prompt,
            output_path=filepath,
            reference_images=photo_refs if photo_refs else None,
        )

        elapsed = time.time() - start
        prompts_log.append({
            "page": page_id,
            "prompt": enriched_prompt,
            "original_prompt": original_prompt,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(elapsed, 1),
            "retry": True,
        })

        if success:
            print(f"[ok] ({elapsed:.1f}s)")
            success_count += 1
        else:
            print(f"[err] ({elapsed:.1f}s)")

        if idx < len(missing):
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)
    print(f"\n  [stats] Retry : {success_count}/{len(missing)} images recuperees")
