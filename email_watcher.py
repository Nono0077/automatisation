"""
Watcher email - Génération automatique de livres depuis Gmail.

============================================================
FORMAT D'UN EMAIL DE COMMANDE
============================================================
Objet : COMMANDE LIVRE

PRENOM: Adam
AGE: 5
GENRE: garcon
THEME: Les pirates magiques
VALEUR: Le courage et l'amitie
LANGUE: fr
DEDICACE: Joyeux anniversaire !
EMAIL_REPONSE: parent@email.com

Champs optionnels :
  TITRE:       Titre suggéré (auto si absent)
  TONALITE:    Ex: Aventurier, Poétique
  TENUE:       Tenue préférée de l'enfant

+ Optionnel : joindre UNE PHOTO de l'enfant (jpg/jpeg/png)

============================================================
LANCEMENT
============================================================
  python email_watcher.py           → polling toutes les 2 min
  python email_watcher.py --once    → traite les mails une seule fois puis quitte
"""

import email
import imaplib
import json
import os
import re
import shutil
import sys
import time
import traceback
import glob as _glob
from email.header import decode_header
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

# ── Constantes ─────────────────────────────────────────────────────────────────

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
POLL_INTERVAL_SECONDS = 120   # toutes les 2 minutes
ORDER_SUBJECT = "COMMANDE LIVRE"
DESKTOP_DIR = str(Path.home() / "Desktop")

CONFIG_PATH  = os.path.join(PROJECT_DIR, "config.json")
PHOTOS_DIR   = os.path.join(PROJECT_DIR, "photos")
IMAGES_DIR   = os.path.join(PROJECT_DIR, "output", "images")
TEXT_DIR     = os.path.join(PROJECT_DIR, "output", "text")
FINAL_DIR    = os.path.join(PROJECT_DIR, "output", "final")
AVATARS_DIR  = os.path.join(PROJECT_DIR, "output", "avatars")
STATUS_PATH  = os.path.join(PROJECT_DIR, "output", "status.json")

# ── Logging ────────────────────────────────────────────────────────────────────

def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ── Gmail IMAP ─────────────────────────────────────────────────────────────────

def _connect_imap() -> imaplib.IMAP4_SSL:
    sender   = os.getenv("GMAIL_SENDER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    if not sender or not password:
        raise RuntimeError("GMAIL_SENDER ou GMAIL_APP_PASSWORD manquant dans .env")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(sender, password)
    return mail

def _decode_header_value(value: str) -> str:
    parts = []
    for part, charset in decode_header(value or ""):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return "".join(parts)

# ── Parsing email body ─────────────────────────────────────────────────────────

def _normalize_key(raw: str) -> str:
    """Normalise une clé email : minuscules, accents retirés, espaces → _."""
    raw = raw.strip().upper()
    replacements = {
        "É": "E", "È": "E", "Ê": "E", "Ë": "E",
        "À": "A", "Â": "A", "Ä": "A",
        "Ô": "O", "Ö": "O", "Ù": "U", "Û": "U", "Ü": "U",
        "Î": "I", "Ï": "I", "Ç": "C",
    }
    for accented, plain in replacements.items():
        raw = raw.replace(accented, plain)
    raw = re.sub(r"\s+", "_", raw)
    raw = re.sub(r"[^A-Z0-9_]", "", raw)
    return raw

def _parse_order_body(body: str) -> dict:
    """
    Parse un corps d'email structuré "CLE: valeur" (une par ligne).
    Retourne un dict avec les clés normalisées (ex: PRENOM, AGE, THEME…).
    """
    data = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key_raw, _, val = line.partition(":")
            key = _normalize_key(key_raw)
            val = val.strip()
            if key and val:
                data[key] = val
    return data

def _get_email_body(msg) -> str:
    """Extrait le corps texte brut d'un email (MIME ou simple)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""

# ── Pièce jointe photo ─────────────────────────────────────────────────────────

def _save_photo_attachment(msg, name_prefix: str) -> str:
    """
    Enregistre la première pièce jointe image (jpg/jpeg/png) dans photos/.
    Retourne le chemin absolu ou "" si aucune photo.
    """
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    for part in msg.walk():
        content_type = part.get_content_type()
        disposition  = str(part.get("Content-Disposition", ""))
        is_attachment = "attachment" in disposition
        is_inline_img = content_type.startswith("image/")

        if is_attachment or is_inline_img:
            filename = part.get_filename()
            if not filename:
                # Générer un nom basé sur content-type
                ext_map = {"image/jpeg": ".jpg", "image/png": ".png"}
                filename = f"photo{ext_map.get(content_type, '.jpg')}"
            filename_decoded = _decode_header_value(filename)
            ext = os.path.splitext(filename_decoded)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png"):
                continue
            dest = os.path.join(PHOTOS_DIR, f"{name_prefix}{ext}")
            payload = part.get_payload(decode=True)
            if payload:
                with open(dest, "wb") as f:
                    f.write(payload)
                _log(f"  Photo sauvegardee : {dest}")
                return dest
    return ""

# ── Construction config ────────────────────────────────────────────────────────

def _build_config(order: dict, photo_path: str = "") -> dict:
    """Construit le dict config.json depuis les champs parsés de l'email."""
    first_name = order.get("PRENOM", "Enfant").strip()

    try:
        age = int(order.get("AGE", "5"))
    except ValueError:
        age = 5

    genre_raw = order.get("GENRE", "neutre").lower().strip()
    genre_map = {
        "garcon": "garçon", "garçon": "garçon", "boy": "garçon",
        "fille": "fille",   "girl": "fille",
        "neutre": "neutre", "neutral": "neutre",
    }
    gender = genre_map.get(genre_raw, "neutre")

    appearance = (
        "Apparence fidele a la photo de reference fournie. "
        "Reproduis exactement les traits du visage, la couleur et la coiffure des cheveux, le teint de la peau."
        if photo_path else
        "Enfant au visage expressif et sympathique, adapte au style aquarelle jeunesse."
    )

    safe_name = re.sub(r"[^a-z0-9_]", "", first_name.lower().replace(" ", "_"))
    photo_rel = ""
    if photo_path:
        rel = os.path.relpath(photo_path, PROJECT_DIR).replace("\\", "/")
        photo_rel = f"./{rel}"

    # Email de réponse : celui fourni dans la commande, ou l'adresse Gmail
    notification_email = order.get("EMAIL_REPONSE", "").strip()
    if not notification_email:
        notification_email = os.getenv("GMAIL_SENDER", "").strip()

    config = {
        "book": {
            "title_suggestion":  order.get("TITRE", "").strip(),
            "language":          order.get("LANGUE", "fr").strip(),
            "theme":             order.get("THEME", "").strip(),
            "educational_value": order.get("VALEUR", "").strip(),
            "tone":              order.get("TONALITE", "").strip(),
            "dedication":        order.get("DEDICACE", "").strip(),
        },
        "child": {
            "first_name":    first_name,
            "age":           age,
            "gender":        gender,
            "appearance":    appearance,
            "default_outfit": order.get("TENUE", "").strip(),
        },
        "secondary_characters": [],
        "options": {
            "include_questions_page": True,
            "number_of_questions":    5,
        },
        "notification_email": notification_email,
    }
    if photo_rel:
        config["child"]["photo"] = photo_rel

    return config

# ── Reset outputs ──────────────────────────────────────────────────────────────

def _reset_output():
    for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR, AVATARS_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    if os.path.exists(STATUS_PATH):
        os.remove(STATUS_PATH)

def _write_status(phase, message, images_done=0, images_total=16, error="", done=False):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "phase": phase, "message": message,
            "images_done": images_done, "images_total": images_total,
            "error": error, "done": done, "ts": time.time(),
        }, f, ensure_ascii=False)

# ── Pipeline de génération ─────────────────────────────────────────────────────

def _run_generation(config: dict) -> str:
    """
    Lance le pipeline complet : Vision → Avatar → Texte → Images → PDF.
    Retourne le chemin du PDF sur le bureau, ou "" en cas d'échec.
    """
    from src.image_generator import (
        generate_single_image, _page_to_filename,
        _get_photo_references, _build_character_brief,
        _load_prompts_log, _save_prompts_log,
        PAUSE_BETWEEN_CALLS, generate_avatar, _analyze_character_photo,
        CHARACTER_DESCRIPTIONS_PATH, DESCRIPTIONS_VERSION,
    )
    import anthropic
    from src.text_generator import _build_user_prompt, _extract_json, SYSTEM_PROMPT, OUTPUT_TEXT_DIR
    from src.pdf_builder import build_pdf
    from src.email_sender import send_book_email

    # Mots-clés indiquant un refus de Vision (GPT-4o refuse parfois les photos de personnes)
    _REFUSAL_PHRASES = [
        "i'm sorry", "i cannot", "i can't", "unable to help",
        "can't help", "not able to", "i apologize", "sorry, but",
    ]

    def _is_valid_desc(text: str) -> bool:
        """Retourne True si la description Vision est exploitable (pas un refus)."""
        if not text or len(text.strip()) < 25:
            return False
        return not any(p in text.lower() for p in _REFUSAL_PHRASES)

    # ── ÉTAPE 1 : Avatar aquarelle + description Vision ───────────────────────
    photo_refs = _get_photo_references(config)
    character_descriptions = {}

    if photo_refs:
        _log("  [1/4] Generation avatar + analyse Vision (GPT-4o)...")
        _write_status("vision", "Analyse photo et generation avatar (GPT-4o Vision)...")

        os.makedirs(AVATARS_DIR, exist_ok=True)
        child      = config.get("child", {})
        child_name = child.get("first_name", "Enfant")
        photo_abs  = os.path.join(PROJECT_DIR, child["photo"].lstrip("./"))

        # — Tentative 1 : Vision sur la photo originale —
        desc = ""
        try:
            raw = _analyze_character_photo(photo_abs, child_name, "child")
            if _is_valid_desc(raw):
                desc = raw
                _log(f"    Vision (photo originale) OK : {desc[:70]}...")
            else:
                _log(f"    [warn] Vision a refuse la photo : {raw[:60]}")
        except Exception as e:
            _log(f"    [warn] Vision error sur photo : {e}")

        # — Génération de l'avatar (100% visuel, ne dépend pas de la desc texte) —
        # L'avatar aquarelle DEVIENT la référence visuelle pour les 16 illustrations.
        avatar_path = os.path.join(AVATARS_DIR, "child_avatar.png")
        _log("    Generation de l'avatar aquarelle depuis la photo...")
        avatar_ok = generate_avatar(photo_abs, child_name, desc, avatar_path)

        if avatar_ok:
            _log("    Avatar OK — utilise comme reference visuelle pour toutes les illustrations.")
            rel = "./" + os.path.relpath(avatar_path, PROJECT_DIR).replace("\\", "/")
            config["child"]["photo"] = rel
            photo_refs = [avatar_path]

            # — Tentative 2 : Vision sur l'avatar (cartoon = moins de risque de refus) —
            if not desc:
                _log("    Vision sur l'avatar aquarelle...")
                try:
                    raw = _analyze_character_photo(avatar_path, child_name, "child")
                    if _is_valid_desc(raw):
                        desc = raw
                        _log(f"    Vision (avatar) OK : {desc[:70]}...")
                    else:
                        _log(f"    [warn] Vision a refuse l'avatar aussi : {raw[:60]}")
                except Exception as e:
                    _log(f"    [warn] Vision error sur avatar : {e}")
        else:
            _log("    [warn] Echec generation avatar — photo originale conservee comme reference.")

        # — Fallback : description générique si Vision a échoué partout —
        if not desc:
            age    = child.get("age", 5)
            gender = child.get("gender", "neutre")
            desc = (
                f"{child_name} has a friendly, expressive face with warm and endearing features, "
                f"typical of a {age}-year-old child."
            )
            _log(f"    Description generique (Vision indisponible) : {desc}")

        # — Enregistrer la description valide —
        character_descriptions["child"] = desc
        config["child"]["appearance"] = desc

        # Sauvegarder dans le cache (lu par _build_character_brief)
        os.makedirs(TEXT_DIR, exist_ok=True)
        with open(CHARACTER_DESCRIPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump({"_version": DESCRIPTIONS_VERSION, **character_descriptions},
                      f, ensure_ascii=False, indent=2)

        _log(f"    Description finale utilisee : {desc[:80]}...")
    else:
        _log("  [1/4] Pas de photo fournie — generation sans reference visuelle.")

    character_brief = _build_character_brief(character_descriptions, config)

    # ── ÉTAPE 2 : Texte avec Claude ───────────────────────────────────────────
    _log("  [2/4] Generation du texte (Claude)...")
    _write_status("text", "Generation du texte avec Claude...")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    client = anthropic.Anthropic()
    user_prompt = _build_user_prompt(config)

    _text_message = None
    for attempt in range(4):
        try:
            _text_message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except Exception as e:
            is_overload = "overloaded" in str(e).lower() or "529" in str(e)
            if is_overload and attempt < 3:
                wait = 30 * (attempt + 1)
                _log(f"    API Claude surchargee, attente {wait}s... ({attempt+1}/4)")
                _write_status("text", f"API Claude surchargee, attente {wait}s...")
                time.sleep(wait)
            else:
                raise

    if _text_message is None:
        raise RuntimeError("Impossible de generer le texte apres 4 tentatives (API surchargee)")

    raw_text = _text_message.content[0].text
    content  = _extract_json(raw_text)

    os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_TEXT_DIR, "book_content.json"), "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    title = content.get("title", "Mon livre")
    image_pages = [p for p in content["pages"] if p.get("type") in ("image", "image_and_text")]

    def sort_key(p):
        page = p["page"]
        if page == "cover_front": return (0, 0)
        if page == "cover_back":  return (1, 0)
        return (2, int(page))
    image_pages.sort(key=sort_key)

    total = len(image_pages)
    _write_status("text_done", f"Texte OK : {title}", images_total=total)
    _log(f"    Texte OK : \"{title}\" ({total} illustrations)")

    # ── ÉTAPE 3 : Illustrations ───────────────────────────────────────────────
    _log("  [3/4] Generation des illustrations (gpt-image-1)...")
    _write_status("images", "Demarrage illustrations...", images_done=0, images_total=total)

    prompts_log = _load_prompts_log()
    for idx, p in enumerate(image_pages):
        page_id  = p["page"]
        filename = _page_to_filename(page_id)
        filepath = os.path.join(IMAGES_DIR, filename)
        original_prompt = p["image_prompt"]
        prompt = character_brief + original_prompt if character_brief else original_prompt

        _log(f"    Illustration {idx+1}/{total} - page {page_id}...")
        _write_status("images", f"Illustration {idx+1}/{total} - page {page_id}",
                      images_done=idx, images_total=total)

        t0 = time.time()
        ok = generate_single_image(
            prompt=prompt,
            output_path=filepath,
            reference_images=photo_refs if photo_refs else None,
        )
        elapsed = time.time() - t0

        prompts_log.append({
            "page": str(page_id), "prompt": prompt,
            "original_prompt": original_prompt,
            "success": ok, "duration_s": round(elapsed, 1),
        })
        _write_status("images", f"Illustration {idx+1}/{total} OK ({elapsed:.0f}s)",
                      images_done=idx+1, images_total=total)
        _log(f"    -> {'OK' if ok else 'ECHEC'} ({elapsed:.0f}s)")

        if idx < total - 1:
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)
    _write_status("images_done", "Toutes les illustrations generees",
                  images_done=total, images_total=total)

    # ── ÉTAPE 4 : PDF ─────────────────────────────────────────────────────────
    _log("  [4/4] Assemblage du PDF...")
    _write_status("pdf", "Assemblage du PDF...", images_done=total, images_total=total)
    build_pdf(CONFIG_PATH)

    pdfs = _glob.glob(os.path.join(FINAL_DIR, "*.pdf"))
    if not pdfs:
        _log("  [err] PDF introuvable apres build_pdf !")
        return ""
    pdf_path = pdfs[0]

    # Copier sur le bureau
    os.makedirs(DESKTOP_DIR, exist_ok=True)
    desktop_pdf = os.path.join(DESKTOP_DIR, os.path.basename(pdf_path))
    shutil.copy2(pdf_path, desktop_pdf)
    _log(f"  PDF copie sur le bureau : {desktop_pdf}")

    _write_status("done", "Livre termine ! PDF sur le bureau.",
                  images_done=total, images_total=total, done=True)

    # Envoyer le PDF par email si notification_email fourni
    notification_email = config.get("notification_email", "").strip()
    if notification_email:
        child_name = config.get("child", {}).get("first_name", "l'enfant")
        ok_email, detail = send_book_email(pdf_path, title, child_name, notification_email)
        if ok_email:
            _log(f"  Email envoye a {notification_email} : {detail}")
        else:
            _log(f"  Email echoue : {detail}")

    return desktop_pdf

# ── Traitement d'un email ──────────────────────────────────────────────────────

def _process_email(mail: imaplib.IMAP4_SSL, email_id: bytes) -> bool:
    """
    Fetch, parse et traite un email de commande.
    Retourne True si la génération s'est terminée avec succès.
    """
    _, data = mail.fetch(email_id, "(RFC822)")
    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = _decode_header_value(msg.get("Subject", ""))
    sender  = msg.get("From", "")
    _log(f"Email recu : '{subject}' de {sender}")

    body  = _get_email_body(msg)
    order = _parse_order_body(body)
    _log(f"  Champs detectes : {list(order.keys())}")

    # Validation minimale
    if not order.get("THEME") and not order.get("VALEUR"):
        _log("  [skip] Champs THEME et VALEUR manquants — email ignore.")
        return False
    if not order.get("THEME"):
        _log("  [skip] Champ THEME manquant — email ignore.")
        return False
    if not order.get("VALEUR"):
        _log("  [skip] Champ VALEUR manquant — email ignore.")
        return False

    # Enregistrer la photo
    first_name = order.get("PRENOM", "enfant")
    safe_name  = re.sub(r"[^a-z0-9_]", "", first_name.lower().replace(" ", "_"))
    photo_path = _save_photo_attachment(msg, safe_name)

    # Construire le config
    config = _build_config(order, photo_path)
    _log(
        f"  Commande : {config['child']['first_name']}, "
        f"{config['child']['age']} ans, "
        f"theme='{config['book']['theme']}'"
    )

    # Réinitialiser les outputs précédents
    _reset_output()

    # Sauvegarder config
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # Lancer la génération
    _log("  Lancement de la generation...")
    try:
        pdf_path = _run_generation(config)
        if pdf_path:
            _log(f"  SUCCES — PDF : {pdf_path}")
            return True
        else:
            _log("  ECHEC — PDF non genere.")
            return False
    except Exception:
        _log(f"  ERREUR :\n{traceback.format_exc()}")
        return False

# ── Polling ────────────────────────────────────────────────────────────────────

def poll_once():
    """Se connecte à Gmail, détecte les emails non lus de commande et les traite."""
    try:
        mail = _connect_imap()
        mail.select("INBOX")

        # Chercher les emails non lus dont le sujet contient ORDER_SUBJECT
        _, msg_ids = mail.search(None, f'(UNSEEN SUBJECT "{ORDER_SUBJECT}")')
        ids = [i for i in msg_ids[0].split() if i]

        if not ids:
            _log("Aucune nouvelle commande.")
            mail.logout()
            return

        _log(f"{len(ids)} commande(s) a traiter.")
        for email_id in ids:
            success = _process_email(mail, email_id)
            # Marquer comme lu pour ne pas retraiter
            mail.store(email_id, "+FLAGS", "\\Seen")
            _log(f"  Email marque comme lu. Succes={success}")

        mail.logout()

    except Exception:
        _log(f"Erreur lors du poll :\n{traceback.format_exc()}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    once = "--once" in sys.argv

    _log("=" * 60)
    _log("Email Watcher - Generateur de livres automatique")
    _log(f"  Gmail    : {os.getenv('GMAIL_SENDER', 'NON CONFIGURE')}")
    _log(f"  Sujet    : \"{ORDER_SUBJECT}\"")
    _log(f"  Bureau   : {DESKTOP_DIR}")
    if once:
        _log("  Mode     : une seule passe (--once)")
    else:
        _log(f"  Mode     : polling toutes les {POLL_INTERVAL_SECONDS}s")
    _log("=" * 60)

    if once:
        poll_once()
        return

    while True:
        _log("Verification des emails...")
        poll_once()
        _log(f"Prochaine verification dans {POLL_INTERVAL_SECONDS}s...")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
