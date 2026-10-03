#!/usr/bin/env python3
"""Rebuild Kindle highlights (text + notes) from a copy of the Kindle's storage.

Why: on some recent Kindles (reported from firmware 5.19) the device no longer writes
documents/My Clippings.txt. Highlights are stored as *positions* only, in
  system/ksdk/.annotations/amzn1.account.<ID>/ksdk_annotation_v1.db   (new)
  documents/**/<book>.sdr/*.{mbp1,yjr,azw3r}                          (legacy sidecars)
The text is recovered by reading the book file still on the device.

Usage:
  python3 kindle_highlights.py SRC OUT [--since YYYY-MM-DD] [--lang en|fr] [--tz Area/City]
SRC must contain the copied `documents/` folder and `ksdk/` (or `system/ksdk/`).
OUT receives: My Clippings.txt, a Markdown export, highlights.json, report.txt

Position rules (verified 2026-10-01 on a Kindle Paperwhite):
  * MOBI7 (.azw/.mobi, no KF8)  -> byte offset in the uncompressed text
  * KF8 (.azw3, or combo .azw)  -> byte offset in the assembled skeleton+fragment text
  * KFX (.kfx)                  -> kfxlib content positions (DRM books cannot be read)
Dependencies (see setup.sh): kfxlib (jhowell KFX Input) and KindleUnpack, lxml, pillow, pypdf.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sqlite3
import struct
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "vendor", "calibre-kfx-input"), os.path.join(HERE, "vendor", "KindleUnpack")]

from krds import parse, find                       # noqa: E402
from mobi_text import raw_text                       # noqa: E402
from textclean import clean                          # noqa: E402

TZ = datetime.datetime.now().astimezone().tzinfo   # overridden by --tz
BOOK_EXT = (".kfx", ".azw3", ".azw", ".mobi", ".prc")
SIDE_EXT = (".mbp1", ".mbp", ".yjr", ".azw3r")
# file-name noise added by download sites and stores: '(something.org, ...)', '(... Library)', '(French Edition)'
JUNK = re.compile(r"\s*\((?:[^()]*\b[\w-]+\.[a-z]{2,4}\b[^()]*|[^()]*\blibrary\b[^()]*|[^()]*\bedition)\)", re.I)

TEXTS = {
    "en": dict(md_file="Kindle Highlights.md", title="Kindle Highlights", recovered="Recovered on {d:%Y-%m-%d}.",
               count="{n} highlights", note="**My note:**", loc="Location {l} · {d:%Y-%m-%d}"),
    "fr": dict(md_file="Surlignages Kindle.md", title="Surlignages Kindle", recovered="Récupérés le {d:%d/%m/%Y}.",
               count="{n} surlignages", note="**Ma note :**", loc="Emplacement {l} · {d:%d/%m/%Y}"),
}


# ---------------------------------------------------------------- book files
def index_books(docs):
    """Map ID suffix and stem -> book path for every book file on the device copy."""
    by_id, by_stem = {}, {}
    for p in glob.glob(os.path.join(docs, "**", "*"), recursive=True):
        if not p.lower().endswith(BOOK_EXT) or ".sdr" + os.sep in p:
            continue
        stem = os.path.splitext(os.path.basename(p))[0]
        by_stem[stem] = p
        m = re.search(r"_([A-Z0-9]{10}|[A-F0-9]{32}|[A-Z0-9]{32})$", stem)
        if m:
            by_id[m.group(1)] = p
    return by_id, by_stem


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_sideloaded(guid, by_stem):
    """guid like 'The_PARA_Method__Simplify,_Orga:C49DBC70' -> documents/PARA Method_ ... .azw3"""
    prefix = norm(guid.split(":")[0])
    prefix2 = norm(re.sub(r"^(the|a|an|l|le|la|les)_", "", guid.split(":")[0], flags=re.I))
    best = None
    for stem, p in by_stem.items():
        n = norm(stem)
        n2 = norm(re.sub(r",\s*(the|a|an|l'|le|la|les)\b", "", stem, flags=re.I))
        for a in (prefix, prefix2):
            for b in (n, n2):
                if a and (b.startswith(a) or a.startswith(b[:len(a)]) and len(a) > 12 and b.startswith(a[:12])):
                    if best is None or len(stem) < len(best[0]):
                        best = (stem, p)
    return best[1] if best else None


def book_format(path):
    if path.lower().endswith(".kfx"):
        return "kfx"
    d = open(path, "rb").read()
    if b"BOUNDARY" in d[:len(d)]:
        # combo MOBI7/KF8: the Kindle reads the KF8 part
        n = struct.unpack(">H", d[76:78])[0]
        offs = [struct.unpack(">I", d[78 + i * 8:82 + i * 8])[0] for i in range(n)] + [len(d)]
        if any(offs[i + 1] - offs[i] == 8 and d[offs[i]:offs[i] + 8] == b"BOUNDARY" for i in range(n)):
            return "kf8"
    r0 = struct.unpack(">I", d[78:82])[0]
    version = struct.unpack(">I", d[r0 + 0x24:r0 + 0x28])[0]
    return "kf8" if version >= 8 else "mobi"


def mobi_meta(path):
    d = open(path, "rb").read()
    r0 = struct.unpack(">I", d[78:82])[0]
    hl = struct.unpack(">I", d[r0 + 20:r0 + 24])[0]
    meta = {}
    if struct.unpack(">I", d[r0 + 0x80:r0 + 0x84])[0] & 0x40:
        e = r0 + 16 + hl
        cnt = struct.unpack(">I", d[e + 8:e + 12])[0]
        p = e + 12
        for _ in range(cnt):
            t, ln = struct.unpack(">II", d[p:p + 8])
            v = d[p + 8:p + ln].decode("utf-8", "ignore").strip()
            if t in (100, 503):
                meta.setdefault(t, v)
            p += ln
    return meta.get(503), meta.get(100)


class Resolver:
    """Turns (start, end) positions into text for one book file."""

    def __init__(self, path):
        self.path, self.fmt = path, book_format(path)
        self.title = self.author = None
        if self.fmt == "kfx":
            from kfxlib import yj_book
            from kfx_extract import load_sections, text_between
            secs = load_sections(path)  # raises KFXDRMError for DRM books
            try:
                md = yj_book.YJ_Book(path).get_metadata()
                self.title, self.author = md.title, ", ".join(md.authors or [])
            except Exception:
                pass
            self.get = lambda a, z: re.sub(r"\s+", " ", text_between(secs, a, z)).strip()
        else:
            self.title, self.author = mobi_meta(path)
            if self.fmt == "kf8":
                from kf8_text import assembled_text
                t = assembled_text(path)
            else:
                t = raw_text(path)
            self.get = lambda a, z: clean(t[a:z + 1])


# ---------------------------------------------------------------- annotations
def ms(t):
    return datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc)


def from_db(db_path, by_id, by_stem, groups):
    c = sqlite3.connect(db_path)
    queries = [("server_view", "dataset_id"), ("local_edit", "dataset_id"), ("nonsyncable_annotations", "book_id")]
    seen = set()
    for table, col in queries:
        try:
            rows = c.execute(f"SELECT annotation_id, dataset, serialized_payload FROM {table} WHERE dataset IN (1,3)").fetchall()
        except sqlite3.Error:
            continue
        for aid, ds, payload in rows:
            p = json.loads(payload)
            bd = p.get("book_data", {})
            asin, guid = bd.get("asin", ""), bd.get("guid", "")
            if (asin, aid) in seen:      # ids like 'kindle.highlight-217710' are only unique per book
                continue
            seen.add((asin, aid))
            path = by_id.get(asin) or (match_sideloaded(guid, by_stem) if bd.get("contentType") == "EBOK" and "-" in asin else None)
            key = path or "id:" + asin
            g = groups.setdefault(key, {"path": path, "hint": guid if "-" in asin else asin, "hl": {}, "notes": []})
            a, z = p["start_position"]["shortPosition"], p["end_position"]["shortPosition"]
            if ds == 1:
                g["hl"].setdefault((a, z), ms(p["created_time"]))
            else:
                body = json.loads(p.get("json_metadata") or "{}").get("note_text", "").strip()
                g["notes"].append((a, body, ms(p["created_time"])))


def from_sidecars(docs, by_stem, groups):
    for f in glob.glob(os.path.join(docs, "**", "*.sdr", "*"), recursive=True):
        if not f.endswith(SIDE_EXT):
            continue
        stem = os.path.basename(os.path.dirname(f))[:-4]
        path = by_stem.get(stem)
        fmt = "kfx" if f.endswith(".yjr") else "mobi"
        try:
            objs = parse(f)
        except Exception:
            continue
        hls = list(find(objs, "annotation.personal.highlight"))
        nts = list(find(objs, "annotation.personal.note"))
        if not hls and not nts:
            continue
        m = re.search(r"_([A-Z0-9]{10}|[A-F0-9]{32}|[A-Z0-9]{32})$", stem)
        key = path or ("id:" + m.group(1) if m else "stem:" + stem)
        g = groups.setdefault(key, {"path": path, "hint": stem, "hl": {}, "notes": []})
        g["hint"] = stem
        for h in hls:
            a, z = (pos_side(v, fmt) for v in h.vals[:2])
            g["hl"].setdefault((a, z), ms(h.vals[2]))
        for n in nts:
            a = pos_side(n.vals[0], fmt)
            if not any(x[0] == a for x in g["notes"]):
                g["notes"].append((a, str(n.vals[5]).strip(), ms(n.vals[2])))


def pos_side(v, fmt):
    s = str(v)
    if fmt == "kfx":                    # 'AXoGAAAAAAAA:88625'
        return int(s.rsplit(":", 1)[-1])
    return int(s.split(":")[0])         # '190324:190324:57005:...' or '19521'


# ---------------------------------------------------------------- output
def tidy_author(a):
    a = (a or "").strip()
    parts = [x.strip() for x in a.split(",")]
    if len(parts) == 2 and " " not in parts[0] and parts[1]:   # 'Ahrens, Sönke' -> 'Sönke Ahrens'
        return f"{parts[1]} {parts[0]}"
    return a


def tidy_title(t, author):
    t = JUNK.sub("", t or "").strip()
    for name in re.split(r"[,&;]| and ", author or ""):
        last = name.strip().split(" ")[-1] if name.strip() else ""
        if len(last) > 2:
            # drop '(Austin Kleon)', '[Cole, Nicolas]', ' - Tiago Forte' style author tags (innermost first)
            inner = re.compile(r"\s*[\(\[][^\(\)\[\]]*\b" + re.escape(last) + r"\b[^\(\)\[\]]*[\)\]]", re.I)
            while inner.search(t):
                t = inner.sub("", t)
            t = re.sub(r"\s+-\s+[^-]*\b" + re.escape(last) + r"\b.*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t.replace("_ ", ": ")).strip(" -")


def added(d):
    t = d.astimezone(TZ)
    return f"{t:%A, %B} {t.day}, {t:%Y} {int(t.strftime('%I'))}:{t:%M:%S %p}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--since", help="only highlights created on/after this date (YYYY-MM-DD)")
    ap.add_argument("--lang", choices=sorted(TEXTS), default="en", help="language of the Markdown export")
    ap.add_argument("--tz", help="time zone for dates, e.g. Europe/Paris (default: system)")
    args = ap.parse_args()
    global TZ
    if args.tz:
        TZ = ZoneInfo(args.tz)
    L = TEXTS[args.lang]
    docs = os.path.join(args.src, "documents")
    since = datetime.datetime.fromisoformat(args.since).replace(tzinfo=TZ) if args.since else None
    by_id, by_stem = index_books(docs)

    groups = {}
    for db in glob.glob(os.path.join(args.src, "**", "ksdk_annotation_v*.db"), recursive=True):
        from_db(db, by_id, by_stem, groups)
    from_sidecars(docs, by_stem, groups)

    # a book sent twice gets two IDs; if one copy's file is gone, resolve with the other copy
    sdr_stem = {}
    for d in glob.glob(os.path.join(docs, "**", "*.sdr"), recursive=True):
        st = os.path.basename(d)[:-4]
        m = re.search(r"_([A-Z0-9]{10}|[A-F0-9]{32}|[A-Z0-9]{32})$", st)
        if m:
            sdr_stem[m.group(1)] = st
    base = lambda st: re.sub(r"_([A-Z0-9]{10}|[A-F0-9]{32}|[A-Z0-9]{32})$", "", st)
    for g in groups.values():
        if g["path"] or not g["hint"]:
            continue
        st = sdr_stem.get(g["hint"].replace("id:", ""), g["hint"])
        g["hint"] = st
        twin = [p for s_, p in by_stem.items() if base(s_) == base(st)]
        if twin:
            g["path"], g["twin"] = twin[0], True
    merged = {}
    for g in groups.values():
        k = g["path"] or "hint:" + g["hint"]
        if k in merged:
            merged[k]["hl"].update({kk: v for kk, v in g["hl"].items() if kk not in merged[k]["hl"]})
            merged[k]["notes"] += [n for n in g["notes"] if not any(n[0] == x[0] for x in merged[k]["notes"])]
        else:
            merged[k] = g
    groups = merged

    books, report = [], []
    for g in groups.values():
        n = len(g["hl"])
        if since:
            g["hl"] = {k: v for k, v in g["hl"].items() if v >= since}
            g["notes"] = [x for x in g["notes"] if x[2] >= since]
        if not g["hl"] and not g["notes"]:
            continue
        if not g["path"]:
            report.append(f"MISSING    {n:4d} highlights  book file not on the Kindle: {g['hint']}")
            continue
        try:
            r = Resolver(g["path"])
        except Exception as e:
            why = "DRM (store purchase: Amazon already syncs these highlights)" if "DRM" in str(e) else f"{type(e).__name__}: {e}"
            report.append(f"UNREADABLE {n:4d} highlights  {why}: {os.path.basename(g['path'])}")
            continue
        items = [dict(start=a, end=z, text=r.get(a, z), created=w, note="") for (a, z), w in g["hl"].items()]
        items.sort(key=lambda h: h["start"])
        for a, body, w in g["notes"]:
            host = next((h for h in items if h["start"] <= a <= h["end"] + 1), None)
            if host:
                host["note"] = (host["note"] + " " + body).strip()
            else:
                items.append(dict(start=a, end=a, text="", created=w, note=body))
        # sanity check for a borrowed copy; one-position spans are highlighted images and have no text
        spans = [h for h in items if h["end"] > h["start"]]
        if g.get("twin") and sum(1 for h in spans if not h["text"]) > 0.1 * max(1, len(spans)):
            report.append(f"MISSING    {n:4d} highlights  book file not on the Kindle: {g['hint']}")
            continue
        items = sorted((h for h in items if h["text"] or h["note"]), key=lambda h: h["start"])
        fallback = os.path.splitext(os.path.basename(g["path"]))[0]
        fallback = re.sub(r"_[A-Z0-9]{10,32}$", "", fallback)
        author = tidy_author(r.author)
        title = tidy_title(r.title or fallback, author)
        books.append(dict(title=title, author=author, file=os.path.basename(g["path"]), items=items))
        report.append(f"OK         {sum(1 for h in items if h['text']):4d} highlights  "
                      f"{sum(1 for h in items if h['note'])} notes  {title} ({author})")

    os.makedirs(args.out, exist_ok=True)
    books.sort(key=lambda b: b["title"].lower())
    # My Clippings.txt, Kindle format (importable in Readwise > Import > Kindle)
    out = []
    for b in books:
        head = f"{b['title']} ({b['author']})"
        for h in b["items"]:
            loc, loc_end = h["start"] // 150 + 1, h["end"] // 150 + 1
            span = f"{loc}-{loc_end}" if loc_end > loc else str(loc)
            if h["text"]:
                out.append(f"{head}\n- Your Highlight on Location {span} | Added on {added(h['created'])}\n\n{h['text']}\n==========")
            if h["note"]:
                out.append(f"{head}\n- Your Note on Location {loc_end} | Added on {added(h['created'])}\n\n{h['note']}\n==========")
    open(os.path.join(args.out, "My Clippings.txt"), "w", encoding="utf-8-sig").write("\n".join(out) + "\n")
    # Markdown
    md = ["# " + L["title"], "", L["recovered"].format(d=datetime.date.today()), ""]
    for b in books:
        n = sum(1 for h in b["items"] if h["text"])
        md += [f"## {b['title']}", "", f"*{b['author']}* · " + L["count"].format(n=n), ""]
        for h in b["items"]:
            if h["text"]:
                md.append(f"> {h['text']}")
            if h["note"]:
                md += ["", f"{L['note']} {h['note']}"]
            md.append("\n<sub>" + L["loc"].format(l=h["start"] // 150 + 1, d=h["created"].astimezone(TZ)) + "</sub>\n")
    open(os.path.join(args.out, L["md_file"]), "w", encoding="utf-8").write("\n".join(md))
    # JSON (for pushing to Readwise)
    for b in books:
        for h in b["items"]:
            h["location"] = h["start"] // 150 + 1
            h["created"] = h["created"].isoformat()
    json.dump(books, open(os.path.join(args.out, "highlights.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(args.out, "report.txt"), "w").write("\n".join(sorted(report)) + "\n")
    print("\n".join(sorted(report)))


if __name__ == "__main__":
    main()
