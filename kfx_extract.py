import json, sys

from kfxlib import yj_book

def load_sections(kfx_path):
    book = yj_book.YJ_Book(kfx_path)
    cj = json.loads(book.convert_to_json_content().decode("utf-8"))
    secs = sorted([e for e in cj.get("data", []) if e.get("type") == 1], key=lambda x: x["position"])
    for i, s in enumerate(secs[:-1]):
        s["length"] = secs[i + 1]["position"] - s["position"]
    if secs:
        secs[-1]["length"] = len(secs[-1]["content"])
    return secs

def text_between(secs, start, end):
    parts = []
    for s in secs:
        a, b = s["position"], s["position"] + s["length"]
        if b <= start or a > end:
            continue
        lo, hi = max(start, a) - a, min(end + 1, b) - a
        if hi > lo:
            parts.append(s["content"][lo:hi])
    return " ".join(p.strip() for p in parts if p.strip())
