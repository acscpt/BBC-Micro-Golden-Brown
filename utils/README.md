# bbctools Utility

`bbctools.py` is a small command line utility for working with BBC Micro DFS disc images.

It supports:

- Listing DFS catalogues from `.ssd` and `.dsd` images
- Extracting BBC BASIC programs to plain text (LIST style)
- Warning when a file does not look like a BASIC program

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

Extract and detokenize one BASIC file.

```bash
python3 bbctools.py extract <image> <filename>
```

You can also write output to a file:

```bash
python3 bbctools.py extract <image> <filename> -o output.bas
```

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

## BASIC detection

A file is treated as BASIC when it matches BASIC-like execution metadata and tokenized content markers.
If the file does not look like BASIC, extraction is skipped with a warning.

## Notes

- `.ssd` is treated as single sided
- `.dsd` is treated as interleaved double sided
- Inline BASIC line references (`0x8D` encoding) are decoded
- Output is intended to match BBC BASIC LIST style as closely as practical
