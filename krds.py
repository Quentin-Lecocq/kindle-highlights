"""Minimal generic parser for Kindle KRDS files (.azw3r, .yjr, .mbp1, ...).

Format (big-endian):
  8-byte signature, then a stream of typed values.
  type byte: 0 bool(1) | 1 int(4) | 2 long(8) | 3 utf | 4 double(8) | 5 short(2)
             6 float(4) | 7 byte(1) | 9 char(1) | 0xFE object begin | 0xFF object end
  utf: flag byte (1 = empty) then ushort length then bytes
  object: 0xFE, name (utf without type byte), values..., 0xFF
"""
import struct

SIG = b"\x00\x00\x00\x00\x00\x1a\xb1\x26"


class Obj:
    def __init__(self, name):
        self.name = name
        self.vals = []

    def __repr__(self):
        return f"Obj({self.name!r}, {self.vals!r})"


class Reader:
    def __init__(self, data):
        if not data.startswith(SIG):
            raise ValueError("not a KRDS file")
        self.d = data
        self.p = len(SIG)

    def take(self, n):
        b = self.d[self.p:self.p + n]
        if len(b) < n:
            raise EOFError
        self.p += n
        return b

    def utf(self):
        flag = self.take(1)[0]
        if flag == 1:
            return ""
        n = struct.unpack(">H", self.take(2))[0]
        return self.take(n).decode("utf-8", "replace")

    def value(self):
        t = self.take(1)[0]
        if t == 0:
            return bool(self.take(1)[0])
        if t == 1:
            return struct.unpack(">i", self.take(4))[0]
        if t == 2:
            return struct.unpack(">q", self.take(8))[0]
        if t == 3:
            return self.utf()
        if t == 4:
            return struct.unpack(">d", self.take(8))[0]
        if t == 5:
            return struct.unpack(">h", self.take(2))[0]
        if t == 6:
            return struct.unpack(">f", self.take(4))[0]
        if t == 7:
            return self.take(1)[0]
        if t == 9:
            return chr(self.take(1)[0])
        if t == 0xFE:
            o = Obj(self.utf())
            while self.d[self.p] != 0xFF:
                o.vals.append(self.value())
            self.p += 1
            return o
        raise ValueError(f"unknown type {t:#x} at {self.p - 1}")

    def all(self):
        out = []
        while self.p < len(self.d):
            out.append(self.value())
        return out


def parse(path):
    return Reader(open(path, "rb").read()).all()


def find(objs, name):
    """Yield every Obj with this name, recursively."""
    for o in objs:
        if isinstance(o, Obj):
            if o.name == name:
                yield o
            yield from find(o.vals, name)


if __name__ == "__main__":
    import sys, pprint
    pprint.pprint(parse(sys.argv[1]), width=160)
