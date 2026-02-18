#!/usr/bin/env python3
"""Point d'entrée CLI pour le générateur de livres enfants personnalisés."""

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def check_api_keys():
    """Vérifie que les clés API sont configurées."""
    missing = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"\n❌ Clés API manquantes : {', '.join(missing)}")
        print("   Configurez-les dans le fichier .env (voir .env.example)")
        sys.exit(1)


def run_interactive(args):
    """Génération complète via formulaire interactif."""
    from src.config_builder import build_config_interactive

    config_path = build_config_interactive()
    if config_path:
        run_full_pipeline(config_path)


def run_full_pipeline(config_path):
    """Exécute le pipeline complet : texte → images → PDF."""
    start = time.time()
    print("\n" + "=" * 50)
    print("  🚀 Lancement du pipeline complet")
    print("=" * 50)

    run_step_text(config_path)
    run_step_images(config_path)
    run_step_pdf(config_path)

    elapsed = time.time() - start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    prenom = config["child"]["first_name"]

    print("\n" + "=" * 50)
    print(f"  ✅ Livre généré en {minutes}m{seconds}s !")
    print(f"  📖 Vérifiez le dossier output/final/")
    print("=" * 50)


def run_step_text(config_path):
    """Étape 1 : Génération du texte."""
    from src.text_generator import generate_text

    print("\n📝 ÉTAPE 1/3 — Génération du texte avec Claude...")
    print("-" * 40)
    generate_text(config_path)


def run_step_images(config_path):
    """Étape 2 : Génération des images."""
    from src.image_generator import generate_all_images

    print("\n🎨 ÉTAPE 2/3 — Génération des illustrations avec gpt-image-1...")
    print("-" * 40)
    generate_all_images(config_path)


def run_step_pdf(config_path):
    """Étape 3 : Assemblage du PDF."""
    from src.pdf_builder import build_pdf

    print("\n📄 ÉTAPE 3/3 — Assemblage du PDF...")
    print("-" * 40)
    build_pdf(config_path)


def run_regenerate(config_path, page, edit_prompt=False, cascade=False):
    """Régénération d'une image individuelle."""
    from src.regenerate import regenerate_image

    regenerate_image(config_path, page, edit_prompt=edit_prompt, cascade=cascade)


def run_preview(config_path):
    """Prévisualisation HTML."""
    from src.preview import generate_preview

    generate_preview(config_path)


def run_retry_failed(config_path):
    """Relance les images échouées."""
    from src.image_generator import retry_failed_images

    retry_failed_images(config_path)


def main():
    parser = argparse.ArgumentParser(
        description="Générateur de livres illustrés personnalisés pour enfants",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation :
  python generate.py --interactive                      Formulaire interactif
  python generate.py --config config.json               Pipeline complet
  python generate.py --config config.json --step text   Texte uniquement
  python generate.py --config config.json --step images Images uniquement
  python generate.py --config config.json --step pdf    PDF uniquement
  python generate.py --config config.json --regenerate 7
  python generate.py --config config.json --preview
  python generate.py --config config.json --retry-failed
        """,
    )

    parser.add_argument(
        "--interactive", action="store_true", help="Lancer le formulaire interactif"
    )
    parser.add_argument("--config", type=str, help="Chemin vers le fichier config.json")
    parser.add_argument(
        "--step",
        choices=["text", "images", "pdf"],
        help="Exécuter une étape spécifique",
    )
    parser.add_argument(
        "--regenerate",
        type=str,
        help="Régénérer une image (numéro de page ou cover_front/cover_back)",
    )
    parser.add_argument(
        "--edit-prompt",
        action="store_true",
        help="Modifier le prompt avant régénération",
    )
    parser.add_argument(
        "--cascade",
        action="store_true",
        help="Régénérer toutes les images après la couverture",
    )
    parser.add_argument(
        "--preview", action="store_true", help="Générer une prévisualisation HTML"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Relancer les images échouées",
    )

    args = parser.parse_args()

    print("\n" + "═" * 50)
    print("  📖 Générateur de Livre Enfant Personnalisé")
    print("═" * 50)

    check_api_keys()

    if args.interactive:
        run_interactive(args)
    elif args.config:
        if not os.path.exists(args.config):
            print(f"\n❌ Fichier config introuvable : {args.config}")
            sys.exit(1)

        if args.regenerate:
            run_regenerate(
                args.config, args.regenerate, args.edit_prompt, args.cascade
            )
        elif args.preview:
            run_preview(args.config)
        elif args.retry_failed:
            run_retry_failed(args.config)
        elif args.step:
            if args.step == "text":
                run_step_text(args.config)
            elif args.step == "images":
                run_step_images(args.config)
            elif args.step == "pdf":
                run_step_pdf(args.config)
        else:
            run_full_pipeline(args.config)
    else:
        parser.print_help()
        print("\n💡 Astuce : lancez avec --interactive pour commencer !")


if __name__ == "__main__":
    main()
