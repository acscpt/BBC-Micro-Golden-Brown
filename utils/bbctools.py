#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BBC-Micro-Golden-Brown contributors
# SPDX-License-Identifier: MIT

"""
bbctools - List and extract files from BBC Micro DFS disc images.

Supports .ssd (single-sided) and .dsd (double-sided interleaved) formats.
BBC BASIC programs are detokenized to produce LIST-style plain text output.
Binary files are extracted as raw bytes with load/exec metadata reported.

Usage:
    bbctools.py cat  <image>                       List disc catalogue
    bbctools.py extract <image> <filename> [-o F]  Extract one file
    bbctools.py extract <image> "*" [-d DIR]       Extract all files
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# BBC BASIC II token table (extracted from BASIC2.rom)
# ---------------------------------------------------------------------------

TOKENS = {
    0x80: "AND",       0x81: "DIV",       0x82: "EOR",       0x83: "MOD",
    0x84: "OR",        0x85: "ERROR",     0x86: "LINE",      0x87: "OFF",
    0x88: "STEP",      0x89: "SPC",       0x8A: "TAB(",      0x8B: "ELSE",
    0x8C: "THEN",
    # 0x8D = inline encoded line number (3 data bytes follow)
    0x8E: "OPENIN",    0x8F: "PTR",       0x90: "PAGE",      0x91: "TIME",
    0x92: "LOMEM",     0x93: "HIMEM",     0x94: "ABS",       0x95: "ACS",
    0x96: "ADVAL",     0x97: "ASC",       0x98: "ASN",       0x99: "ATN",
    0x9A: "BGET",      0x9B: "COS",       0x9C: "COUNT",     0x9D: "DEG",
    0x9E: "ERL",       0x9F: "ERR",       0xA0: "EVAL",      0xA1: "EXP",
    0xA2: "EXT",       0xA3: "FALSE",     0xA4: "FN",        0xA5: "GET",
    0xA6: "INKEY",     0xA7: "INSTR(",    0xA8: "INT",       0xA9: "LEN",
    0xAA: "LN",        0xAB: "LOG",       0xAC: "NOT",       0xAD: "OPENUP",
    0xAE: "OPENOUT",   0xAF: "PI",        0xB0: "POINT(",    0xB1: "POS",
    0xB2: "RAD",       0xB3: "RND",       0xB4: "SGN",       0xB5: "SIN",
    0xB6: "SQR",       0xB7: "TAN",       0xB8: "TO",        0xB9: "TRUE",
    0xBA: "USR",       0xBB: "VAL",       0xBC: "VPOS",      0xBD: "CHR$",
    0xBE: "GET$",      0xBF: "INKEY$",    0xC0: "LEFT$(",    0xC1: "MID$(",
    0xC2: "RIGHT$(",   0xC3: "STR$",      0xC4: "STRING$(",  0xC5: "EOF",
    0xC6: "AUTO",      0xC7: "DELETE",    0xC8: "LOAD",      0xC9: "LIST",
    0xCA: "NEW",       0xCB: "OLD",       0xCC: "RENUMBER",  0xCD: "SAVE",
    0xCF: "PTR",       0xD0: "PAGE",      0xD1: "TIME",      0xD2: "LOMEM",
    0xD3: "HIMEM",     0xD4: "SOUND",     0xD5: "BPUT",      0xD6: "CALL",
    0xD7: "CHAIN",     0xD8: "CLEAR",     0xD9: "CLOSE",     0xDA: "CLG",
    0xDB: "CLS",       0xDC: "DATA",      0xDD: "DEF",       0xDE: "DIM",
    0xDF: "DRAW",      0xE0: "END",       0xE1: "ENDPROC",   0xE2: "ENVELOPE",
    0xE3: "FOR",       0xE4: "GOSUB",     0xE5: "GOTO",      0xE6: "GCOL",
    0xE7: "IF",        0xE8: "INPUT",     0xE9: "LET",       0xEA: "LOCAL",
    0xEB: "MODE",      0xEC: "MOVE",      0xED: "NEXT",      0xEE: "ON",
    0xEF: "VDU",       0xF0: "PLOT",      0xF1: "PRINT",     0xF2: "PROC",
    0xF3: "READ",      0xF4: "REM",       0xF5: "REPEAT",    0xF6: "REPORT",
    0xF7: "RESTORE",   0xF8: "RETURN",    0xF9: "RUN",       0xFA: "STOP",
    0xFB: "COLOUR",    0xFC: "TRACE",     0xFD: "UNTIL",     0xFE: "WIDTH",
    0xFF: "OSCLI",
}

# Tokens where the rest of the line is literal text (not tokenized).
LINE_LITERAL_TOKENS = {0xDC, 0xF4}  # DATA, REM

# ---------------------------------------------------------------------------
# Inline line-number decoding (0x8D prefix, 3 data bytes)
# ---------------------------------------------------------------------------

def decodeLineRef(b0, b1, b2):
    """Decode a BBC BASIC inline line-number reference.

    Args:
        b0: Control byte that stores encoded high bits for the line number.
        b1: Encoded low byte payload.
        b2: Encoded high byte payload.

    The encoding XORs the top two bits of each byte of the 16-bit line
    number into a single control byte, with the sentinel value 0x54.

    Returns:
        Decoded BBC BASIC line number as an integer.
    """
    x = b0 ^ 0x54
    lo = (b1 & 0x3F) | ((x & 0x30) << 2)
    hi = (b2 & 0x3F) | ((x & 0x0C) << 4)
    return hi * 256 + lo

# ---------------------------------------------------------------------------
# BASIC detokenizer
# ---------------------------------------------------------------------------

def detokenize(data):
    """Convert a tokenized BBC BASIC program to LIST-style text lines.

    Args:
        data: Raw bytes for a tokenized BBC BASIC program.

    Returns a list of strings, one per program line.
    """
    # Collect each decoded BASIC line in LIST output format.
    lines = []
    pos = 0

    # Walk the tokenized program line-by-line until end marker or malformed data.
    while pos < len(data):
        if data[pos] != 0x0D:
            break

        # Step past the line marker and verify there is enough data remaining.
        pos += 1
        if pos >= len(data):
            break

        # Read line header fields: number and encoded line length.
        hi = data[pos]
        if hi == 0xFF:
            break

        lo = data[pos + 1]
        linenum = hi * 256 + lo
        linelen = data[pos + 2]

        # Slice out line body bytes and advance to the next line record.
        # Line content runs from pos+3 to pos+linelen-1 (last byte is 0x0D).
        content = data[pos + 3 : pos - 1 + linelen]
        pos = pos - 1 + linelen

        # Decode token bytes and format as a LIST-style text line.
        text = _decodeLineContent(content)
        lines.append(f"{linenum:>5d}{text}")

    return lines


def _decodeLineContent(content):
    """Decode token bytes for one BASIC line into LIST text.

    Args:
        content: Tokenized bytes for one line body (without line header).

    Returns:
        Decoded line text.
    """
    parts = []
    i = 0
    in_string = False
    literal_rest = False

    while i < len(content):
        b = content[i]

        # Inside a quoted string - emit raw characters, no token expansion.
        if in_string:
            if b == 0x22:  # closing quote
                in_string = False
                parts.append('"')
            elif 0x20 <= b <= 0x7E:
                parts.append(chr(b))
            else:
                parts.append(f"CHR$({b})" if b < 0x20 or b == 0x7F else chr(b))
            i += 1
            continue

        # After DATA or REM the rest of the line is literal.
        if literal_rest:
            if 0x20 <= b <= 0x7E:
                parts.append(chr(b))
            else:
                parts.append(chr(b))
            i += 1
            continue

        # Opening quote.
        if b == 0x22:
            in_string = True
            parts.append('"')
            i += 1
            continue

        # Inline encoded line number.
        if b == 0x8D:
            if i + 3 < len(content):
                target = decodeLineRef(content[i + 1], content[i + 2],
                                         content[i + 3])
                parts.append(str(target))
                i += 4
            else:
                parts.append("?")
                i += 1
            continue

        # Token byte.
        if b >= 0x80:
            keyword = TOKENS.get(b)
            if keyword is not None:
                parts.append(keyword)
                if b in LINE_LITERAL_TOKENS:
                    literal_rest = True
            else:
                # Unknown token - emit hex escape.
                parts.append(f"[&{b:02X}]")
            i += 1
            continue

        # Plain ASCII.
        if 0x20 <= b <= 0x7E:
            parts.append(chr(b))
        elif b == 0x0D:
            break
        else:
            # Control character - leave as-is for now.
            parts.append(chr(b))
        i += 1

    return "".join(parts)

# ---------------------------------------------------------------------------
# BASIC pretty-printer (post-processes detokenized text lines)
# ---------------------------------------------------------------------------

def prettyPrint(lines):
    """Apply readable spacing to detokenized BASIC lines.

    This is a post-processing pass on plain text, equivalent to what a
    sed/regex pipeline would do but with proper string-literal awareness.
    String literals and REM/DATA tails are never altered.

    Args:
        lines: List of detokenized BASIC line strings.

    Returns:
        List of prettified line strings.
    """
    result = []
    for line in lines:
        # Detokenized lines start with a right-justified line number.
        m = re.match(r'^(\s*\d+)(.*)', line)
        if not m:
            result.append(line)
            continue

        num_part = m.group(1)
        code = m.group(2)

        # Convert *| MOS comment syntax to REM, stripping any control
        # characters (e.g. VDU 21 anti-listing traps) from the tail.
        stripped = code.lstrip()
        if stripped.startswith('*|'):
            rest = stripped[2:]
            rest = ''.join(c for c in rest if ord(c) >= 32)
            code = ' REM *|' + rest

        # Ensure exactly one space between line number and first token.
        if code and not code[0].isspace():
            code = ' ' + code

        result.append(num_part + _prettyCode(code))
    return result


def _prettyCode(code):
    """Format the code portion of one BASIC line.

    Walks character by character so quoted strings and REM/DATA tails
    are passed through verbatim.  Outside those regions, spaces are
    normalised around operators and commas.

    Args:
        code: The code portion of a detokenized BASIC line (no line number).

    Returns:
        Formatted code string.
    """
    buf = []
    i = 0
    n = len(code)
    in_string = False
    literal_rest = False

    while i < n:
        ch = code[i]

        # Inside a quoted string - pass through verbatim until closing quote.
        if in_string:
            buf.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue

        # After REM or DATA - remainder of line is literal, pass through.
        if literal_rest:
            buf.append(ch)
            i += 1
            continue

        # Opening quote.
        if ch == '"':
            in_string = True
            buf.append(ch)
            i += 1
            continue

        # Detect REM or DATA keywords which mark the rest of the line as literal.
        triggered = False
        for kw in ('REM', 'DATA'):
            kl = len(kw)
            if code[i:i + kl] == kw:
                # Confirm not part of a longer identifier.
                after = i + kl
                if after >= n or not code[after].isalpha():
                    buf.append(kw)
                    i += kl
                    literal_rest = True
                    triggered = True
                    break
        if triggered:
            continue

        # Two-character comparison operators - must be checked before single-char.
        two = code[i:i + 2]
        if two in ('<>', '<=', '>='):
            _ensureSpace(buf)
            buf.append(two)
            buf.append(' ')
            i += 2
            while i < n and code[i] == ' ':
                i += 1
            continue

        # Single-character comparison and assignment operators.
        if ch in ('=', '<', '>'):
            _ensureSpace(buf)
            buf.append(ch)
            buf.append(' ')
            i += 1
            while i < n and code[i] == ' ':
                i += 1
            continue

        # Star command - * at the start of a statement passes the rest of
        # the line to the MOS command interpreter verbatim.  Do not add
        # spaces; mark remainder as literal.
        if ch == '*':
            prev = ''.join(buf).rstrip()
            if not prev or prev[-1] == ':':
                buf.append('*')
                i += 1
                literal_rest = True
                continue

        # Arithmetic operators - treat +/- as unary when following ( , : or operator.
        if ch in ('+', '-', '*', '/'):
            prev = ''.join(buf).rstrip()
            is_unary = ch in ('+', '-') and (not prev or prev[-1] in '(,:+-*/=')
            if is_unary:
                buf.append(ch)
            else:
                _ensureSpace(buf)
                buf.append(ch)
                buf.append(' ')
                while i + 1 < n and code[i + 1] == ' ':
                    i += 1
            i += 1
            continue

        # Colon statement separator - pad to ` : ` on both sides.
        if ch == ':':
            while buf and buf[-1] == ' ':
                buf.pop()
            buf.append(' : ')
            i += 1
            while i < n and code[i] == ' ':
                i += 1
            continue

        # Comma - normalise to exactly one following space, no leading space.
        if ch == ',':
            while buf and buf[-1] == ' ':
                buf.pop()
            buf.append(', ')
            i += 1
            while i < n and code[i] == ' ':
                i += 1
            continue

        buf.append(ch)
        i += 1

    # Collapse any double spaces introduced by adjacent padding operations,
    # but only outside strings and literal tails (which are already done).
    return re.sub(r'  +', ' ', ''.join(buf))


def _ensureSpace(buf):
    """Trim trailing spaces from buf then append exactly one space."""
    while buf and buf[-1] == ' ':
        buf.pop()
    buf.append(' ')

# ---------------------------------------------------------------------------
# DFS disc image handling
# ---------------------------------------------------------------------------

SECTOR_SIZE = 256
SECTORS_PER_TRACK = 10


def _dsdSectorOffset(track, side, sector):
    """Calculate byte offset for a sector in a .dsd image.

    Args:
        track: Track number.
        side: Side number (0 or 1).
        sector: Sector number within the track.

    Returns:
        Byte offset for the requested sector.
    """
    return (track * 20 + side * 10 + sector) * SECTOR_SIZE


def _ssdSectorOffset(sector):
    """Calculate byte offset for a sector in a .ssd image.

    Args:
        sector: Logical sector number.

    Returns:
        Byte offset for the requested sector.
    """
    return sector * SECTOR_SIZE


class DFSDisc:
    """Represents one side of a DFS disc image."""

    def __init__(self, image_data, side, is_dsd):
        """Create a DFS disc-side reader.

        Args:
            image_data: Full disc image bytes.
            side: Disc side number represented by this instance.
            is_dsd: True when image is .dsd interleaved format.
        """
        self.image = image_data
        self.side = side
        self.is_dsd = is_dsd

    def _readSector(self, sector_num):
        """Read one DFS logical sector from this side.

        Args:
            sector_num: Logical sector number on this side.

        Returns:
            256-byte sector payload.
        """
        track = sector_num // SECTORS_PER_TRACK
        sector_in_track = sector_num % SECTORS_PER_TRACK

        if self.is_dsd:
            off = _dsdSectorOffset(track, self.side, sector_in_track)
        else:
            off = _ssdSectorOffset(sector_num)

        return self.image[off : off + SECTOR_SIZE]

    def readCatalogue(self):
        """Parse the DFS catalogue and return a list of file entries.

        Args:
            None.

        Each entry is a dict with keys:
            name, dir, load, exec, length, start_sector, locked

        Returns:
            Tuple of (disc title, list of parsed entry dictionaries).
        """
        # Read the two catalogue sectors from track 0.
        sec0 = self._readSector(0)
        sec1 = self._readSector(1)

        # Disc title (first 8 chars in sec0[0:8], next 4 in sec1[0:4]).
        title = (bytes(sec0[0:8]) + bytes(sec1[0:4])).decode(
            "ascii",
            errors="replace").rstrip("\x00 ")

        # DFS stores one file record in 8-byte blocks.
        file_count = sec1[5] // 8
        entries = []

        for i in range(file_count):
            base0 = 8 + i * 8
            base1 = 8 + i * 8

            # Name (7 bytes) and directory byte (top bit = locked).
            raw_name = bytes(sec0[base0 : base0 + 7])
            dir_byte = sec0[base0 + 7]
            locked = bool(dir_byte & 0x80)
            directory = chr(dir_byte & 0x7F)
            name = raw_name.decode("ascii", errors="replace").rstrip()

            # Decode packed metadata from sector 1.
            load_lo = sec1[base1] | (sec1[base1 + 1] << 8)
            exec_lo = sec1[base1 + 2] | (sec1[base1 + 3] << 8)
            length_lo = sec1[base1 + 4] | (sec1[base1 + 5] << 8)
            extra = sec1[base1 + 6]
            start_sector = sec1[base1 + 7] | ((extra & 0x03) << 8)

            load_hi = (extra >> 2) & 0x03
            length_hi = (extra >> 4) & 0x03
            exec_hi = (extra >> 6) & 0x03

            load = load_lo | (load_hi << 16)
            exec_ = exec_lo | (exec_hi << 16)
            length = length_lo | (length_hi << 16)

            entries.append({
                "name": name,
                "dir": directory,
                "load": load,
                "exec": exec_,
                "length": length,
                "start_sector": start_sector,
                "locked": locked,
            })

        return title, entries

    def readFile(self, entry):
        """Read raw bytes for one catalogued DFS file.

        Args:
            entry: Catalogue entry dictionary returned by readCatalogue().

        Returns:
            File bytes truncated to the recorded file length.
        """
        start = entry["start_sector"]
        length = entry["length"]
        sectors_needed = (length + SECTOR_SIZE - 1) // SECTOR_SIZE

        data = bytearray()
        for s in range(sectors_needed):
            data.extend(self._readSector(start + s))

        return bytes(data[:length])


def openDiscImage(path):
    """Open a disc image and build DFS side readers.

    Args:
        path: Path to .ssd or .dsd disc image.

    Returns:
        List of DFSDisc instances, one per available side.
    """
    with open(path, "rb") as f:
        image = f.read()

    # Infer format from file extension.
    ext = path.lower()
    is_dsd = ext.endswith(".dsd")

    sides = []
    sides.append(DFSDisc(image, 0, is_dsd))

    if is_dsd:
        # A valid .dsd must have at least 20 sectors (2 sides x 1 track).
        if len(image) >= 20 * SECTOR_SIZE:
            sides.append(DFSDisc(image, 1, is_dsd))

    return sides

# ---------------------------------------------------------------------------
# File-type detection
# ---------------------------------------------------------------------------

def isBasic(entry):
    """Heuristic: a BBC BASIC program has load address 0xFFxxxx00 and
    exec address 0xFF8023 (or close variants), and starts with 0x0D.

    Args:
        entry: Catalogue entry dictionary.

    Returns:
        True if the entry looks like a BASIC program, else False.
    """
    exec_ = entry["exec"]
    # Typical BASIC load addresses: 0x000E00, 0x001900, 0x030E00, 0x031900
    # Typical BASIC exec: 0x00802B, 0x03802B
    # More reliable: exec & 0xFFFF == 0x802B or exec & 0xFFFF == 0x8023
    exec_lo = exec_ & 0xFFFF
    return exec_lo in (0x8023, 0x802B)


def looksLikeText(data):
    """Check whether file bytes look like tokenized BASIC.

    Args:
        data: Raw file bytes.

    Returns:
        True when data starts with the BASIC line marker 0x0D.
    """
    return len(data) > 0 and data[0] == 0x0D


def sortCatalogueEntries(entries, sortMode):
    """Return catalogue entries in the requested output order.

    Args:
        entries: List of catalogue entry dictionaries.
        sortMode: Sorting mode: name, catalog, or size.

    sortMode values:
        name    - sort by bare filename (default)
        catalog - preserve on-disc DFS catalogue order
        size    - sort by file length (ascending)

    Returns:
        Ordered list of catalogue entries.
    """
    if sortMode == "catalog":
        # Keep the original DFS catalogue slot order.
        return entries

    if sortMode == "size":
        # Secondary keys provide deterministic ordering for equal sizes.
        return sorted(
            entries,
            key=lambda e: (e["length"], e["name"].upper(), e["dir"].upper()),
        )

    # Default behavior: sort by the bare filename, ignoring directory prefix.
    return sorted(entries, key=lambda e: (e["name"].upper(), e["dir"].upper()))

# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmdCat(args):
    """Print the disc catalogue.

    Args:
        args: Parsed command-line arguments for the cat subcommand.
    """
    sides = openDiscImage(args.image)

    for disc in sides:
        title, entries = disc.readCatalogue()
        side_label = f"Side {disc.side}"
        header = f"--- {side_label}"

        if title:
            header += f": {title}"

        header += f" ({len(entries)} files) ---"
        print(header)
        print()

        if not entries:
            print("  (empty)")
        else:
            orderedEntries = sortCatalogueEntries(entries, args.sort)
            print(f"  {'Name':<12s} {'Load':>8s} {'Exec':>8s} {'Length':>8s}  {'Type'}")

            for e in orderedEntries:
                ftype = "BASIC" if isBasic(e) else ""
                lock = "L" if e["locked"] else " "
                full_name = f"{e['dir']}.{e['name']}"
                print(
                    f"  {lock}{full_name:<11s} "
                    f"{e['load']:08X} "
                    f"{e['exec']:08X} "
                    f"{e['length']:08X}  "
                    f"{ftype}"
                )
        print()


def _extractAll(args):
    """Extract every file from a disc image into a directory.

    BASIC programs are saved as .bas plain text.
    Binary files are saved as .bin raw bytes.
    Load/exec addresses for binary files are printed to stdout.

    Args:
        args: Parsed command-line arguments for the extract subcommand.
    """
    sides = openDiscImage(args.image)

    # Default output directory is the image filename stem (e.g. disc39 for disc39.dsd).
    if args.dir:
        out_dir = args.dir
    else:
        out_dir = os.path.splitext(os.path.basename(args.image))[0]

    os.makedirs(out_dir, exist_ok=True)

    # When the image has two sides we prefix each filename with the side number
    # to avoid collisions between identically-named files on different sides.
    multi_side = len(sides) > 1

    for disc in sides:
        _title, entries = disc.readCatalogue()

        for entry in entries:
            # Build a safe output filename from the DFS dir.name pair.
            base = f"{entry['dir']}.{entry['name']}"
            if multi_side:
                base = f"side{disc.side}_{base}"

            data = disc.readFile(entry)

            if isBasic(entry) and looksLikeText(data):
                # Detokenize BASIC and write as plain text.
                out_path = os.path.join(out_dir, base + ".bas")
                text_lines = detokenize(data)
                if args.pretty:
                    text_lines = prettyPrint(text_lines)
                with open(out_path, "w", encoding="ascii", errors="replace") as f:
                    f.write("\n".join(text_lines) + "\n")
                print(f"  BASIC   {out_path}")

            else:
                # Write binary file and report addressing metadata.
                out_path = os.path.join(out_dir, base + ".bin")
                with open(out_path, "wb") as f:
                    f.write(data)
                print(
                    f"  binary  {out_path}  "
                    f"load=0x{entry['load']:06X}  "
                    f"exec=0x{entry['exec']:06X}  "
                    f"length={entry['length']} bytes"
                )


def cmdExtract(args):
    """Extract a file (or all files) from the disc image.

    Use -a/--all to extract everything into a directory.
    BASIC programs are detokenized to LIST-style plain text.
    Binary files are written as raw bytes, with load/exec addresses reported.

    Args:
        args: Parsed command-line arguments for the extract subcommand.
    """
    # --all: route to the bulk extractor.
    if args.all:
        if args.output:
            print("Error: -o/--output cannot be used with -a/--all. Use -d/--dir instead.",
                  file=sys.stderr)
            sys.exit(1)
        _extractAll(args)
        return

    if not args.filename:
        print("Error: filename required unless -a/--all is specified.", file=sys.stderr)
        sys.exit(1)
    sides = openDiscImage(args.image)

    # Parse requested filename. Accept either D.NAME or bare NAME.
    # For bare NAME we infer the directory only when the match is unique.
    target = args.filename

    if len(target) >= 3 and target[1] == ".":
        target_dir = target[0].upper()
        target_name = target[2:]

        # Search all sides for an exact directory + filename match.
        found = None

        for disc in sides:
            _title, entries = disc.readCatalogue()

            for e in entries:
                if e["dir"].upper() == target_dir and e["name"].upper() == target_name.upper():
                    found = (disc, e)
                    break

            if found:
                break
    else:
        # Collect every matching bare filename across all sides and directories.
        target_name = target
        matches = []

        for disc in sides:
            _title, entries = disc.readCatalogue()

            for e in entries:
                if e["name"].upper() == target_name.upper():
                    matches.append((disc, e))

        if len(matches) == 1:
            found = matches[0]
        elif len(matches) > 1:
            print(
                f"Ambiguous filename '{target_name}' - specify exactly with directory prefix.",
                file=sys.stderr,
            )

            for disc, entry in matches:
                print(f"  Side {disc.side}: {entry['dir']}.{entry['name']}", file=sys.stderr)

            sys.exit(1)
        else:
            found = None

    if not found:
        print(f"File not found: {target}", file=sys.stderr)
        sys.exit(1)

    disc, entry = found
    data = disc.readFile(entry)
    full_name = f"{entry['dir']}.{entry['name']}"

    if isBasic(entry) and looksLikeText(data):
        # Detokenize the BASIC program and emit as LIST-style text.
        text_lines = detokenize(data)
        if args.pretty:
            text_lines = prettyPrint(text_lines)
        output = "\n".join(text_lines) + "\n"

        if args.output:
            with open(args.output, "w", encoding="ascii", errors="replace") as f:
                f.write(output)
            print(f"Extracted to {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(output)

    else:
        # Binary file - write raw bytes.
        if args.output:
            with open(args.output, "wb") as f:
                f.write(data)

            # Report addressing metadata to stdout alongside the confirmation so
            # the caller has what they need to set the base address in a disassembler.
            print(f"Extracted to {args.output}")
            print(
                f"{full_name}  "
                f"load=0x{entry['load']:06X}  "
                f"exec=0x{entry['exec']:06X}  "
                f"length={entry['length']} bytes"
            )
        else:
            # Raw bytes go directly to stdout - useful for piping to a disassembler.
            # Metadata is omitted here because it would corrupt the binary stream.
            sys.stdout.buffer.write(data)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.

    Args:
        None.
    """
    parser = argparse.ArgumentParser(
        description="BBC Micro DFS disc image tool",
    )
    sub = parser.add_subparsers(dest="command")

    p_cat = sub.add_parser("cat", help="List disc catalogue")
    p_cat.add_argument("image", help="Path to .ssd or .dsd disc image")
    p_cat.add_argument(
        "-s",
        "--sort",
        choices=["name", "catalog", "size"],
        default="name",
        help="Sort order: name (default), catalog, or size",
    )

    p_extract = sub.add_parser("extract", help="Extract a file, or all files with -a")
    p_extract.add_argument("image", help="Path to .ssd or .dsd disc image")
    p_extract.add_argument("filename", nargs="?", help="DFS filename, e.g. T.MYPROG or MYPROG")
    p_extract.add_argument("-a", "--all", action="store_true", help="Extract all files")
    p_extract.add_argument("-o", "--output", help="Write single file to this path instead of stdout")
    p_extract.add_argument("-d", "--dir", help="Output directory for -a/--all (default: image name)")
    p_extract.add_argument("--pretty", action="store_true",
                           help="Add spaces around operators for readability (BASIC only)")

    args = parser.parse_args()

    if args.command == "cat":
        cmdCat(args)
    elif args.command == "extract":
        cmdExtract(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
