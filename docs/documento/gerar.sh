#!/bin/bash
# Gera o PDF do documento consolidado a partir de documento.html (Chrome sem janela) e confere pelo texto.
set -eo pipefail
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
SAIDA="Parallax-documento-consolidado.pdf"
PERFIL="$(mktemp -d)"
"$CHROME" --headless=new --disable-gpu --no-first-run --user-data-dir="$PERFIL" \
  --no-pdf-header-footer --print-to-pdf="$SAIDA" "file://$PWD/documento.html" 2>/dev/null
rm -rf "$PERFIL"
pdfinfo "$SAIDA" | grep -E "Pages|Page size"
PEND=$(pdftotext "$SAIDA" - | grep -c "A ENTRAR" || true)
echo "pendentes (A ENTRAR): $PEND"
TRAV=$(pdftotext "$SAIDA" - | grep -c "[—·]" || true)
echo "linhas com travessão ou ponto do meio: $TRAV"
