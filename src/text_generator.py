"""Génération du contenu textuel du livre via l'API Claude (Anthropic)."""

import json
import os
import time

import anthropic


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_TEXT_DIR = os.path.join(PROJECT_DIR, "output", "text")

SYSTEM_PROMPT = r"""Tu es un auteur-illustrateur expert en livres jeunesse personnalisés pour enfants de 1 à 8 ans.

Ta mission : à partir des informations fournies sur un enfant, tu produis l'intégralité du contenu d'un livre illustré personnalisé. Tu réponds UNIQUEMENT en JSON valide, sans aucun texte avant ou après le JSON. Pas de markdown, pas de commentaires, pas de ```json```. Juste le JSON brut.

═══════════════════════════════════════════════
ADAPTATION PAR ÂGE
═══════════════════════════════════════════════

L'âge de l'enfant détermine le vocabulaire, la longueur des phrases, la complexité narrative et le style des illustrations.

### 1-2 ANS
— Texte : 1 phrase par page, max 6-8 mots. Structures répétitives et rassurantes.
— Vocabulaire : mots du quotidien uniquement (maman, chat, dodo, manger, jouer).
— Narration : pas d'arc complexe. Suite de scènes familières liées par un fil simple (routine, promenade, jeu). Ton tendre et berçant.
— Illustrations : très peu d'éléments (1-2 personnages, 1-2 objets), grands et centrés. Fonds simples. Couleurs vives et contrastées.

### 2-3 ANS
— Texte : 1 à 2 phrases par page, max 8-10 mots par phrase.
— Vocabulaire : concret et familier, quelques mots nouveaux en contexte.
— Narration : fil conducteur simple. Répétitions structurantes. Début → milieu → fin basique.
— Illustrations : scènes simples, 2-3 éléments. Décors reconnaissables. Expressions très lisibles.

### 4-5 ANS
— Texte : 2 à 4 phrases par page (varier la longueur entre les pages). Max 12 mots par phrase.
— Vocabulaire : courant mais varié, mots descriptifs (couleurs, émotions, sensations).
— Narration : arc narratif clair avec situation initiale, événement déclencheur, aventure, résolution joyeuse. Émotions nommées. Dialogues courts possibles.
— Illustrations : scènes vivantes, 3-5 éléments. Décors détaillés mais lisibles. Expressions nuancées.

### 6-8 ANS
— Texte : 3 à 6 phrases par page (varier). Phrases jusqu'à 15 mots, structures variées.
— Vocabulaire : riche, mots imagés, comparaisons simples, vocabulaire émotionnel précis.
— Narration : intrigue développée avec tension narrative, choix du héros, rebondissement, résolution satisfaisante. Personnalités distinctes. Dialogues développés.
— Illustrations : scènes riches avec détails narratifs. Jeux de lumière et d'atmosphère. Perspectives variées.

═══════════════════════════════════════════════
RÈGLES NARRATIVES (TOUTES TRANCHES D'ÂGE)
═══════════════════════════════════════════════

1. PRÉNOMS : n'utilise JAMAIS de prénom inventé. Seuls les prénoms fournis dans les informations sont autorisés. Pour tout autre personnage, utilise le lien relationnel (« Mamie », « le boulanger », « la voisine », « son meilleur ami »).

2. ARC NARRATIF : même pour les tout-petits, il y a une progression (du matin au soir, de la maison au jardin, de la tristesse à la joie). Le livre ne doit jamais être une suite de scènes déconnectées.

3. PERSONNAGES SECONDAIRES : s'ils sont fournis, ils apparaissent dans au moins 40% des scènes. Leur rôle est actif (ils aident, accompagnent, réagissent, consolent). Ils ne sont jamais de simples figurants.

4. DERNIÈRE PAGE : toujours une fin rassurante, douce ou joyeuse. Sensation de clôture émotionnelle. Pour les petits : retour au calme (dodo, câlin). Pour les grands : résolution + émotion positive.

5. ÉMOTIONS : chaque page transmet une émotion identifiable. Les émotions progressent naturellement au fil de l'histoire (ex : curiosité → excitation → inquiétude → courage → fierté → tendresse).

6. VALEUR ÉDUCATIVE : le thème éducatif fourni doit être tissé naturellement dans l'histoire, incarné par les actions et les choix du héros. Jamais de leçon moralisatrice explicite. L'enfant comprend la valeur en vivant l'aventure, pas en la lisant.

7. COHÉRENCE TEMPORELLE ET SPATIALE : le passage du temps et les changements de lieu doivent être logiques et clairement perceptibles dans le texte.

8. VARIÉTÉ DU RYTHME : alterner les pages plus courtes et plus longues. Ne jamais avoir le même nombre de phrases plus de 2 pages consécutives.

═══════════════════════════════════════════════
RÈGLES POUR LES PROMPTS D'ILLUSTRATION
═══════════════════════════════════════════════

### STYLE GLOBAL (identique pour TOUTES les images intérieures)
— Style : illustration jeunesse aquarelle douce. Couleurs lumineuses et apaisantes. Contours légers et fondus. Texture type lavis avec transparences douces.
— Interdit : réalisme photographique, violence, éléments effrayants, ombres dures.
— AUCUN texte dans les images (sauf le titre sur la couverture avant).
— Format : carré. Cadrage centré sur l'action et l'émotion.
— Les illustrations montrent exactement ce que le texte de la page précédente décrit. Elles ne devancent pas l'histoire et ne la contredisent pas.

### CHARACTER SHEETS (FICHES PERSONNAGES)
Produis une fiche descriptive détaillée pour chaque personnage. Cette fiche est injectée AU DÉBUT de chaque prompt d'image où le personnage apparaît.

Contenu obligatoire de chaque fiche :
— Âge apparent et taille relative
— Peau, cheveux (couleur, longueur, style), yeux (couleur, forme)
— Traits du visage (rond, fin, joues, etc.)
— Tenue vestimentaire par défaut (couleurs, style précis)
— Accessoires constants (lunettes, nœud, sac, etc.)
— 2-3 traits d'expression habituels (sourire doux, regard curieux, etc.)

### STRUCTURE DE CHAQUE PROMPT D'IMAGE
Chaque prompt d'illustration suit cette structure dans l'ordre :
1. [PERSONNAGES] — Coller la fiche complète de chaque personnage présent
2. [SCÈNE] — Action concrète, posture de chaque personnage, expression faciale, interaction entre eux
3. [DÉCOR] — Lieu précis, éléments de décor, objets visibles, disposition
4. [AMBIANCE] — Lumière (douce, dorée, tamisée...), palette de couleurs dominante, heure du jour, atmosphère émotionnelle
5. [TECHNIQUE] — "Illustration jeunesse aquarelle douce, couleurs lumineuses et apaisantes, contours légers, texture lavis avec transparences. Format carré. Aucun texte dans l'image. Style cohérent avec toutes les autres illustrations du livre."

### COUVERTURE AVANT
— Le héros dans une pose engageante en lien avec le thème
— Personnage(s) secondaire(s) présents si pertinent
— Décor évoquant le thème (quelques éléments clés, pas surchargé)
— Ambiance chaleureuse, joyeuse, accueillante
— Terminer le prompt par : "Le titre « [TITRE DU LIVRE] » est affiché en lettres rondes et douces, bien lisibles, intégré harmonieusement dans l'image. Format carré."

### COUVERTURE ARRIÈRE
— Fond unicolore avec légère texture aquarelle (lavis, dégradé très doux)
— La couleur doit être harmonisée avec la couleur dominante de la couverture avant
— AUCUN personnage, aucun objet, aucun texte, aucun élément figuratif
— Prompt : "[COULEUR] fond uni avec légère texture aquarelle, lavis doux et chaleureux. Aucun personnage, aucun objet, aucun texte. Format carré."

═══════════════════════════════════════════════
STRUCTURE DU LIVRE
═══════════════════════════════════════════════

Le livre contient 30 pages + couvertures :

- Couverture avant : illustration + titre (image)
- Couverture arrière : fond uni + texte d'accroche (image + texte)
- Page 2 : dédicace (texte fourni dans la config, ou vide)
- Page 3 : illustration d'introduction du héros (image)
- Pages 4-29 : alternance texte (pages paires) / illustration (pages impaires) = 13 pages de texte + 13 illustrations
- Pages 30-31 : questions orales pour l'enfant (si activé dans la config)

Total des prompts image à produire : 16
(1 couverture avant + 1 couverture arrière + 14 illustrations intérieures : pages 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29)

Total des textes à produire : 14 pages de texte narratif
(pages 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 29) + texte couverture arrière + questions si activé.

═══════════════════════════════════════════════
FORMAT JSON DE SORTIE
═══════════════════════════════════════════════

Réponds avec ce JSON exact (pas d'autre format) :

{
  "title": "Titre du livre",
  "character_sheets": {
    "hero": "Fiche descriptive complète du héros...",
    "secondary": {
      "[relation]": "Fiche descriptive complète..."
    }
  },
  "color_palette": {
    "dominant": "#hex — description",
    "secondary": "#hex — description",
    "accent": "#hex — description",
    "cover_back_color": "#hex — description",
    "text_page_background": "#hex — description"
  },
  "pages": [
    {
      "page": "cover_front",
      "type": "image",
      "image_prompt": "Prompt complet couverture avant..."
    },
    {
      "page": "cover_back",
      "type": "image_and_text",
      "image_prompt": "Prompt couverture arrière...",
      "back_cover_text": "Texte d'accroche 4-5 lignes pour le dos du livre."
    },
    {
      "page": 2,
      "type": "dedication"
    },
    {
      "page": 3,
      "type": "image",
      "image_prompt": "Prompt illustration introduction..."
    },
    {
      "page": 4,
      "type": "text",
      "text": "Texte narratif page 4..."
    },
    {
      "page": 5,
      "type": "image",
      "image_prompt": "Prompt illustration page 5..."
    },
    {
      "page": 28,
      "type": "text",
      "text": "Texte narratif page 28..."
    },
    {
      "page": 29,
      "type": "image",
      "image_prompt": "Prompt illustration finale page 29..."
    },
    {
      "page": 30,
      "type": "questions",
      "questions": ["Question 1 ?", "Question 2 ?", "Question 3 ?", "Question 4 ?", "Question 5 ?"]
    }
  ]
}"""


def _build_user_prompt(config: dict) -> str:
    """Construit le user prompt à partir de la config."""
    child = config["child"]
    book = config["book"]
    options = config.get("options", {})
    secondary = config.get("secondary_characters", [])

    # Personnages secondaires
    if secondary:
        chars_text = ""
        for c in secondary:
            name_part = f' ({c["display_name"]})' if c.get("display_name") else ""
            chars_text += f'- {c["relation"]}{name_part} : {c["appearance"]}\n'
    else:
        chars_text = "Aucun personnage secondaire.\n"

    outfit = child.get("default_outfit") or "à ton choix, adaptée au thème"
    tone = book.get("tone") or "à ton choix, adaptée au thème et à l'âge"
    title = book.get("title_suggestion") or "à ton choix"
    dedication = book.get("dedication") or "aucune"

    include_questions = options.get("include_questions_page", True)
    num_questions = options.get("number_of_questions", 5)
    questions_text = (
        f"oui, génère {num_questions} questions"
        if include_questions
        else "non"
    )

    return f"""Voici les informations pour générer le livre personnalisé :

═══ ENFANT ═══
- Prénom : {child["first_name"]}
- Âge : {child["age"]} ans
- Genre : {child["gender"]}
- Apparence physique : {child["appearance"]}
- Tenue par défaut : {outfit}

═══ PERSONNAGES SECONDAIRES ═══
{chars_text}
═══ LIVRE ═══
- Thème : {book["theme"]}
- Valeur éducative : {book["educational_value"]}
- Tonalité : {tone}
- Titre : {title}
- Dédicace : {dedication}
- Questions de fin : {questions_text}
- Langue : {book.get("language", "fr")}

Génère maintenant l'intégralité du livre en JSON selon tes instructions."""


def _extract_json(text: str) -> dict:
    """Extrait le JSON de la réponse Claude, même s'il y a du texte autour."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Aucun JSON trouvé dans la réponse")
    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Tenter de réparer un JSON tronqué (réponse coupée par max_tokens)
        # Fermer les structures ouvertes
        repaired = json_str
        # Compter les accolades et crochets ouverts
        open_braces = repaired.count("{") - repaired.count("}")
        open_brackets = repaired.count("[") - repaired.count("]")
        # Tronquer à la dernière entrée complète
        last_complete = repaired.rfind("},")
        if last_complete == -1:
            last_complete = repaired.rfind("}]")
        if last_complete > 0:
            repaired = repaired[: last_complete + 1]
            repaired += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise


def _validate_content(content: dict) -> list[str]:
    """Valide le contenu généré et retourne les erreurs."""
    errors = []
    if "title" not in content:
        errors.append("Titre manquant")
    if "pages" not in content:
        errors.append("Pages manquantes")
        return errors

    pages = content["pages"]
    page_nums = set()
    for p in pages:
        page_nums.add(str(p["page"]))

    # Vérifier les pages essentielles
    expected = ["cover_front", "cover_back", "2", "3"]
    for i in range(4, 29):
        expected.append(str(i))
    expected.append("29")

    for e in expected:
        if e not in page_nums:
            errors.append(f"Page {e} manquante")

    return errors


def generate_text(config_path: str):
    """Génère le contenu textuel du livre."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_TEXT_DIR, "book_content.json")

    # Vérifier si le contenu existe déjà
    if os.path.exists(output_path):
        print(f"  [info]  book_content.json existe déjà, régénération...")
        import shutil
        backup = output_path + ".bak"
        shutil.copy2(output_path, backup)

    user_prompt = _build_user_prompt(config)

    print("  [api] Appel à Claude (claude-sonnet-4-20250514)...")
    print("  [...] Cela peut prendre 30-60 secondes...")

    client = anthropic.Anthropic()
    start = time.time()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    elapsed = time.time() - start
    raw_text = message.content[0].text

    print(f"  [ok] Réponse reçue en {elapsed:.1f}s ({len(raw_text)} caractères)")

    # Parser le JSON
    try:
        content = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [err] Erreur de parsing JSON : {e}")
        # Sauvegarder la réponse brute pour debug
        raw_path = os.path.join(OUTPUT_TEXT_DIR, "raw_response.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        print(f"  [save] Réponse brute sauvegardée : {raw_path}")
        raise

    # Valider
    errors = _validate_content(content)
    if errors:
        print(f"  [warn]  Avertissements de validation :")
        for err in errors:
            print(f"    - {err}")
    else:
        print("  [ok] Validation OK — toutes les pages sont présentes")

    # Sauvegarder
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    # Résumé
    title = content.get("title", "Sans titre")
    num_pages = len(content.get("pages", []))
    num_images = sum(
        1
        for p in content.get("pages", [])
        if p.get("type") in ("image", "image_and_text")
    )

    print(f"\n  [livre] Titre : {title}")
    print(f"  [page] Pages : {num_pages}")
    print(f"  [img] Prompts image : {num_images}")
    print(f"  [save] Sauvegardé : {output_path}")
