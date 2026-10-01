"""Assemble a KF8 (azw3) book's text in reading order, as the Kindle counts positions."""
import sys, io, contextlib

from lib.mobi_sectioner import Sectionizer
from lib.mobi_header import MobiHeader
from lib.mobi_k8proc import K8Processor

K8_BOUNDARY = b"BOUNDARY"

class _Files:  # K8Processor only needs a few attributes when not dumping
    outdir = k8dir = '/tmp'
    def getInputFileBasename(self): return 'book'

def assembled_text(path):
    with contextlib.redirect_stdout(io.StringIO()):
        sect = Sectionizer(path)
        mh = MobiHeader(sect, 0)
        if not mh.isK8():
            for i in range(len(sect.sectionoffsets) - 1):
                a, b = sect.sectionoffsets[i:i + 2]
                if b - a == 8 and sect.loadSection(i) == K8_BOUNDARY:
                    mh = MobiHeader(sect, i + 1)
                    break
        raw = mh.getRawML()
        k = K8Processor(mh, sect, _Files())
        k.buildParts(raw)
    return b''.join(k.parts)
