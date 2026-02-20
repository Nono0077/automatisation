"""Assemblage du PDF final avec reportlab."""

import json
import os
import re
import unicodedata

from PIL import Image as PILImage
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
TEXT_DIR = os.path.join(OUTPUT_DIR, "text")
FINAL_DIR = os.path.join(OUTPUT_DIR, "final")
FONTS_DIR = os.path.join(PROJECT_DIR, "fonts")

PAGE_SIZE = 21 * cm  # 21cm x 21cm
MARGIN = 20 * mm
TEXT_COLOR = HexColor("#2D2D2D")

# Polices par âge
FONT_CONFIG = {
    (1, 2): {"font": "Quicksand-Bold", "size": 30, "fallback_size": 30},
    (3, 3): {"font": "Quicksand-Medium", "size": 26, "fallback_size": 26},
    (4, 5): {"font": "Quicksand-Regular", "size": 22, "fallback_size": 22},
    (6, 8): {"font": "Quicksand-Regular", "size": 18, "fallback_size": 18},
}


def _slugify(text: str) -> str:
    """Convertit un texte en slug pour le nom de fichier."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", text)


def _register_fonts():
    """Enregistre les polices Quicksand si disponibles."""
    font_map = {
        "Quicksand-Regular": "Quicksand-Regular.ttf",
        "Quicksand-Medium": "Quicksand-Medium.ttf",
        "Quicksand-Bold": "Quicksand-Bold.ttf",
        "Quicksand-Light": "Quicksand-Light.ttf",
    }

    registered = {}
    for font_name, filename in font_map.items():
        path = os.path.join(FONTS_DIR, filename)
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                registered[font_name] = True
            except Exception as e:
                print(f"  [warn] Impossible de charger {filename}: {e}")
                registered[font_name] = False
        else:
            registered[font_name] = False

    return registered


def _get_font_for_age(age: int, registered: dict) -> tuple[str, int]:
    """Retourne la police et la taille pour un âge donné."""
    for (min_age, max_age), cfg in FONT_CONFIG.items():
        if min_age <= age <= max_age:
            font_name = cfg["font"]
            size = cfg["size"]
            if registered.get(font_name):
                return font_name, size
            return "Helvetica", cfg["fallback_size"]

    return "Helvetica", 20


def _get_page_data(content: dict, page_id) -> dict | None:
    """Récupère les données d'une page par son identifiant."""
    for p in content["pages"]:
        if str(p["page"]) == str(page_id):
            return p
    return None


def _draw_image_page(c: canvas.Canvas, image_path: str):
    """Dessine une image pleine page."""
    if os.path.exists(image_path):
        c.drawImage(
            image_path,
            0, 0,
            width=PAGE_SIZE,
            height=PAGE_SIZE,
            preserveAspectRatio=True,
            anchor="c",
        )
    else:
        # Page vide avec message
        c.setFont("Helvetica", 14)
        c.setFillColor(HexColor("#999999"))
        c.drawCentredString(
            PAGE_SIZE / 2, PAGE_SIZE / 2, f"[Image manquante : {os.path.basename(image_path)}]"
        )


def _draw_text_page(
    c: canvas.Canvas,
    text: str,
    font_name: str,
    font_size: int,
    bg_color: str = "#FFF8F0",
):
    """Dessine une page de texte avec fond coloré."""
    # Fond
    c.setFillColor(HexColor(bg_color))
    c.rect(0, 0, PAGE_SIZE, PAGE_SIZE, fill=1, stroke=0)

    # Texte
    c.setFillColor(TEXT_COLOR)
    c.setFont(font_name, font_size)

    line_height = font_size * 1.5
    usable_width = PAGE_SIZE - 2 * MARGIN

    # Découper le texte en lignes
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        text_width = pdfmetrics.stringWidth(test_line, font_name, font_size)
        if text_width <= usable_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    # Centrer verticalement
    total_height = len(lines) * line_height
    start_y = (PAGE_SIZE + total_height) / 2 - font_size

    for i, line in enumerate(lines):
        y = start_y - i * line_height
        c.drawCentredString(PAGE_SIZE / 2, y, line)


def _draw_dedication_page(
    c: canvas.Canvas,
    dedication: str,
    font_name: str,
    font_size: int,
    bg_color: str = "#FFF8F0",
):
    """Dessine la page de dédicace."""
    # Fond
    c.setFillColor(HexColor(bg_color))
    c.rect(0, 0, PAGE_SIZE, PAGE_SIZE, fill=1, stroke=0)

    if not dedication:
        c.showPage()
        return

    # Texte en italique (plus petit)
    ital_font = font_name
    if "Quicksand" in font_name:
        try:
            pdfmetrics.getFont("Quicksand-Light")
            ital_font = "Quicksand-Light"
        except KeyError:
            pass
    else:
        ital_font = "Helvetica-Oblique"

    ded_size = max(font_size - 4, 14)
    c.setFillColor(HexColor("#555555"))

    try:
        c.setFont(ital_font, ded_size)
    except Exception:
        c.setFont("Helvetica-Oblique", ded_size)

    line_height = ded_size * 1.6
    usable_width = PAGE_SIZE - 2 * MARGIN

    # Découper en lignes
    lines = []
    for paragraph in dedication.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            try:
                w = pdfmetrics.stringWidth(test, ital_font, ded_size)
            except Exception:
                w = pdfmetrics.stringWidth(test, "Helvetica-Oblique", ded_size)
            if w <= usable_width:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

    total_height = len(lines) * line_height
    start_y = (PAGE_SIZE + total_height) / 2 - ded_size

    for i, line in enumerate(lines):
        y = start_y - i * line_height
        c.drawCentredString(PAGE_SIZE / 2, y, line)


def _draw_questions_page(
    c: canvas.Canvas,
    questions: list[str],
    font_name: str,
    font_size: int,
    bg_color: str = "#FFF8F0",
):
    """Dessine la page de questions."""
    c.setFillColor(HexColor(bg_color))
    c.rect(0, 0, PAGE_SIZE, PAGE_SIZE, fill=1, stroke=0)

    # Titre
    title_size = font_size + 6
    c.setFillColor(HexColor("#E8725C"))
    c.setFont(font_name, title_size)
    c.drawCentredString(PAGE_SIZE / 2, PAGE_SIZE - 3 * cm, "Parlons ensemble !")

    # Questions
    c.setFillColor(TEXT_COLOR)
    q_size = max(font_size - 2, 14)
    c.setFont(font_name, q_size)

    start_y = PAGE_SIZE - 5 * cm
    spacing = 2.2 * cm

    for i, question in enumerate(questions):
        y = start_y - i * spacing
        # Numéro avec étoile
        c.drawString(MARGIN + 5 * mm, y, f"  {i + 1}. {question}")


def _draw_back_cover(
    c: canvas.Canvas,
    image_path: str,
    back_text: str,
    font_name: str,
    font_size: int,
):
    """Dessine la couverture arrière."""
    # Image de fond
    _draw_image_page(c, image_path)

    if not back_text:
        return

    # Texte superposé en bas
    text_size = max(font_size - 2, 13)

    # Semi-transparent overlay en bas
    c.setFillColor(HexColor("#00000033"))
    c.rect(0, 0, PAGE_SIZE, 6 * cm, fill=1, stroke=0)

    c.setFillColor(HexColor("#FFFFFF"))
    try:
        c.setFont(font_name, text_size)
    except Exception:
        c.setFont("Helvetica", text_size)

    line_height = text_size * 1.4
    usable_width = PAGE_SIZE - 2 * MARGIN

    # Découper en lignes
    lines = []
    for paragraph in back_text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            try:
                w = pdfmetrics.stringWidth(test, font_name, text_size)
            except Exception:
                w = pdfmetrics.stringWidth(test, "Helvetica", text_size)
            if w <= usable_width:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

    total_height = len(lines) * line_height
    start_y = 5 * cm - (5 * cm - total_height) / 2

    for i, line in enumerate(lines):
        y = start_y - i * line_height
        c.drawCentredString(PAGE_SIZE / 2, y, line)


def build_pdf(config_path: str):
    """Assemble le PDF final."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  ❌ book_content.json introuvable. Lancez --step text d'abord.")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    os.makedirs(FINAL_DIR, exist_ok=True)

    # Nom du fichier
    prenom = config["child"]["first_name"]
    theme_slug = _slugify(config["book"]["theme"])
    pdf_filename = f"livre_{_slugify(prenom)}_{theme_slug}.pdf"
    pdf_path = os.path.join(FINAL_DIR, pdf_filename)

    # Polices
    registered = _register_fonts()
    age = config["child"]["age"]
    font_name, font_size = _get_font_for_age(age, registered)
    print(f"  [police] {font_name} {font_size}pt (age {age} ans)")

    # Couleur de fond
    palette = content.get("color_palette", {})
    bg_color = palette.get("text_page_background", "#FFF8F0")
    # Extraire juste le hex si format "#hex — description"
    if " " in bg_color:
        bg_color = bg_color.split(" ")[0].split("—")[0].strip()
    if not bg_color.startswith("#"):
        bg_color = "#FFF8F0"

    # Créer le PDF
    c = canvas.Canvas(pdf_path, pagesize=(PAGE_SIZE, PAGE_SIZE))
    c.setTitle(content.get("title", "Mon Livre"))
    c.setAuthor(f"Livre personnalisé pour {prenom}")

    dedication = config["book"].get("dedication", "")
    include_questions = config.get("options", {}).get("include_questions_page", True)

    # === COUVERTURE AVANT ===
    print("  📄 Couverture avant...")
    cover_front_path = os.path.join(IMAGES_DIR, "cover_front.png")
    _draw_image_page(c, cover_front_path)
    c.showPage()

    # === PAGE 2 : DÉDICACE ===
    print("  📄 Page 2 (dédicace)...")
    _draw_dedication_page(c, dedication, font_name, font_size, bg_color)
    c.showPage()

    # === PAGES 3-29 : alternance image/texte ===
    for page_num in range(3, 30):
        page_data = _get_page_data(content, page_num)
        if not page_data:
            continue

        if page_data["type"] == "image":
            img_path = os.path.join(IMAGES_DIR, f"page_{page_num:02d}.png")
            print(f"  [page] {page_num} (illustration)...")
            _draw_image_page(c, img_path)

        elif page_data["type"] == "text":
            print(f"  [page] {page_num} (texte)...")
            _draw_text_page(c, page_data.get("text", ""), font_name, font_size, bg_color)

        c.showPage()

    # === PAGES QUESTIONS ===
    if include_questions:
        q_data = _get_page_data(content, 30)
        if q_data and q_data.get("questions"):
            print("  📄 Page questions...")
            _draw_questions_page(c, q_data["questions"], font_name, font_size, bg_color)
            c.showPage()

    # === COUVERTURE ARRIÈRE ===
    print("  📄 Couverture arrière...")
    cover_back_path = os.path.join(IMAGES_DIR, "cover_back.png")
    back_data = _get_page_data(content, "cover_back")
    back_text = back_data.get("back_cover_text", "") if back_data else ""
    _draw_back_cover(c, cover_back_path, back_text, font_name, font_size)
    c.showPage()

    # Sauvegarder
    c.save()
    print(f"\n  [ok] PDF genere : {pdf_path}")
    print(f"  [ok] Format : 21cm x 21cm")
