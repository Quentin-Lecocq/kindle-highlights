"""Extract the raw (uncompressed) text of a DRM-free MOBI / AZW / AZW3 file."""
import struct


def palmdoc_decompress(data):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        i += 1
        if c == 0 or 9 <= c <= 0x7F:
            out.append(c)
        elif 1 <= c <= 8:
            out += data[i:i + c]
            i += c
        elif c >= 0xC0:
            out += b" " + bytes([c ^ 0x80])
        else:  # 0x80..0xBF: back-reference
            c = (c << 8) | data[i]
            i += 1
            dist = (c >> 3) & 0x7FF
            length = (c & 7) + 3
            for _ in range(length):
                out.append(out[-dist])
    return bytes(out)


def _trailing_size(rec, flags):
    size = 0
    end = len(rec)
    for bit in range(15, 0, -1):
        if flags & (1 << bit):
            # backward-encoded variable-width integer
            v = 0
            shift = 0
            pos = end - size - 1
            while True:
                b = rec[pos]
                v |= (b & 0x7F) << shift
                shift += 7
                if b & 0x80 or shift >= 28:
                    break
                pos -= 1
            size += v
    if flags & 1:
        size += (rec[end - size - 1] & 0x3) + 1
    return size


def raw_text(path, kf8=False):
    d = open(path, "rb").read()
    nrec = struct.unpack(">H", d[76:78])[0]
    offs = [struct.unpack(">I", d[78 + i * 8:82 + i * 8])[0] for i in range(nrec)] + [len(d)]

    def rec(i):
        return d[offs[i]:offs[i + 1]]

    base = 0
    r0 = rec(0)
    if kf8:
        # In a combined MOBI7/KF8 file the KF8 part starts after a BOUNDARY record.
        # EXTH 121 gives the KF8 header record index.
        hl = struct.unpack(">I", r0[20:24])[0]
        exth_flag = struct.unpack(">I", r0[0x80:0x84])[0]
        if exth_flag & 0x40:
            e = r0[16 + hl:]
            cnt = struct.unpack(">I", e[8:12])[0]
            p = 12
            for _ in range(cnt):
                t, l = struct.unpack(">II", e[p:p + 8])
                if t == 121:
                    base = struct.unpack(">I", e[p + 8:p + 12])[0]
                p += l
            if base == 0xFFFFFFFF:
                base = 0
        r0 = rec(base)
    comp, _, textlen, ntext, recsize = struct.unpack(">HHIHH", r0[:12])
    enc = struct.unpack(">H", r0[12:14])[0]
    if enc:
        raise ValueError("DRM-protected")
    hl = struct.unpack(">I", r0[20:24])[0]
    flags = 0
    if hl >= 0xE4:
        flags = struct.unpack(">H", r0[0xF2:0xF4])[0]
    out = bytearray()
    for i in range(1, ntext + 1):
        r = rec(base + i)
        r = r[:len(r) - _trailing_size(r, flags)]
        out += palmdoc_decompress(r) if comp == 2 else r
    return bytes(out[:textlen])
