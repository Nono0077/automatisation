"""Génération d'une prévisualisation HTML du livre."""

import json
import os
import webbrowser


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
TEXT_DIR = os.path.join(OUTPUT_DIR, "text")


def generate_preview(config_path: str):
    """Génère un fichier HTML de prévisualisation et l'ouvre dans le navigateur."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    content_path = os.path.join(TEXT_DIR, "book_content.json")
    if not os.path.exists(content_path):
        print("  ❌ book_content.json introuvable. Lancez --step text d'abord.")
        return

    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    title = content.get("title", "Mon Livre")
    dedication = config["book"].get("dedication", "")
    palette = content.get("color_palette", {})
    bg_color = palette.get("text_page_background", "#FFF8F0")
    if " " in bg_color:
        bg_color = bg_color.split(" ")[0].split("—")[0].strip()

    # Chemin relatif vers les images
    images_rel = "../images"

    html_parts = [f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>{title} — Prévisualisation</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Quicksand', 'Segoe UI', sans-serif; background: #f0f0f0; padding: 20px; }}
  h1 {{ text-align: center; margin: 20px 0 30px; color: #333; }}
  .spread {{
    display: flex; justify-content: center; gap: 4px;
    margin: 10px auto; max-width: 1100px;
  }}
  .page {{
    width: 500px; height: 500px;
    border: 1px solid #ddd; border-radius: 4px;
    overflow: hidden; position: relative;
    background: white;
  }}
  .page img {{
    width: 100%; height: 100%; object-fit: cover;
  }}
  .page.text-page {{
    display: flex; align-items: center; justify-content: center;
    padding: 40px; text-align: center;
    background: {bg_color}; color: #2D2D2D;
    font-size: 18px; line-height: 1.6;
  }}
  .page.dedication {{
    font-style: italic; color: #555;
    background: {bg_color};
    display: flex; align-items: center; justify-content: center;
    padding: 40px; text-align: center; font-size: 16px;
  }}
  .page.questions {{
    background: {bg_color}; padding: 30px;
    display: flex; flex-direction: column; justify-content: center;
  }}
  .page.questions h2 {{ color: #E8725C; text-align: center; margin-bottom: 20px; }}
  .page.questions ol {{ padding-left: 20px; }}
  .page.questions li {{ margin: 12px 0; font-size: 16px; color: #2D2D2D; }}
  .label {{
    position: absolute; top: 5px; left: 5px;
    background: rgba(0,0,0,0.6); color: white;
    padding: 2px 8px; border-radius: 3px; font-size: 11px;
  }}
  .single {{ justify-content: center; }}
  .single .page {{ margin: 0 auto; }}
  hr {{ margin: 20px auto; max-width: 600px; border: none; border-top: 2px dashed #ccc; }}
</style>
</head>
<body>
<h1>📖 {title}</h1>
"""]

    # Couverture avant
    html_parts.append(f"""
<div class="spread single">
  <div class="page">
    <img src="{images_rel}/cover_front.png" alt="Couverture avant">
    <span class="label">Couverture</span>
  </div>
</div>
<hr>
""")

    # Dédicace
    if dedication:
        html_parts.append(f"""
<div class="spread single">
  <div class="page dedication">
    <p>{dedication}</p>
    <span class="label">Page 2 — Dédicace</span>
  </div>
</div>
<hr>
""")

    # Pages 3-29 en double pages
    page_num = 3
    while page_num <= 29:
        left_data = None
        right_data = None

        for p in content["pages"]:
            if str(p["page"]) == str(page_num):
                left_data = p
            if str(p["page"]) == str(page_num + 1):
                right_data = p

        left_html = ""
        right_html = ""

        if left_data:
            if left_data["type"] == "image":
                img_file = f"page_{page_num:02d}.png"
                left_html = f"""<div class="page">
    <img src="{images_rel}/{img_file}" alt="Page {page_num}">
    <span class="label">Page {page_num}</span>
  </div>"""
            elif left_data["type"] == "text":
                text = left_data.get("text", "")
                left_html = f"""<div class="page text-page">
    <p>{text}</p>
    <span class="label">Page {page_num}</span>
  </div>"""

        if right_data:
            if right_data["type"] == "image":
                img_file = f"page_{page_num + 1:02d}.png"
                right_html = f"""<div class="page">
    <img src="{images_rel}/{img_file}" alt="Page {page_num + 1}">
    <span class="label">Page {page_num + 1}</span>
  </div>"""
            elif right_data["type"] == "text":
                text = right_data.get("text", "")
                right_html = f"""<div class="page text-page">
    <p>{text}</p>
    <span class="label">Page {page_num + 1}</span>
  </div>"""

        if left_html or right_html:
            html_parts.append(f"""
<div class="spread">
  {left_html}
  {right_html}
</div>
<hr>
""")

        page_num += 2

    # Questions
    q_data = None
    for p in content["pages"]:
        if str(p["page"]) == "30" and p.get("type") == "questions":
            q_data = p

    if q_data and q_data.get("questions"):
        questions_html = "\n".join(f"    <li>{q}</li>" for q in q_data["questions"])
        html_parts.append(f"""
<div class="spread single">
  <div class="page questions">
    <h2>Parlons ensemble !</h2>
    <ol>
{questions_html}
    </ol>
    <span class="label">Page 30</span>
  </div>
</div>
<hr>
""")

    # Couverture arrière
    back_data = None
    for p in content["pages"]:
        if str(p["page"]) == "cover_back":
            back_data = p

    back_text = back_data.get("back_cover_text", "") if back_data else ""
    html_parts.append(f"""
<div class="spread single">
  <div class="page" style="position: relative;">
    <img src="{images_rel}/cover_back.png" alt="Couverture arrière">
    <div style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.4); color: white; padding: 20px; text-align: center; font-size: 14px;">
      {back_text}
    </div>
    <span class="label">Couverture arrière</span>
  </div>
</div>
""")

    html_parts.append("</body></html>")

    # Sauvegarder
    preview_path = os.path.join(OUTPUT_DIR, "preview.html")
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"  ✅ Prévisualisation générée : {preview_path}")

    # Ouvrir dans le navigateur
    webbrowser.open(f"file://{os.path.abspath(preview_path)}")
    print("  🌐 Ouvert dans le navigateur")
