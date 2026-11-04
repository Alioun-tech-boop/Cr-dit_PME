#!/usr/bin/env bash
# Installation utilisateur du modèle français officiel, sans privilèges système.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="$project_root/.local/share/tessdata"
system_data=/usr/share/tesseract-ocr/5/tessdata
expected=ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca
if ! command -v tesseract >/dev/null; then
    echo 'Tesseract manque. Sur Debian : sudo apt-get install tesseract-ocr tesseract-ocr-fra' >&2
    exit 1
fi
if [[ ! -d "$system_data/configs" ]]; then
    echo "Configurations Tesseract introuvables dans $system_data ; installer tesseract-ocr." >&2
    exit 1
fi
mkdir -p "$target"
if ! echo "$expected  $target/fra.traineddata" | sha256sum --check --status 2>/dev/null; then
    download="$(mktemp "$target/fra.XXXXXX")"
    trap 'rm -f "$download"' EXIT
    curl --fail --location --max-time 60 \
        https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/fra.traineddata \
        --output "$download"
    echo "$expected  $download" | sha256sum --check --status
    mv "$download" "$target/fra.traineddata"
fi
# TSV dépend aussi des configurations ; un modèle seul ne suffit pas.
for item in configs tessconfigs eng.traineddata osd.traineddata; do
    if [[ -e "$system_data/$item" && ! -e "$target/$item" ]]; then
        ln -s "$system_data/$item" "$target/$item"
    fi
done
TESSDATA_PREFIX="$target" tesseract --list-langs
printf 'Pour la session courante : export TESSDATA_PREFIX="%s"\n' "$target"
