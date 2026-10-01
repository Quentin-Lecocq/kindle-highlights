#!/usr/bin/env bash
# Installs the two third-party readers the tool needs, pinned to the versions tested on 2026-10-01.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p vendor
clone() {  # repo dir commit
  if [ ! -d "vendor/$2" ]; then git clone -q "https://github.com/$1.git" "vendor/$2"; fi
  git -C "vendor/$2" fetch -q --depth 1 origin "$3" 2>/dev/null || true
  git -C "vendor/$2" checkout -q "$3"
}
clone kluyg/calibre-kfx-input calibre-kfx-input 44db6b6ee8c0094a98c33770575a9070ddb90fda   # kfxlib (KFX books)
clone kevinhendricks/KindleUnpack KindleUnpack bf0ca6ece4e73494625e7950be3e259b6260774c     # KF8/AZW3 books
python3 -m pip install -q lxml pillow pypdf 2>/dev/null || python3 -m pip install -q --break-system-packages lxml pillow pypdf
echo "OK"
