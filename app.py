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

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR   = os.path.join(PROJECT_DIR, "output", "images")
TEXT_DIR     = os.path.join(PROJECT_DIR, "output", "text")
FINAL_DIR    = os.path.join(PROJECT_DIR, "output", "final")
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
    for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR]:
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

    # ── ÉTAPE 1 : TEXTE ──────────────────────────────────────────────────────
    write_status("text", "Generation du texte avec Claude...")
    import anthropic
    from src.text_generator import _build_user_prompt, _extract_json, SYSTEM_PROMPT, OUTPUT_TEXT_DIR

    user_prompt = _build_user_prompt(config)
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = message.content[0].text
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

    # ── ÉTAPE 2 : IMAGES ─────────────────────────────────────────────────────
    from src.image_generator import (
        generate_single_image, _get_reference_images, _page_to_filename,
        _load_prompts_log, _save_prompts_log, PAUSE_BETWEEN_CALLS
    )
    cover_front_path = os.path.join(IMAGES_DIR, "cover_front.png")
    prompts_log = _load_prompts_log()

    for idx, p in enumerate(image_pages):
        page_id  = p["page"]
        filename = _page_to_filename(page_id)
        filepath = os.path.join(IMAGES_DIR, filename)
        prompt   = p["image_prompt"]
        refs     = _get_reference_images(config, page_id, cover_front_path)

        write_status("images", f"Illustration {idx+1}/{total} - page {page_id}",
                     images_done=idx, images_total=total)

        t0 = time.time()
        ok = generate_single_image(prompt=prompt, output_path=filepath, reference_images=refs)
        elapsed = time.time() - t0

        prompts_log.append({"page": str(page_id), "prompt": prompt,
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

    write_status("done", "Livre termine !", images_done=total, images_total=total, done=True)

except Exception as e:
    write_status("error", str(e), error=traceback.format_exc())
'''
    with open(RUNNER_SCRIPT, "w", encoding="utf-8") as f:
        f.write(code)

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
        appearance = st.text_area(
            "Description physique *",
            placeholder="Ex : Peau brun clair, cheveux noirs bouclés courts, yeux marron, grand sourire...",
            height=90,
        )
        outfit = st.text_input("Tenue préférée", placeholder="Laisser vide pour auto")
        photo = st.file_uploader("Photo de l'enfant (optionnel)", type=["jpg","jpeg","png"])
        if photo:
            st.image(photo, width=110)

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
            ch["appearance"]       = st.text_area( "Description", key=f"a{i}", value=ch["appearance"],   height=68, placeholder="Apparence physique...")
            cp = st.file_uploader("Photo (optionnel)", key=f"p{i}", type=["jpg","jpeg","png"])
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

        if first_name and theme and educational_value and appearance:
            st.markdown('<p class="section-title" style="margin-top:1.5rem">📋 Récapitulatif</p>', unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
<b>{first_name}</b>, {age} ans ({gender})<br>
<i>{appearance[:80]}{"..." if len(appearance)>80 else ""}</i><br><br>
📖 <b>{theme}</b><br>💡 {educational_value}
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    bc1, bc2, bc3 = st.columns([1,2,1])
    with bc2:
        can = bool(first_name and theme and educational_value and appearance)
        if st.button("🚀 Générer le livre", disabled=not can, type="primary", use_container_width=True):
            # Sauvegarder photos
            photo_rel = ""
            if photo and first_name:
                photo_rel = save_photo(photo, first_name)

            secondary = []
            for ch in st.session_state["secondary_chars"]:
                if ch.get("relation"):
                    c = {"relation": ch["relation"], "display_name": ch.get("display_name",""), "appearance": ch.get("appearance","")}
                    if ch.get("_photo") and ch.get("display_name"):
                        c["photo"] = save_photo(ch["_photo"], ch["display_name"])
                    secondary.append(c)

            config = {
                "book": {"title_suggestion": title_suggestion, "language": language,
                         "theme": theme, "educational_value": educational_value,
                         "tone": tone, "dedication": dedication},
                "child": {"first_name": first_name, "age": int(age), "gender": gender,
                          "appearance": appearance, "default_outfit": outfit},
                "secondary_characters": secondary,
                "options": {"include_questions_page": include_q, "number_of_questions": num_q},
            }
            if photo_rel:
                config["child"]["photo"] = photo_rel

            # Nettoyer outputs
            for d in [IMAGES_DIR, TEXT_DIR, FINAL_DIR]:
                if os.path.exists(d): shutil.rmtree(d)
                os.makedirs(d, exist_ok=True)
            if os.path.exists(STATUS_PATH):
                os.remove(STATUS_PATH)

            # Sauvegarder config
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            # Créer et lancer le runner
            write_runner()
            proc = subprocess.Popen(
                [sys.executable, RUNNER_SCRIPT],
                cwd=PROJECT_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            st.session_state["proc_pid"] = proc.pid
            st.session_state["page"] = "generating"
            st.rerun()

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
    if phase in ("", "text"):
        pct = 0.05
    elif phase == "text_done":
        pct = 0.12
    elif phase == "images":
        pct = 0.12 + (img_done / max(img_total, 1)) * 0.75
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

    col_s1, col_s2, col_s3 = st.columns(3)
    for col, (icon, label, active) in zip([col_s1, col_s2, col_s3], [
        ("📝", "1. Texte",        phase in ("text","text_done","images","images_done","pdf","done")),
        ("🎨", "2. Illustrations", phase in ("images","images_done","pdf","done")),
        ("📄", "3. PDF",          phase in ("pdf","done")),
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

    st.markdown(f"""<div class="success-box">
<h2 style="color:#16a34a">✅ "{title}"</h2>
<p style="color:#555">16 illustrations aquarelle générées • Prêt à imprimer</p>
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
    if st.button("🔄 Recommencer"):
        reset()
        st.rerun()


# ── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    ak = os.getenv("ANTHROPIC_API_KEY","")
    ok = os.getenv("OPENAI_API_KEY","")
    st.success("✅ Claude API connectée") if ak else st.error("❌ Clé Anthropic manquante")
    st.success("✅ OpenAI API connectée") if ok else st.error("❌ Clé OpenAI manquante")
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
elif p == "generating":
    page_generating()
elif p == "done":
    page_done()
elif p == "error":
    page_error()
