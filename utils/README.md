# bbctools Utility

`bbctools.py` is a small command line utility for working with BBC Micro DFS disc images.

It supports:

- Listing DFS catalogues from `.ssd` and `.dsd` images
- Extracting a single file (BASIC or binary) by name
- Extracting all files from a disc image at once with `-a`

## Location

- Script: `bbctools.py`

## Commands

### `cat`

List catalogue entries on each side of the image.

```bash
python3 bbctools.py cat <image>
```

Examples:

```bash
python3 bbctools.py cat /path/to/disc.dsd
python3 bbctools.py cat /path/to/disc.ssd
```

#### Sort options

`cat` supports `-sort` / `--sort`:

- `name` (default): sort by bare filename (ignores directory prefix)
- `catalog`: preserve original DFS catalogue order
- `size`: sort by file length ascending

Examples:

```bash
python3 bbctools.py cat /path/to/disc.dsd --sort name
python3 bbctools.py cat /path/to/disc.dsd --sort catalog
python3 bbctools.py cat /path/to/disc.dsd --sort size
```

### `extract`

Extract a single file from the disc image.

```bash
python3 bbctools.py extract <image> <filename>
```

You can write output to a file instead of stdout:

```bash
python3 bbctools.py extract <image> <filename> -o output.bas
python3 bbctools.py extract <image> <filename> -o output.bin
```

BBC BASIC programs are automatically detected and detokenized to plain LIST-style text.
All other files are extracted as raw bytes.  When writing to a file with `-o`, the load
address, exec address, and file length are also printed so you have the information
needed to set the base address in a disassembler.

Example output when extracting a binary file with `-o`:

```text
Extracted to output.bin
$.LOADER  load=0x001900  exec=0x001900  length=512 bytes
```

When no `-o` is given, raw bytes are written directly to stdout for piping to a
disassembler without any additional output.

#### Extract all files

Use `-a` / `--all` to extract every file on the disc in one operation:

```bash
python3 bbctools.py extract <image> -a
```

By default the files are written into a directory named after the image (e.g. `bbc39/`
for `bbc39.dsd`).  Use `-d` / `--dir` to specify a different location:

```bash
python3 bbctools.py extract <image> -a -d output/
```

For each file extracted:
- BASIC programs are saved as `{dir}.{name}.bas` (detokenized plain text)
- Binary files are saved as `{dir}.{name}.bin` with load/exec/length printed to stdout

On a `.dsd` image with two sides, files from each side are prefixed with `side0_` or
`side1_` to avoid name collisions between identically-named files on different sides.

## Filename matching rules

`extract` accepts either:

- Explicit DFS name: `D.NAME` (for example `T.GOLDENB`, `$.MENU`)
- Bare name: `NAME` (for example `GOLDENB`)

When a bare name is used:

- If there is exactly one match across all sides and directories, it is used
- If there are multiple matches, the tool stops and reports an ambiguity error
- If there is no match, the tool reports file not found

Example ambiguity output:

```text
Ambiguous filename 'SCUMPI' - specify exactly with directory prefix.
  Side 0: $.SCUMPI
  Side 1: $.SCUMPI
```

## File type detection

A file is treated as BBC BASIC when it matches BASIC execution metadata and starts with the
tokenized line marker byte.  All other files are extracted as raw bytes.

## Pretty-printing

Add `--pretty` to any `extract` command to apply readable spacing to BASIC output:

- A space is inserted between the line number and the first token
- `=`, `<`, `>`, `<>`, `<=`, `>=` are surrounded by spaces
- `*`, `/`, `+`, `-` are surrounded by spaces (unary `+`/`-` after `(` or `,` are left alone)
- `:` statement separators are padded to ` : `
- `,` is normalised to `, ` with no leading space
- String literals, `REM` tails, and `DATA` tails are never touched
- Star commands (`*COMMAND`) are passed through verbatim - no spaces are inserted
- `*|` anti-listing traps are converted to `REM *|` and any control characters in
  the tail (e.g. `CHR$(21)` VDU-disable bytes) are stripped. This was a common
  copy-protection trick: placing `VDU 21` bytes after `*|` caused the screen to
  go blank when the program was LISTed, hiding the source code from casual inspection.

```bash
python3 bbctools.py extract disc.dsd T.GOLDENB --pretty
python3 bbctools.py extract disc.dsd -a --pretty -d output/
```

`--pretty` is silently ignored for binary files.

## Notes

- `.ssd` is treated as single sided
- `.dsd` is treated as interleaved double sided
- Inline BASIC line references (`0x8D` encoding) are decoded
- Output is intended to match BBC BASIC LIST style as closely as practical
