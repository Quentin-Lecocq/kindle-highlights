"""Strip book markup from a slice of HTML and normalise whitespace."""
import html
import re

TAG = re.compile(rb"<[^>]*>")
BLOCK = re.compile(rb"</?(?:p|div|br|h[1-6]|li|ul|ol|blockquote|tr|td|section|aside)\b[^>]*>", re.I)


def clean(raw):
    raw = BLOCK.sub(b" ", raw)                      # block tags separate words
    raw = TAG.sub(b"", raw)                         # inline tags (spans, small caps) do not
    raw = re.sub(rb"<[^>]*$", b"", raw)             # tag cut at the end of the slice
    raw = re.sub(rb'^[^<>]*["=][^<>]*>', b"", raw)  # tag cut at the start of the slice
    text = html.unescape(raw.decode("utf-8", "ignore")).replace("­", "")
    return re.sub(r"\s+", " ", text).strip()
