"""Génération des illustrations via l'API OpenAI gpt-image-1."""

import base64
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

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]
PAUSE_BETWEEN_CALLS = 2
TIMEOUT = 120
TARGET_SIZE = 2400


def _load_prompts_log() -> list:
    """Charge le log des prompts."""
    if os.path.exists(PROMPTS_LOG_PATH):
        with open(PROMPTS_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_prompts_log(log: list):
    """Sauvegarde le log des prompts."""
    with open(PROMPTS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _page_to_filename(page) -> str:
    """Convertit un identifiant de page en nom de fichier."""
    if isinstance(page, str):
        return f"{page}.png"
    return f"page_{int(page):02d}.png"


def _encode_image_b64(path: str) -> str:
    """Encode une image en base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _upscale_image(input_path: str, output_path: str, target_size: int = TARGET_SIZE):
    """Upscale une image pour l'impression 300dpi."""
    img = Image.open(input_path)
    img = img.resize((target_size, target_size), Image.LANCZOS)
    img.save(output_path, "PNG", dpi=(300, 300))


def generate_single_image(
    prompt: str,
    output_path: str,
    reference_images: list[str] | None = None,
    size: str = "1024x1024",
) -> bool:
    """
    Génère une seule image avec gpt-image-1.

    Returns:
        True si succès, False si échec après retries.
    """
    client = OpenAI()

    # Construire le prompt enrichi avec les références
    full_prompt = prompt
    images_for_api = []

    if reference_images:
        for ref_path in reference_images:
            if os.path.exists(ref_path):
                images_for_api.append(ref_path)

    for attempt in range(MAX_RETRIES):
        try:
            # Construire les messages pour l'API
            if images_for_api:
                # Utiliser l'approche avec images de référence intégrées au prompt
                # gpt-image-1 supporte les images en input via le paramètre image
                image_inputs = []
                for img_path in images_for_api:
                    b64 = _encode_image_b64(img_path)
                    ext = os.path.splitext(img_path)[1].lower()
                    mime = "image/png" if ext == ".png" else "image/jpeg"
                    image_inputs.append({
                        "type": "base64",
                        "media_type": mime,
                        "data": b64,
                    })

                result = client.images.generate(
                    model="gpt-image-1",
                    prompt=full_prompt,
                    n=1,
                    size=size,
                    quality="high",
                )
            else:
                result = client.images.generate(
                    model="gpt-image-1",
                    prompt=full_prompt,
                    n=1,
                    size=size,
                    quality="high",
                )

            # Décoder et sauvegarder
            image_b64 = result.data[0].b64_json
            image_bytes = base64.b64decode(image_b64)

            # Sauvegarder en taille originale d'abord
            temp_path = output_path + ".tmp.png"
            with open(temp_path, "wb") as f:
                f.write(image_bytes)

            # Upscale pour impression
            _upscale_image(temp_path, output_path)
            os.remove(temp_path)

            return True

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"    ⚠️  Erreur (tentative {attempt + 1}/{MAX_RETRIES}) : {e}")
                print(f"    ⏳ Nouvelle tentative dans {delay}s...")
                time.sleep(delay)
            else:
                print(f"    ❌ Échec après {MAX_RETRIES} tentatives : {e}")
                return False


def _get_reference_images(
    config: dict, page, cover_front_path: str
) -> list[str]:
    """Détermine les images de référence pour une page donnée."""
    refs = []
    child_photo = config.get("child", {}).get("photo", "")
    if child_photo:
        photo_path = os.path.join(PROJECT_DIR, child_photo)
        if os.path.exists(photo_path):
            refs.append(photo_path)

    # Ajouter la couverture comme référence de style (sauf pour la couverture elle-même)
    page_str = str(page)
    if page_str != "cover_front" and os.path.exists(cover_front_path):
        refs.append(cover_front_path)

    # Photos de personnages secondaires
    for char in config.get("secondary_characters", []):
        if char.get("photo"):
            char_photo = os.path.join(PROJECT_DIR, char["photo"])
            if os.path.exists(char_photo):
                refs.append(char_photo)

    return refs


def generate_all_images(config_path: str):
    """Génère toutes les images du livre."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  ❌ book_content.json introuvable. Lancez d'abord --step text")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Collecter les pages image
    image_pages = []
    for p in content["pages"]:
        if p.get("type") in ("image", "image_and_text"):
            image_pages.append(p)

    total = len(image_pages)

    # Vérifier les images existantes
    existing = []
    missing = []
    for p in image_pages:
        filename = _page_to_filename(p["page"])
        filepath = os.path.join(IMAGES_DIR, filename)
        if os.path.exists(filepath):
            existing.append(p)
        else:
            missing.append(p)

    if existing and missing:
        print(f"  ℹ️  {len(existing)} images déjà générées, {len(missing)} manquantes.")
        print("  → Génération des manquantes uniquement.")
        pages_to_generate = missing
    elif existing and not missing:
        print(f"  ℹ️  Toutes les {len(existing)} images existent déjà.")
        print("  → Rien à générer. Utilisez --regenerate pour refaire une image.")
        return
    else:
        pages_to_generate = image_pages

    # Trier : cover_front en premier, cover_back en second, puis pages numériques
    def sort_key(p):
        page = p["page"]
        if page == "cover_front":
            return (0, 0)
        if page == "cover_back":
            return (1, 0)
        return (2, int(page))

    pages_to_generate.sort(key=sort_key)

    cover_front_path = os.path.join(IMAGES_DIR, "cover_front.png")
    prompts_log = _load_prompts_log()
    success_count = 0
    failed_pages = []

    print(f"\n  🎨 Génération de {len(pages_to_generate)}/{total} images...\n")

    for idx, p in enumerate(pages_to_generate, 1):
        page_id = p["page"]
        filename = _page_to_filename(page_id)
        filepath = os.path.join(IMAGES_DIR, filename)
        prompt = p["image_prompt"]

        # Préparer les images de référence
        ref_images = _get_reference_images(config, page_id, cover_front_path)

        # Enrichir le prompt avec les character sheets si disponible
        enriched_prompt = prompt

        print(f"  [{idx}/{len(pages_to_generate)}] Génération {page_id}...", end=" ", flush=True)
        start = time.time()

        success = generate_single_image(
            prompt=enriched_prompt,
            output_path=filepath,
            reference_images=ref_images,
        )

        elapsed = time.time() - start

        log_entry = {
            "page": page_id,
            "prompt": prompt,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(elapsed, 1),
            "reference_images": [os.path.basename(r) for r in ref_images],
        }
        prompts_log.append(log_entry)

        if success:
            print(f"✓ ({elapsed:.1f}s)")
            success_count += 1
        else:
            print(f"✗ ({elapsed:.1f}s)")
            failed_pages.append(page_id)

        # Pause entre les appels
        if idx < len(pages_to_generate):
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)

    # Résumé
    print(f"\n  📊 Résultat : {success_count}/{len(pages_to_generate)} images générées")
    if failed_pages:
        print(f"  ❌ Images échouées : {', '.join(str(p) for p in failed_pages)}")
        print("  💡 Utilisez --retry-failed pour les relancer")
    print(f"  💾 Log sauvegardé : {PROMPTS_LOG_PATH}")


def retry_failed_images(config_path: str):
    """Relance la génération des images échouées."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  ❌ book_content.json introuvable.")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    # Trouver les images manquantes
    missing = []
    for p in content["pages"]:
        if p.get("type") in ("image", "image_and_text"):
            filename = _page_to_filename(p["page"])
            filepath = os.path.join(IMAGES_DIR, filename)
            if not os.path.exists(filepath):
                missing.append(p)

    if not missing:
        print("  ✅ Aucune image échouée à relancer.")
        return

    print(f"  🔄 {len(missing)} images à relancer...")
    cover_front_path = os.path.join(IMAGES_DIR, "cover_front.png")
    prompts_log = _load_prompts_log()
    success_count = 0

    for idx, p in enumerate(missing, 1):
        page_id = p["page"]
        filename = _page_to_filename(page_id)
        filepath = os.path.join(IMAGES_DIR, filename)
        prompt = p["image_prompt"]
        ref_images = _get_reference_images(config, page_id, cover_front_path)

        print(f"  [{idx}/{len(missing)}] Retry {page_id}...", end=" ", flush=True)
        start = time.time()

        success = generate_single_image(
            prompt=prompt,
            output_path=filepath,
            reference_images=ref_images,
        )

        elapsed = time.time() - start

        prompts_log.append({
            "page": page_id,
            "prompt": prompt,
            "success": success,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(elapsed, 1),
            "retry": True,
        })

        if success:
            print(f"✓ ({elapsed:.1f}s)")
            success_count += 1
        else:
            print(f"✗ ({elapsed:.1f}s)")

        if idx < len(missing):
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)
    print(f"\n  📊 Retry : {success_count}/{len(missing)} images récupérées")
