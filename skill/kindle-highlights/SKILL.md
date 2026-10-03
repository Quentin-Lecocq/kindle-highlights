---
name: kindle-highlights
description: Recover Kindle highlights and notes when My Clippings.txt is missing (firmware 5.19+). Use when the user plugs in a Kindle, asks for their Kindle highlights, or mentions My Clippings.txt.
---

# Kindle highlights

Recover the highlights and notes stored on a Kindle e-reader and hand them to the user as text.

## What to know first

- Since firmware ~5.19 (summer 2026), Kindles no longer write `documents/My Clippings.txt`. Do not spend time looking for it.
- Highlights are stored as **positions only**, with no text, in two places:
  - `system/ksdk/.annotations/amzn1.account.<ID>/ksdk_annotation_v1.db` (SQLite, current firmware)
  - `documents/**/<book>.sdr/*.mbp1 | *.yjr | *.azw3r` (per-book sidecars, older firmware)
- The text is recovered from the **book file still on the Kindle**. If the user removed the book from the device, its highlights cannot be resolved until the book is downloaded again.
- Store purchases are DRM-protected. This tool does not read them and you must not try to remove DRM. Amazon already syncs those highlights to its cloud (and to services such as Readwise).
- The tool is `kindle_highlights.py`, in the repository this skill ships with: `https://github.com/Quentin-Lecocq/kindle-highlights`.

## Step 1: get a copy of the Kindle's files

You need two folders from the Kindle, copied side by side into one folder you can read: `documents` and `system/ksdk`.

1. Check with the user that the Kindle is plugged in **and unlocked** (a locked Kindle hides its storage), and that no other app is talking to it (only one MTP app can connect at a time).
2. By default, ask the user to copy the two folders and tell you where they put them:
   - macOS: Amazon's *USB File Manager* (installed with *Send to Kindle* for Mac) or OpenMTP, then drag both folders into a Finder folder.
   - Windows: the Kindle appears in File Explorer; copy both folders from there.
3. If you can control the user's desktop and they agree, you may do the drag yourself. Known pitfalls in USB File Manager:
   - Start the drag with a short **horizontal** move that stays on the same row. If the first move leaves the row, the neighbouring folder is dragged instead. Check the name of what arrived before continuing.
   - Clicking the name of an already selected row starts a rename. Press Return to leave it unchanged. Click the disclosure triangles and icons instead.
4. `system/ksdk` is small and must be copied every time, because it holds the new highlights. `documents` is large; an earlier copy can be reused as long as the user has not added or re-downloaded books since.

## Step 2: run the tool

1. If the repository is not already available, clone it: `git clone https://github.com/Quentin-Lecocq/kindle-highlights`
2. Install the dependencies once: `./setup.sh` (needs git, Python 3.9+ and network access to GitHub and PyPI).
3. Run:

   ```bash
   python3 kindle_highlights.py <copied folder> <output folder> [--since YYYY-MM-DD] [--lang en|fr] [--tz Area/City]
   ```

If you work in a remote sandbox rather than on the user's machine, bring the copy over as an archive and leave out the `.cache` folders.

## Step 3: read the report

`report.txt` has one line per book:

- `OK`: highlights resolved.
- `MISSING`: the book file is no longer on the Kindle. Tell the user which books to open on the Kindle so they download again, then repeat steps 1 and 2.
- `UNREADABLE ... DRM`: a store purchase. Nothing to do; Amazon syncs these.

A highlight placed on an image has no text and is left out.

## Step 4: deliver

- Give the user `My Clippings.txt` (classic Kindle format) and the Markdown export, and state how many highlights and notes were recovered per book, plus any `MISSING` books.
- **Readwise**: the simplest route is for the user to upload `My Clippings.txt` at readwise.io/import (Kindle, My Clippings). It keeps the highlight dates and Readwise removes duplicates.
- If a Readwise connector is available and the user asks you to send the highlights yourself, use `highlights.json`:
  - First check whether the book already exists in Readwise, and reuse its exact title, author **and source**. Books imported from a clippings file have the source `clippings`; a different source creates a second copy of the book.
  - Send in batches of about 60. Start with one highlight and confirm it landed in the existing book.
  - If a call fails without a message, retry without the date field: some connectors reject it.
  - Skip a highlight that is fully contained in a longer one.

## Privacy

The copied folders contain the user's books and an annotation database that includes their Amazon account ID and every highlight they made. Keep them on the user's machine or in your private workspace. Never commit, publish or share them, and do not paste book text beyond the highlights themselves.
