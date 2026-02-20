"""Interface Streamlit pour le générateur de livres enfants personnalisés."""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

PROJECT_DIR  = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR   = os.path.join(PROJECT_DIR, "output", "images")
TEXT_DIR     = os.path.join(PROJECT_DIR, "output", "text")
FINAL_DIR    = os.path.join(PROJECT_DIR, "output", "final")
AVATARS_DIR  = os.path.join(PROJECT_DIR, "output", "avatars")
PHOTOS_DIR   = os.path.join(PROJECT_DIR, "photos")
CONFIG_PATH  = os.path.join(PROJECT_DIR, "config.json")
STATUS_PATH  = os.path.join(PROJECT_DIR, "output", "status.json")

# ── PAGE CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Générateur de Livres Enfants",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-title{font-size:2.2rem;font-weight:800;text-align:center;
  background:linear-gradient(135deg,#E8725C,#F0A500);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.2rem}
.subtitle{text-align:center;color:#888;margin-bottom:2rem;font-size:1rem}
.section-title{font-size:1.05rem;font-weight:700;color:#E8725C;
  border-bottom:2px solid #f0ebe5;padding-bottom:5px;margin-bottom:1rem}
.card{background:#fafafa;border-radius:12px;padding:1.2rem;
  border:1px solid #f0ebe5;margin-bottom:1rem}
.success-box{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
  padding:1rem;text-align:center}
div[data-testid="stImage"] img{border-radius:8px}
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ──────────────────────────────────────────────────────────────
for k, v in {
    "page": "form",
    "secondary_chars": [],
    "proc_pid": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── HELPERS ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", t)

def save_photo(uploaded_file, name: str) -> str:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    dest = os.path.join(PHOTOS_DIR, f"{slugify(name)}{ext}")
    uploaded_file.seek(0)
    with open(dest, "wb") as f:
        f.write(uploaded_file.read())
    return f"./photos/{slugify(name)}{ext}"

def read_status() -> dict:
    if os.path.exists(STATUS_PATH):
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def count_images() -> int:
    if not os.path.exists(IMAGES_DIR):
        return 0
    return len([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")])

def reset():
    st.session_state["page"] = "form"
    st.session_state["secondary_chars"] = []
    st.session_state["proc_pid"] = None
    for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR, AVATARS_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    if os.path.exists(STATUS_PATH):
        os.remove(STATUS_PATH)

def find_pdf() -> str:
    if os.path.exists(FINAL_DIR):
        pdfs = [f for f in os.listdir(FINAL_DIR) if f.endswith(".pdf")]
        if pdfs:
            return os.path.join(FINAL_DIR, pdfs[0])
    return ""

# ── SCRIPT DE GÉNÉRATION (appelé en subprocess) ───────────────────────────────

RUNNER_SCRIPT = os.path.join(PROJECT_DIR, "_runner.py")

def write_runner():
    """Crée le script runner qui gère la génération et écrit le statut."""
    code = r'''
import json, os, sys, time, shutil, traceback

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv()

STATUS_PATH = os.path.join(PROJECT_DIR, "output", "status.json")
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
IMAGES_DIR  = os.path.join(PROJECT_DIR, "output", "images")
TEXT_DIR    = os.path.join(PROJECT_DIR, "output", "text")
FINAL_DIR   = os.path.join(PROJECT_DIR, "output", "final")

def write_status(phase, message, images_done=0, images_total=16, error="", done=False):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "phase": phase,
            "message": message,
            "images_done": images_done,
            "images_total": images_total,
            "error": error,
            "done": done,
            "ts": time.time(),
        }, f, ensure_ascii=False)

try:
    for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR]:
        os.makedirs(d, exist_ok=True)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    # ── ÉTAPE 1 : ANALYSE PHOTO (Vision GPT-4o) ──────────────────────────────
    from src.image_generator import (
        generate_single_image, _page_to_filename,
        _get_photo_references, _analyze_character_photo,
        _build_character_brief, _load_prompts_log, _save_prompts_log,
        PAUSE_BETWEEN_CALLS, CHARACTER_DESCRIPTIONS_PATH, DESCRIPTIONS_VERSION
    )

    _REFUSAL_PHRASES = [
        "i'm sorry", "i cannot", "i can't", "unable to help",
        "can't help", "not able to", "i apologize", "sorry, but",
    ]
    def _is_valid_desc(text):
        if not text or len(text.strip()) < 25:
            return False
        return not any(p in text.lower() for p in _REFUSAL_PHRASES)

    photo_refs = _get_photo_references(config)
    character_descriptions = {}

    if photo_refs:
        write_status("vision", "Analyse photo de reference (GPT-4o Vision)...")
        child = config.get("child", {})
        child_name = child.get("first_name", "Enfant")

        # Photo actuelle (peut être l'avatar si validation faite depuis l'UI)
        photo_path = os.path.join(PROJECT_DIR, child.get("photo", ""))
        desc = ""
        if os.path.exists(photo_path):
            try:
                raw = _analyze_character_photo(photo_path, child_name, "child")
                if _is_valid_desc(raw):
                    desc = raw
                else:
                    print(f"  [warn] Vision a refuse la photo : {raw[:60]}")
            except Exception as e:
                print(f"  [warn] Vision error : {e}")

        # Fallback générique si Vision a refusé
        if not desc:
            age = child.get("age", 5)
            desc = (
                f"{child_name} has a friendly, expressive face with warm and endearing features, "
                f"typical of a {age}-year-old child."
            )
            print(f"  [warn] Description generique utilisee (Vision indisponible)")

        character_descriptions["child"] = desc
        config["child"]["appearance"] = desc

        # Personnages secondaires
        for char in config.get("secondary_characters", []):
            if char.get("photo"):
                char_path = os.path.join(PROJECT_DIR, char["photo"])
                char_name = char.get("display_name", "personnage")
                char_desc = ""
                if os.path.exists(char_path):
                    try:
                        raw = _analyze_character_photo(char_path, char_name, "secondary")
                        if _is_valid_desc(raw):
                            char_desc = raw
                    except Exception:
                        pass
                if not char_desc:
                    char_desc = f"{char_name} has a friendly, expressive face."
                key = char.get("display_name", "secondary")
                character_descriptions[key] = char_desc
                char["appearance"] = char_desc

        # Sauvegarder dans le cache
        os.makedirs(TEXT_DIR, exist_ok=True)
        with open(CHARACTER_DESCRIPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump({"_version": DESCRIPTIONS_VERSION, **character_descriptions},
                      f, ensure_ascii=False)

    character_brief = _build_character_brief(character_descriptions, config)

    # ── ÉTAPE 2 : TEXTE ──────────────────────────────────────────────────────
    write_status("text", "Generation du texte avec Claude...")
    import anthropic
    from src.text_generator import _build_user_prompt, _extract_json, SYSTEM_PROMPT, OUTPUT_TEXT_DIR

    user_prompt = _build_user_prompt(config)
    client = anthropic.Anthropic()

    # Retry avec backoff exponentiel en cas d'overload Anthropic (erreur 529)
    _text_message = None
    for _text_attempt in range(4):
        try:
            _text_message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except Exception as _e:
            _is_overload = "overloaded" in str(_e).lower() or "529" in str(_e)
            if _is_overload and _text_attempt < 3:
                _wait = 30 * (_text_attempt + 1)
                write_status("text", f"API Claude surchargee, nouvelle tentative dans {_wait}s... ({_text_attempt + 1}/4)")
                time.sleep(_wait)
            else:
                raise
    if _text_message is None:
        raise RuntimeError("Impossible de generer le texte apres 4 tentatives (API surchargee)")

    raw_text = _text_message.content[0].text
    content = _extract_json(raw_text)

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
    write_status("text_done", f"Texte OK : {title}", images_total=total)

    # ── ÉTAPE 3 : IMAGES ─────────────────────────────────────────────────────
    prompts_log = _load_prompts_log()
    write_status("images", "Demarrage des illustrations...", images_done=0, images_total=total)

    for idx, p in enumerate(image_pages):
        page_id  = p["page"]
        filename = _page_to_filename(page_id)
        filepath = os.path.join(IMAGES_DIR, filename)
        original_prompt = p["image_prompt"]
        prompt = character_brief + original_prompt if character_brief else original_prompt

        write_status("images", f"Illustration {idx+1}/{total} - page {page_id}",
                     images_done=idx, images_total=total)

        t0 = time.time()
        ok = generate_single_image(prompt=prompt, output_path=filepath,
                                   reference_images=photo_refs if photo_refs else None)
        elapsed = time.time() - t0

        prompts_log.append({"page": str(page_id), "prompt": prompt,
                             "original_prompt": original_prompt,
                             "success": ok, "duration_s": round(elapsed,1)})
        write_status("images", f"Illustration {idx+1}/{total} OK ({elapsed:.0f}s)",
                     images_done=idx+1, images_total=total)

        if idx < len(image_pages) - 1:
            time.sleep(PAUSE_BETWEEN_CALLS)

    _save_prompts_log(prompts_log)
    write_status("images_done", "Toutes les illustrations generees", images_done=total, images_total=total)

    # ── ÉTAPE 3 : PDF ────────────────────────────────────────────────────────
    write_status("pdf", "Assemblage du PDF...", images_done=total, images_total=total)
    from src.pdf_builder import build_pdf
    build_pdf(CONFIG_PATH)

    # ── ÉTAPE 4 : EMAIL ──────────────────────────────────────────────────────
    notification_email = config.get("notification_email", "").strip()
    if notification_email:
        write_status("email", f"Envoi du livre par email a {notification_email}...",
                     images_done=total, images_total=total)
        import glob as _glob
        from src.email_sender import send_book_email
        pdfs = _glob.glob(os.path.join(FINAL_DIR, "*.pdf"))
        if pdfs:
            child_name = config.get("child", {}).get("first_name", "l'enfant")
            ok, detail = send_book_email(pdfs[0], title, child_name, notification_email)
            done_msg = f"Livre termine ! {detail}" if ok else f"Livre termine ! (email echoue : {detail})"
        else:
            done_msg = "Livre termine ! (PDF introuvable pour envoi email)"
        write_status("done", done_msg, images_done=total, images_total=total, done=True)
    else:
        write_status("done", "Livre termine !", images_done=total, images_total=total, done=True)

except Exception as e:
    write_status("error", str(e), error=traceback.format_exc())
'''
    with open(RUNNER_SCRIPT, "w", encoding="utf-8") as f:
        f.write(code)

# ── HELPERS GÉNÉRATION ────────────────────────────────────────────────────────

def _launch_runner():
    """Lance le subprocess de génération et bascule sur la page 'generating'."""
    write_runner()
    proc = subprocess.Popen(
        [sys.executable, RUNNER_SCRIPT],
        cwd=PROJECT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    st.session_state["proc_pid"] = proc.pid
    st.session_state["page"] = "generating"
    st.rerun()


# ── PAGE VALIDATION AVATARS ────────────────────────────────────────────────────

def page_avatar_validation():
    st.markdown('<p class="main-title">📷 Validation des personnages</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Vérifiez que les avatars aquarelle ressemblent bien aux personnages '
        'avant de lancer la génération des 16 illustrations</p>',
        unsafe_allow_html=True,
    )

    if not os.path.exists(CONFIG_PATH):
        st.error("Config introuvable. Recommencez depuis le formulaire.")
        if st.button("Retour"):
            st.session_state["page"] = "form"
            st.rerun()
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Construire la liste des personnages avec photo
    chars_with_photos = []
    child = config.get("child", {})
    if child.get("photo"):
        chars_with_photos.append({
            "key": "child",
            "name": child.get("first_name", "Enfant"),
            "photo_rel": child["photo"],
            "avatar": os.path.join(AVATARS_DIR, "child_avatar.png"),
        })
    for char in config.get("secondary_characters", []):
        if char.get("photo"):
            chars_with_photos.append({
                "key": char.get("display_name", "secondary"),
                "name": char.get("display_name", "Personnage"),
                "photo_rel": char["photo"],
                "avatar": os.path.join(AVATARS_DIR, f"{slugify(char.get('display_name','secondary'))}_avatar.png"),
            })

    if not chars_with_photos:
        _launch_runner()
        return

    os.makedirs(AVATARS_DIR, exist_ok=True)

    # Générer les avatars manquants
    needs_gen = [c for c in chars_with_photos if not os.path.exists(c["avatar"])]
    if needs_gen:
        names = ", ".join(c["name"] for c in needs_gen)
        with st.spinner(f"Génération de l'avatar aquarelle pour : {names}  (~30 secondes par personnage)"):
            load_dotenv()
            from src.image_generator import _analyze_character_photo, generate_avatar
            for char in needs_gen:
                photo_abs = os.path.join(PROJECT_DIR, char["photo_rel"])
                try:
                    desc = _analyze_character_photo(photo_abs, char["name"], "child")
                    ok = generate_avatar(photo_abs, char["name"], desc, char["avatar"])
                    if not ok:
                        st.error(f"Erreur lors de la génération de l'avatar de {char['name']}. Réessayez.")
                        if st.button("Réessayer"):
                            st.rerun()
                        return
                except Exception as e:
                    st.error(f"Erreur : {e}")
                    return
        st.rerun()

    # Afficher les avatars
    st.markdown("### Aperçu des avatars aquarelle")
    cols = st.columns(max(len(chars_with_photos), 1))
    for i, char in enumerate(chars_with_photos):
        with cols[i]:
            st.image(char["avatar"], caption=f"{char['name']}", use_container_width=True)

    st.markdown("---")
    st.info(
        "Ces avatars seront utilisés comme référence visuelle pour **toutes les illustrations** du livre. "
        "La ressemblance doit être bonne avant de valider."
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Régénérer les avatars", use_container_width=True):
            for char in chars_with_photos:
                if os.path.exists(char["avatar"]):
                    os.remove(char["avatar"])
            st.rerun()
    with col2:
        if st.button("✅ Valider et générer le livre", type="primary", use_container_width=True):
            # Mettre à jour le config pour que les avatars remplacent les photos comme références
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                updated_config = json.load(f)

            for char in chars_with_photos:
                rel = "./" + os.path.relpath(char["avatar"], PROJECT_DIR).replace("\\", "/")
                if char["key"] == "child":
                    updated_config["child"]["photo"] = rel
                else:
                    for sec in updated_config.get("secondary_characters", []):
                        if sec.get("display_name") == char["key"]:
                            sec["photo"] = rel

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(updated_config, f, ensure_ascii=False, indent=2)

            _launch_runner()


# ── PAGE FORMULAIRE ───────────────────────────────────────────────────────────

def page_form():
    st.markdown('<p class="main-title">📖 Générateur de Livre Personnalisé</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Créez un livre illustré unique pour votre enfant</p>', unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown('<p class="section-title">👶 L\'enfant</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            first_name = st.text_input("Prénom *", placeholder="Ex : Liam")
        with c2:
            age = st.number_input("Âge *", min_value=1, max_value=8, value=5)

        gender = st.selectbox("Genre *", ["fille", "garçon", "neutre"])
        outfit = st.text_input("Tenue préférée", placeholder="Laisser vide pour auto")
        photo = st.file_uploader("Photo de l'enfant *", type=["jpg","jpeg","png"],
                                  help="Utilisée comme référence visuelle pour toutes les illustrations")
        if photo:
            st.image(photo, width=110)
            st.caption("Photo uploadée — utilisée comme référence pour les illustrations")

        st.markdown('<p class="section-title" style="margin-top:1.5rem">📚 Le livre</p>', unsafe_allow_html=True)
        theme = st.text_input("Thème *", placeholder="Ex : Le labyrinthe magique")
        educational_value = st.text_input("Valeur éducative *", placeholder="Ex : Le courage, L'amitié")
        c3, c4 = st.columns(2)
        with c3:
            title_suggestion = st.text_input("Titre (optionnel)", placeholder="Auto si vide")
        with c4:
            language = st.selectbox("Langue", ["fr","en","es","de","it"])
        tone = st.text_input("Tonalité (optionnel)", placeholder="Ex : Aventurier, Poétique...")
        dedication = st.text_input("Dédicace (optionnel)", placeholder="Ex : Joyeux anniversaire !")

    with col_right:
        st.markdown('<p class="section-title">👥 Personnages secondaires</p>', unsafe_allow_html=True)

        if st.button("＋ Ajouter un personnage"):
            st.session_state["secondary_chars"].append(
                {"relation":"","display_name":"","appearance":"","_photo":None}
            )

        to_remove = []
        for i, ch in enumerate(st.session_state["secondary_chars"]):
            st.markdown(f"**Personnage {i+1}**")
            ca, cb = st.columns(2)
            with ca:
                ch["relation"]     = st.text_input("Relation",    key=f"r{i}", value=ch["relation"],     placeholder="son chat, sa mamie...")
            with cb:
                ch["display_name"] = st.text_input("Prénom/Nom",  key=f"n{i}", value=ch["display_name"], placeholder="Moustache")
            cp = st.file_uploader("Photo du personnage *", key=f"p{i}", type=["jpg","jpeg","png"])
            if cp:
                st.image(cp, width=80)
                ch["_photo"] = cp
            if st.button("Supprimer", key=f"d{i}"):
                to_remove.append(i)
            st.markdown("---")
        for i in reversed(to_remove):
            st.session_state["secondary_chars"].pop(i)

        st.markdown('<p class="section-title" style="margin-top:1.5rem">⚙️ Options</p>', unsafe_allow_html=True)
        include_q = st.checkbox("Page de questions à la fin", value=True)
        num_q = st.slider("Nombre de questions", 3, 8, 5) if include_q else 5

        st.markdown('<p class="section-title" style="margin-top:1.5rem">📧 Notification email</p>', unsafe_allow_html=True)
        notification_email = st.text_input(
            "Recevoir le livre par email",
            value="monlivreunique.professional@gmail.com",
            placeholder="votre@email.com",
            help="Laissez vide pour désactiver. Requiert GMAIL_APP_PASSWORD dans le fichier .env"
        )
        if notification_email and not os.getenv("GMAIL_APP_PASSWORD", "").strip():
            st.warning("⚠️ GMAIL_APP_PASSWORD manquant dans .env — l'email ne sera pas envoyé")

        if first_name and theme and educational_value:
            st.markdown('<p class="section-title" style="margin-top:1.5rem">📋 Récapitulatif</p>', unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
<b>{first_name}</b>, {age} ans ({gender})<br>
{"Photo uploadee" if photo else "Pas de photo"}<br><br>
<b>{theme}</b><br>{educational_value}
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    bc1, bc2, bc3 = st.columns([1,2,1])
    with bc2:
        can = bool(first_name and theme and educational_value)
        if st.button("🚀 Générer le livre", disabled=not can, type="primary", use_container_width=True):
            # Sauvegarder photos
            photo_rel = ""
            if photo and first_name:
                photo_rel = save_photo(photo, first_name)

            # Apparence auto selon la photo
            if photo_rel:
                appearance_note = "Apparence fidele a la photo de reference fournie. Reproduis exactement les traits du visage, la couleur et la coiffure des cheveux, le teint de la peau."
            else:
                appearance_note = "Enfant au visage expressif et sympathique, adapte au style aquarelle jeunesse."

            secondary = []
            for ch in st.session_state["secondary_chars"]:
                if ch.get("relation"):
                    char_photo = ch.get("_photo")
                    char_photo_rel = ""
                    if char_photo and ch.get("display_name"):
                        char_photo_rel = save_photo(char_photo, ch["display_name"])
                    if char_photo_rel:
                        char_appearance = "Apparence fidele a la photo de reference fournie."
                    else:
                        char_appearance = ch.get("appearance", "")
                    c = {"relation": ch["relation"], "display_name": ch.get("display_name",""), "appearance": char_appearance}
                    if char_photo_rel:
                        c["photo"] = char_photo_rel
                    secondary.append(c)

            config = {
                "book": {"title_suggestion": title_suggestion, "language": language,
                         "theme": theme, "educational_value": educational_value,
                         "tone": tone, "dedication": dedication},
                "child": {"first_name": first_name, "age": int(age), "gender": gender,
                          "appearance": appearance_note, "default_outfit": outfit},
                "secondary_characters": secondary,
                "options": {"include_questions_page": include_q, "number_of_questions": num_q},
                "notification_email": notification_email.strip(),
            }
            if photo_rel:
                config["child"]["photo"] = photo_rel

            # Nettoyer outputs (avatars inclus — seront régénérés à la validation)
            for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR, AVATARS_DIR]:
                if os.path.exists(d): shutil.rmtree(d)
                os.makedirs(d, exist_ok=True)
            if os.path.exists(STATUS_PATH):
                os.remove(STATUS_PATH)

            # Sauvegarder config
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            # Si des photos sont fournies → étape validation avatar
            # Sinon → lancer directement la génération
            has_photos = bool(photo_rel or any(c.get("_photo") for c in st.session_state["secondary_chars"]))
            if has_photos:
                st.session_state["page"] = "avatar_validation"
                st.rerun()
            else:
                _launch_runner()

        if not can:
            st.caption("Remplissez les champs obligatoires (*)")


# ── PAGE GÉNÉRATION ───────────────────────────────────────────────────────────

def page_generating():
    st.markdown('<p class="main-title">📖 Génération en cours...</p>', unsafe_allow_html=True)

    status = read_status()
    phase      = status.get("phase", "")
    message    = status.get("message", "Démarrage...")
    img_done   = status.get("images_done", 0)
    img_total  = status.get("images_total", 16)
    is_done    = status.get("done", False)
    error      = status.get("error", "")

    # Redirection si terminé
    if is_done:
        st.session_state["page"] = "done"
        st.rerun()
    if phase == "error":
        st.session_state["page"] = "error"
        st.rerun()

    # Progression globale
    if phase in ("", "vision"):
        pct = 0.04
    elif phase == "text":
        pct = 0.08
    elif phase == "text_done":
        pct = 0.14
    elif phase == "images":
        pct = 0.14 + (img_done / max(img_total, 1)) * 0.73
    elif phase == "images_done":
        pct = 0.87
    elif phase == "pdf":
        pct = 0.92
    else:
        pct = 0.0

    st.progress(pct, text=message)

    # Étapes visuelles
    steps = {
        "text":        ("📝", "Texte",        phase in ("text",)),
        "text_done":   ("📝", "Texte",        phase in ("text_done", "images", "images_done", "pdf", "done")),
        "images":      ("🎨", "Illustrations", phase in ("images", "images_done")),
        "pdf":         ("📄", "PDF",           phase in ("pdf",)),
    }

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    for col, (icon, label, active) in zip([col_s1, col_s2, col_s3, col_s4], [
        ("📷", "1. Photo",        phase in ("vision","text","text_done","images","images_done","pdf","done")),
        ("📝", "2. Texte",        phase in ("text","text_done","images","images_done","pdf","done")),
        ("🎨", "3. Illustrations", phase in ("images","images_done","pdf","done")),
        ("📄", "4. PDF",          phase in ("pdf","done")),
    ]):
        color = "#E8725C" if active else "#ccc"
        col.markdown(f"<div style='text-align:center;font-size:1.8rem'>{icon}</div>"
                     f"<div style='text-align:center;color:{color};font-weight:600'>{label}</div>",
                     unsafe_allow_html=True)

    st.markdown("---")

    # Compteur images
    if phase in ("images", "images_done"):
        st.markdown(f"### 🎨 Illustrations : {img_done} / {img_total}")
        imgs = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")]) if os.path.exists(IMAGES_DIR) else []
        if imgs:
            cols = st.columns(4)
            for i, fname in enumerate(imgs):
                with cols[i % 4]:
                    try:
                        img = Image.open(os.path.join(IMAGES_DIR, fname))
                        lbl = fname.replace(".png","").replace("_"," ").title()
                        st.image(img, caption=lbl, use_container_width=True)
                    except Exception:
                        pass

    # Auto-refresh toutes les 4 secondes
    time.sleep(4)
    st.rerun()


# ── PAGE RÉSULTAT ─────────────────────────────────────────────────────────────

def page_done():
    st.markdown('<p class="main-title">🎉 Livre terminé !</p>', unsafe_allow_html=True)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    title = "Votre livre"
    if os.path.exists(content_path):
        with open(content_path, "r", encoding="utf-8") as f:
            title = json.load(f).get("title", title)

    # Lire le message final du status (contient info email)
    status = read_status()
    status_msg = status.get("message", "")
    email_info = ""
    if "email" in status_msg.lower() or "envoye" in status_msg.lower():
        if "echoue" in status_msg.lower():
            email_info = f'<p style="color:#dc2626;font-size:0.9rem">⚠️ Email : {status_msg}</p>'
        else:
            # Extraire la partie email du message
            parts = status_msg.split("!")
            if len(parts) > 1:
                email_detail = "!".join(parts[1:]).strip()
                email_info = f'<p style="color:#16a34a;font-size:0.9rem">📧 {email_detail}</p>'

    st.markdown(f"""<div class="success-box">
<h2 style="color:#16a34a">✅ "{title}"</h2>
<p style="color:#555">16 illustrations aquarelle générées • Prêt à imprimer</p>
{email_info}
</div>""", unsafe_allow_html=True)

    pdf_path = find_pdf()
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        size_mb = len(pdf_bytes) / 1024 / 1024
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            st.download_button(
                label=f"📥 Télécharger le PDF ({size_mb:.0f} Mo)",
                data=pdf_bytes,
                file_name=os.path.basename(pdf_path),
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

    st.markdown("### 🖼 Galerie")
    if os.path.exists(IMAGES_DIR):
        imgs = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")])
        cols = st.columns(4)
        for i, fname in enumerate(imgs):
            with cols[i % 4]:
                try:
                    img = Image.open(os.path.join(IMAGES_DIR, fname))
                    st.image(img, caption=fname.replace(".png","").replace("_"," ").title(), use_container_width=True)
                except Exception:
                    pass

    st.markdown("---")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        if st.button("📖 Créer un nouveau livre", use_container_width=True):
            reset()
            st.rerun()


# ── PAGE ERREUR ───────────────────────────────────────────────────────────────

def page_error():
    status = read_status()
    st.error("Une erreur est survenue pendant la génération")
    st.markdown(f"**Message :** {status.get('message','')}")
    with st.expander("Détails techniques"):
        st.code(status.get("error","Aucun détail disponible"))

    col1, col2 = st.columns(2)
    with col1:
        # Relance sans tout effacer — conserve avatars + config validé
        can_relaunch = os.path.exists(CONFIG_PATH)
        if st.button("🔁 Relancer la génération", disabled=not can_relaunch, use_container_width=True,
                     help="Relance depuis le début sans supprimer les avatars déjà validés"):
            if os.path.exists(STATUS_PATH):
                os.remove(STATUS_PATH)
            for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR]:
                if os.path.exists(d): shutil.rmtree(d)
                os.makedirs(d, exist_ok=True)
            _launch_runner()
    with col2:
        if st.button("🗑️ Tout recommencer", use_container_width=True,
                     help="Repart de zéro (efface tout, y compris les avatars)"):
            reset()
            st.rerun()


# ── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    ak = os.getenv("ANTHROPIC_API_KEY","")
    ok = os.getenv("OPENAI_API_KEY","")
    gm = os.getenv("GMAIL_APP_PASSWORD","").strip()
    st.success("✅ Claude API connectée") if ak else st.error("❌ Clé Anthropic manquante")
    st.success("✅ OpenAI API connectée") if ok else st.error("❌ Clé OpenAI manquante")
    st.success("✅ Gmail configuré") if gm else st.warning("⚠️ Gmail non configuré (email désactivé)")
    st.markdown("---")
    st.markdown("""### ℹ️ À propos
Génère automatiquement :
- **Texte** adapté à l'âge (Claude)
- **16 illustrations** aquarelle (gpt-image-1)
- **PDF** 21×21cm prêt à imprimer

*Durée estimée : ~15 minutes*""")
    if st.session_state["page"] in ("done","error"):
        st.markdown("---")
        if st.button("🔄 Nouveau livre", use_container_width=True):
            reset()
            st.rerun()


# ── ROUTEUR ───────────────────────────────────────────────────────────────────

p = st.session_state["page"]
if p == "form":
    page_form()
elif p == "avatar_validation":
    page_avatar_validation()
elif p == "generating":
    page_generating()
elif p == "done":
    page_done()
elif p == "error":
    page_error()
