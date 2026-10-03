# kindle-highlights

Recover your Kindle highlights and notes as text, even though recent Kindles no longer write `My Clippings.txt`.

## The problem

Since firmware ~5.19 (summer 2026), Kindle e-readers stopped writing `documents/My Clippings.txt`, the plain-text file every highlight tool relied on. Highlights are now stored as **positions only**, with no text:

- `system/ksdk/.annotations/amzn1.account.<ID>/ksdk_annotation_v1.db`: a SQLite database (current firmware)
- `documents/**/<book>.sdr/*.mbp1 | *.yjr | *.azw3r`: per-book sidecar files (older firmware)

Amazon only syncs highlights of **store purchases** to its cloud (and so to Readwise). Highlights in personal documents (Send to Kindle, Calibre, USB) never leave the device.

`kindle-highlights` reads both stores, then looks up each position in the book file still on the Kindle to recover the exact text.

## What it handles

| Book format | Typical source | Position means |
|---|---|---|
| KFX (`.kfx`) | Send to Kindle | kfxlib content position |
| KF8 (`.azw3`) | Calibre, USB | byte offset in the assembled (skeleton + fragment) text |
| MOBI7 (`.azw`, `.mobi`) | older Send to Kindle | byte offset in the uncompressed text |

Notes are attached to the highlight they belong to. A book sent twice (two IDs) is resolved with whichever copy is still on the device.

DRM-protected books are **not** decrypted: they are reported as unreadable and skipped. Their highlights are already synced by Amazon.

## Usage

1. Plug in the Kindle and **unlock it** (a locked Kindle hides its storage over USB).
2. Copy two folders from the Kindle to your computer: `documents` and `system/ksdk`.
   On macOS the Kindle uses MTP; Amazon's *USB File Manager* app (bundled with *Send to Kindle* for Mac) or [OpenMTP](https://openmtp.ganeshrvel.com) can do the copy.
3. Install the dependencies once:

   ```bash
   ./setup.sh
   ```

4. Run:

   ```bash
   python3 kindle_highlights.py <copied folder> <output folder> [--since 2026-10-01] [--lang en|fr] [--tz Europe/Paris]
   ```

Output:

- `My Clippings.txt`: classic Kindle format, importable in Readwise (*Import > Kindle*) and most highlight tools
- `Kindle Highlights.md`: one section per book
- `highlights.json`: structured data (title, author, text, note, location, date)
- `report.txt`: one line per book, `OK`, `MISSING` or `UNREADABLE`

## Use it with Claude (optional)

The [`skill/kindle-highlights`](skill/kindle-highlights/SKILL.md) folder is a ready-made skill: it teaches Claude the whole procedure, so you can plug in the Kindle and ask "get my Kindle highlights".

- **Claude Code**: copy the folder to `~/.claude/skills/kindle-highlights/`.
- **Claude app**: zip the `kindle-highlights` folder and add it in *Customize > Skills*.

Claude will ask you to copy the two folders from the Kindle (or do it itself if it can control your desktop), run the tool, and give you the export. With a Readwise connector it can also send the highlights straight to Readwise.

## Limitations

- **The book file must still be on the Kindle.** If you removed it, the highlight positions survive but the text cannot be recovered: the book is reported as `MISSING`. Download it again on the Kindle and re-run.
- Locations are approximate (`position / 150`), close to what the Kindle displays.
- Tested on a Kindle Paperwhite in October 2026. Amazon may move things again; if highlights stop appearing, look for a new database under `system/ksdk/`.

## Credits

- [KFX Input / kfxlib](https://github.com/kluyg/calibre-kfx-input) by John Howell (GPL v3), used to read KFX books
- [KindleUnpack](https://github.com/kevinhendricks/KindleUnpack) (GPL v3), used to reassemble KF8 books
- [KFX-Highlights](https://github.com/aakar/KFX-Highlights) by aakar, which documented the move to `ksdk_annotation_v1.db`

## License

GPL v3, see [LICENSE](LICENSE).
