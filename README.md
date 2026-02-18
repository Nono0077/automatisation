# Generateur de Livres Enfants Personnalises

Generateur automatise de livres illustres personnalises pour enfants de 1 a 8 ans.

Utilise l'API Claude (Anthropic) pour le texte et gpt-image-1 (OpenAI) pour les illustrations.

## Installation

```bash
pip install -r requirements.txt
```

Configurez vos cles API dans `.env` (voir `.env.example`).

Telechargez la police Quicksand depuis Google Fonts et placez les fichiers TTF dans `fonts/`.

## Utilisation

### Generation complete (formulaire interactif)

```bash
python generate.py --interactive
```

### Generation via fichier config

```bash
python generate.py --config config.json
```

### Etapes individuelles

```bash
python generate.py --config config.json --step text
python generate.py --config config.json --step images
python generate.py --config config.json --step pdf
```

### Regeneration d'une image

```bash
python generate.py --config config.json --regenerate 7
python generate.py --config config.json --regenerate 7 --edit-prompt
python generate.py --config config.json --regenerate cover_front --cascade
```

### Previsualisation HTML

```bash
python generate.py --config config.json --preview
```

### Relancer les images echouees

```bash
python generate.py --config config.json --retry-failed
```

## Structure du projet

```
childbook-generator/
├── generate.py            # Point d'entree CLI
├── config.json            # Configuration du livre
├── src/
│   ├── config_builder.py  # Formulaire interactif
│   ├── text_generator.py  # Generation texte (Claude)
│   ├── image_generator.py # Generation images (gpt-image-1)
│   ├── pdf_builder.py     # Assemblage PDF
│   ├── regenerate.py      # Regeneration d'images
│   └── preview.py         # Previsualisation HTML
├── fonts/                 # Polices TTF (Quicksand)
├── photos/                # Photos de reference
└── output/
    ├── text/              # book_content.json
    ├── images/            # Illustrations PNG
    ├── images_backup/     # Backups (regeneration)
    └── final/             # PDF final
```
