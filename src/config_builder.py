"""Formulaire CLI interactif pour construire la configuration du livre."""

import json
import os
import shutil
import unicodedata


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")


def _input(prompt: str, default: str = "") -> str:
    """Input avec valeur par défaut."""
    if default:
        val = input(f"{prompt} [{default}] : ").strip()
        return val if val else default
    return input(f"{prompt} : ").strip()


def _input_required(prompt: str) -> str:
    """Input obligatoire."""
    while True:
        val = input(f"{prompt} : ").strip()
        if val:
            return val
        print("  ⚠️  Ce champ est obligatoire.")


def _input_int(prompt: str, min_val: int, max_val: int) -> int:
    """Input entier avec validation de plage."""
    while True:
        val = input(f"{prompt} ({min_val}-{max_val}) : ").strip()
        try:
            n = int(val)
            if min_val <= n <= max_val:
                return n
            print(f"  ⚠️  Entrez un nombre entre {min_val} et {max_val}.")
        except ValueError:
            print(f"  ⚠️  Entrez un nombre valide.")


def _input_choice(prompt: str, choices: list[str]) -> str:
    """Input avec choix restreint."""
    choices_str = "/".join(choices)
    while True:
        val = input(f"{prompt} ({choices_str}) : ").strip().lower()
        if val in choices:
            return val
        print(f"  ⚠️  Choisissez parmi : {choices_str}")


def _input_photo(prompt: str) -> str:
    """Input chemin photo avec validation."""
    while True:
        val = input(f"{prompt} (ou Entrée pour passer) : ").strip()
        if not val:
            return ""
        val = val.strip('"').strip("'")
        if os.path.isfile(val):
            ext = os.path.splitext(val)[1].lower()
            if ext in (".jpg", ".jpeg", ".png"):
                return val
            print(f"  ⚠️  Format non supporté ({ext}). Utilisez jpg, jpeg ou png.")
        else:
            print(f"  ⚠️  Fichier introuvable : {val}")


def _copy_photo(src_path: str, name: str) -> str:
    """Copie une photo dans le dossier photos/ du projet."""
    if not src_path:
        return ""
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    ext = os.path.splitext(src_path)[1].lower()
    slug = _slugify(name)
    dest = os.path.join(PHOTOS_DIR, f"{slug}{ext}")
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)
    return f"./photos/{slug}{ext}"


def _slugify(text: str) -> str:
    """Convertit un texte en slug."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace(" ", "_")
    return "".join(c for c in text if c.isalnum() or c == "_")


def _confirm(prompt: str) -> bool:
    """Confirmation oui/non."""
    val = input(f"{prompt} (o/n) : ").strip().lower()
    return val in ("o", "oui", "y", "yes")


def build_config_interactive() -> str:
    """Lance le formulaire interactif et retourne le chemin du config.json."""

    print("\n" + "═" * 45)
    print("  📖 Générateur de Livre Personnalisé")
    print("═" * 45)

    # --- ENFANT ---
    print("\n👶 INFORMATIONS SUR L'ENFANT")
    print("─" * 35)

    first_name = _input_required("Prénom de l'enfant")
    age = _input_int("Âge", 1, 8)
    gender = _input_choice("Genre", ["fille", "garçon", "neutre"])
    photo_path = _input_photo("Chemin vers la photo de l'enfant")

    if photo_path:
        print("  📷 La photo sera utilisée comme référence visuelle.")
        appearance = _input_required(
            "  Ajoute une description pour compléter (couleur des yeux, coiffure, etc.)"
        )
    else:
        appearance = _input_required("Description physique de l'enfant")

    default_outfit = _input(
        "Tenue par défaut (ou Entrée pour laisser Claude choisir)", ""
    )

    child_photo_rel = _copy_photo(photo_path, first_name) if photo_path else ""

    # --- LIVRE ---
    print("\n📚 LE LIVRE")
    print("─" * 35)

    theme = _input_required("Thème (ex : La forêt magique, L'espace, Les fonds marins)")
    educational_value = _input_required(
        "Valeur éducative (ex : Le courage, L'amitié, Le partage)"
    )
    tone = _input("Tonalité souhaitée (ou Entrée pour auto)", "")
    title_suggestion = _input("Suggestion de titre (ou Entrée pour auto)", "")
    dedication = _input("Dédicace (texte libre, ou Entrée pour passer)", "")
    language = _input("Langue", "fr")

    # --- PERSONNAGES SECONDAIRES ---
    print("\n👥 PERSONNAGES SECONDAIRES")
    print("─" * 35)

    secondary_characters = []
    while _confirm("Ajouter un personnage secondaire ?"):
        relation = _input_required(
            "  Relation avec l'enfant (ex : son chat, sa mamie)"
        )
        display_name = _input(
            "  Nom dans l'histoire (ex : Moustache) ou Entrée", ""
        )
        char_photo = _input_photo("  Chemin vers une photo")
        char_appearance = _input_required("  Description physique")

        char_photo_rel = ""
        if char_photo:
            name = display_name if display_name else relation
            char_photo_rel = _copy_photo(char_photo, name)

        char_data = {
            "relation": relation,
            "display_name": display_name,
            "appearance": char_appearance,
        }
        if char_photo_rel:
            char_data["photo"] = char_photo_rel

        secondary_characters.append(char_data)
        print()

    # --- CONFIG ---
    config = {
        "book": {
            "title_suggestion": title_suggestion,
            "language": language,
            "theme": theme,
            "educational_value": educational_value,
            "tone": tone,
            "dedication": dedication,
        },
        "child": {
            "first_name": first_name,
            "age": age,
            "gender": gender,
            "appearance": appearance,
            "default_outfit": default_outfit,
        },
        "secondary_characters": secondary_characters,
        "options": {
            "include_questions_page": True,
            "number_of_questions": 5,
        },
    }

    if child_photo_rel:
        config["child"]["photo"] = child_photo_rel

    # --- RÉCAPITULATIF ---
    print("\n📋 RÉCAPITULATIF")
    print("─" * 35)
    print(f"  Prénom : {first_name}")
    print(f"  Âge : {age} ans")
    print(f"  Genre : {gender}")
    print(f"  Apparence : {appearance}")
    if default_outfit:
        print(f"  Tenue : {default_outfit}")
    if child_photo_rel:
        print(f"  Photo : {child_photo_rel}")
    print(f"  Thème : {theme}")
    print(f"  Valeur : {educational_value}")
    if tone:
        print(f"  Tonalité : {tone}")
    if title_suggestion:
        print(f"  Titre suggéré : {title_suggestion}")
    if dedication:
        print(f"  Dédicace : {dedication}")
    print(f"  Langue : {language}")
    if secondary_characters:
        print(f"  Personnages secondaires : {len(secondary_characters)}")
        for c in secondary_characters:
            name = c.get("display_name", c["relation"])
            print(f"    - {name} ({c['relation']})")

    print()
    if not _confirm("✅ Confirmer et lancer la génération ?"):
        print("❌ Génération annulée.")
        return ""

    config_path = os.path.join(PROJECT_DIR, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Configuration sauvegardée : {config_path}")

    return config_path
