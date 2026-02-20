"""Régénération d'une image individuelle avec backup."""

import json
import os
import shutil
import time

from src.image_generator import (
    IMAGES_DIR,
    PROJECT_DIR,
    TEXT_DIR,
    _build_character_brief,
    _get_photo_references,
    _load_or_create_character_descriptions,
    _load_prompts_log,
    _page_to_filename,
    _save_prompts_log,
    generate_single_image,
    PAUSE_BETWEEN_CALLS,
)


BACKUP_DIR = os.path.join(PROJECT_DIR, "output", "images_backup")


def _get_next_version(page_id) -> int:
    """Trouve le prochain numéro de version pour le backup."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    base = _page_to_filename(page_id).replace(".png", "")
    version = 1
    while os.path.exists(os.path.join(BACKUP_DIR, f"{base}_v{version}.png")):
        version += 1
    return version


def _backup_image(page_id) -> str | None:
    """Sauvegarde l'image actuelle dans le dossier backup."""
    filename = _page_to_filename(page_id)
    src = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(src):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    base = filename.replace(".png", "")
    version = _get_next_version(page_id)
    dest = os.path.join(BACKUP_DIR, f"{base}_v{version}.png")
    shutil.copy2(src, dest)
    return dest


def regenerate_image(
    config_path: str,
    page_id: str,
    edit_prompt: bool = False,
    cascade: bool = False,
):
    """Régénère une image individuelle."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  [err] book_content.json introuvable.")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    # Trouver la page
    try:
        page_key = int(page_id)
    except ValueError:
        page_key = page_id

    page_data = None
    for p in content["pages"]:
        if str(p["page"]) == str(page_key):
            page_data = p
            break

    if not page_data:
        print(f"  [err] Page '{page_id}' introuvable dans book_content.json")
        return

    if page_data.get("type") not in ("image", "image_and_text"):
        print(f"  [err] La page {page_id} n'est pas une page d'illustration")
        return

    prompt = page_data["image_prompt"]

    # Modifier le prompt si demandé
    if edit_prompt:
        print(f"\n  Prompt actuel pour la page {page_id} :")
        print(f"  {'-' * 40}")
        print(f"  {prompt[:500]}...")
        print(f"  {'-' * 40}")
        print("\n  Entrez les modifications (ou le nouveau prompt complet) :")
        new_prompt = input("  > ").strip()
        if new_prompt:
            prompt = new_prompt
            print("  [ok] Prompt mis a jour")

    # Charger photos de référence et descriptions texte
    print("  [vision] Chargement des references personnages...")
    photo_refs = _get_photo_references(config)
    character_descriptions = _load_or_create_character_descriptions(config)
    character_brief = _build_character_brief(character_descriptions, config)
    enriched_prompt = character_brief + prompt if character_brief else prompt

    # Backup
    backup_path = _backup_image(page_key)
    if backup_path:
        print(f"  [backup] {os.path.basename(backup_path)}")

    # Régénérer
    filename = _page_to_filename(page_key)
    filepath = os.path.join(IMAGES_DIR, filename)

    print(f"  [img] Regeneration de {page_id}...", end=" ", flush=True)
    start = time.time()

    success = generate_single_image(
        prompt=enriched_prompt,
        output_path=filepath,
        reference_images=photo_refs if photo_refs else None,
    )

    elapsed = time.time() - start

    # Log
    prompts_log = _load_prompts_log()
    prompts_log.append({
        "page": str(page_key),
        "prompt": enriched_prompt,
        "original_prompt": prompt,
        "success": success,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(elapsed, 1),
        "regeneration": True,
    })
    _save_prompts_log(prompts_log)

    if success:
        print(f"[ok] ({elapsed:.1f}s)")
        print(f"  [ok] Page {page_id} regeneree. Lancez --step pdf pour reassembler le livre.")
    else:
        print(f"[err] ({elapsed:.1f}s)")
        print(f"  [err] Echec de la regeneration")
        # Restaurer le backup
        if backup_path and os.path.exists(backup_path):
            shutil.copy2(backup_path, filepath)
            print("  [restore] Image precedente restauree")
        return

    # Mode cascade (couverture)
    if cascade and str(page_key) == "cover_front":
        print("\n  [info] La couverture a change.")
        resp = input("  Regenerer les autres images avec ce nouveau style ? (o/n) : ").strip().lower()
        if resp in ("o", "oui", "y", "yes"):
            # Collecter les autres pages image
            other_pages = []
            for p in content["pages"]:
                if p.get("type") in ("image", "image_and_text"):
                    if str(p["page"]) != "cover_front":
                        other_pages.append(p)

            # Trier
            def sort_key(p):
                page = p["page"]
                if page == "cover_back":
                    return (0, 0)
                return (1, int(page))

            other_pages.sort(key=sort_key)

            print(f"\n  [img] Regeneration cascade : {len(other_pages)} images...")
            for idx, p in enumerate(other_pages, 1):
                pid = p["page"]
                fname = _page_to_filename(pid)
                fpath = os.path.join(IMAGES_DIR, fname)

                # Backup
                _backup_image(pid)

                page_prompt = p["image_prompt"]
                enriched = character_brief + page_prompt if character_brief else page_prompt

                print(f"  [{idx}/{len(other_pages)}] {pid}...", end=" ", flush=True)
                s = time.time()

                ok = generate_single_image(
                    prompt=enriched,
                    output_path=fpath,
                    reference_images=photo_refs if photo_refs else None,
                )

                el = time.time() - s
                print(f"[{'ok' if ok else 'err'}] ({el:.1f}s)")

                if idx < len(other_pages):
                    time.sleep(PAUSE_BETWEEN_CALLS)

            print(f"\n  [ok] Cascade terminee. Lancez --step pdf pour reassembler.")
