# Golden Brown on the BBC Micro  -  A Technical Deep Dive

The BBC Micro was launched in December 1981 by Acorn Computers, developed in partnership with the BBC for their *Computer Literacy Project*. It had a 2MHz 6502 processor, 32KB of RAM as standard, a full-travel keyboard, and a documented operating system with published OS entry points and a mapped memory layout.

BBC BASIC, written by Sophie Wilson, was the language that came with it - and it offered features that most contemporary home computer BASICs did not:

- `SOUND` command driving the SN76489 sound chip with 3 tone + 1 noise channels.
- `ENVELOPE` command for per-channel amplitude and pitch shaping, running at interrupt level.
- A `TIME` hardware centisecond counter for real-time timing from BASIC.
- Direct memory access: `?addr` (single byte) and `!addr` (32-bit word).
- `INSTR()` for substring search - crucial to the encoding scheme here.
- `MID$()`, `LEFT$()`, `RIGHT$()` string operations.
- Named procedures (`PROC`) and functions (`FN`) with local variables - genuine structured programming, not just `GOSUB`.
- `ON ... GOTO` and `ON ... GOSUB` for computed multi-way branching.
- MODE 7 Teletext display with hardware colour, block mosaic graphics occupying only 1KB of screen RAM.

The BBC Micro's internals  -  its memory map, its OS workspace, its interrupt handlers, its screen architecture  -  were thoroughly documented and directly accessible from BASIC.

`goldenbrown.bas` deploys nearly every one of these features simultaneously:

- a coloured animated screen
- three-voice music playing recognisably
- an efficient live display of the notes moving across a keyboard diagram
  
All from a program you could list and read in its entirety in two minutes.

---

## Complete Program Structure

```text
Line 10        Setup: MODE 7, disable cursor
Line 20        Array declarations: OV%, Y%, NY%
Lines 30-110   Title screen and piano keyboard display
Lines 120-130  Screen colour setup for the cursor display rows
Lines 140-170  Engine initialisation: variables and envelopes
Line 180       Section dispatcher
Lines 190-420  Core sequencer loop (the engine)
Lines 430-580  Four phrase/section blocks (the score)
```

---

## Line 10: MODE 7 and Cursor Control

```basic
10 MODE 7 : VDU 23;8202;0;0;0;
```

`MODE7` selects **Teletext mode**: 40 columns x 25 rows, screen RAM from `&7C00` to `&7FE7` - just 1000 bytes. Compare this with the BBC Micro's other modes: MODE 0 (640x256 pixels, black and white) uses 20KB and MODE 2 (160x256 pixels, 8 colours) uses 20KB. By choosing MODE 7, the program keeps the screen footprint tiny, leaving the maximum space for the program's string score data and BASIC workspace.

More importantly, MODE 7 uses a dedicated co-processor for display. The **SAA5050 Teletext chip** reads screen RAM independently of the 6502 CPU and renders full colour text and mosaic graphics to the TV signal at 50Hz. The CPU never touches the video signal - it only writes bytes to RAM. This means screen updates are effectively free: one `?addr=byte` instruction, and the SAA5050 handles the rest at the next frame boundary. This is the architectural foundation that makes the real-time note visualiser (lines 310-390) possible at no meaningful CPU cost.

`VDU23;8202;0;0;0;` is a VDU 23 sequence that disables the flashing text cursor. `8202` in decimal = `&200A` - the low byte (`&0A`) selects 6845 CRTC register 10 (Cursor Start), and the high byte (`&20` = `00100000` binary) is written as its value. Bits 6-5 of that value are `01`, which sets the cursor display mode to "not displayed". Without this, the OS text cursor would blink independently over whatever row 0 column 0 happens to contain - visually interfering with the title screen mosaic graphics.

---

## Line 20: Variable Declarations

```basic
20 DIM OV%(2), Y%(2), NY%(2)
```

| Variable | Purpose |
| ---------- | --------- |
| `OV%(0..2)` | Last-played note index per voice, biased +67 (ensures stored value is never zero even for S$ position 1) |
| `Y%(0..2)` | Current cursor screen RAM address per voice |
| `NY%(0..2)` | Previous cursor address per voice (for erasure next step) |

---

## Lines 30-110: Title Screen and Piano Keyboard Display

```basic
30  CLS
40  PRINT TAB(11,1) CHR$(141); CHR$(132); "****************"
50  PRINT TAB(11,2) CHR$(141); CHR$(132); "****************"
60  PRINT TAB(11,3) CHR$(141); CHR$(132); "*"; CHR$(131); "GOLDEN BROWN"; CHR$(132); "*"
70  PRINT TAB(11,4) CHR$(141); CHR$(132); "*"; CHR$(131); "GOLDEN BROWN"; CHR$(132); "*"
80  PRINT TAB(11,5) CHR$(141); CHR$(132); "****************"
90  PRINT TAB(11,6) CHR$(141); CHR$(132); "****************"
100 PRINT TAB(19,7) CHR$(134); "by" ' TAB(13) CHR$(134); "The Stranglers"
110 PRINT ' CHR$(131); " b  # b  # # b  # b  # # b  # b  # # b ABBCCDEEFFGGABBCCDEEFFGGABBCCDEEFFGGABB"; CHR$(30)
```

Lines 40-100 build a MODE 7 title using a small set of Teletext attribute codes. In MODE 7, bytes 128-159 (`&80`-`&9F`) are invisible control codes that alter the rendering state for all subsequent characters on the same screen row  -  the *sequential attribute model*. Each control code consumes one character cell but renders as a space. The codes used here:

| CHR$() | Hex | Effect |
| -------- | ----- | -------- |
| `CHR$(131)` | `&83` | Yellow text |
| `CHR$(132)` | `&84` | Blue text |
| `CHR$(134)` | `&86` | Cyan text |
| `CHR$(141)` | `&8D` | Double height |

`TAB(11)` positions before the two leading codes (`CHR$(141)` and `CHR$(132)`), placing the first visible character at column 13. Rows 1-2 and 5-6 print blue double-height `****************`; rows 3-4 print a double-height blue `*`, then `GOLDEN BROWN` in yellow, then a blue `*`. Each double-height character pair must be printed twice  -  once for the top half and once for the bottom  -  which is why lines 40/50, 60/70, and 80/90 each repeat.

The original program stored these control codes as raw bytes embedded directly inside the string literals, which is valid BBC BASIC and compact at the keyboard. This version uses explicit `CHR$()` calls instead, which is clearer when reading the source in a text editor or on GitHub.

**Line 110** draws a **piano keyboard diagram**  -  a permanent reference display at the bottom of the screen:

- `b` = a black key
- Letters `A B C D E F G` = musical note names for white keys, cycling across multiple octaves

This keyboard is not decoration. It directly corresponds to the `S$` note lookup string (line 170). The musician who wrote this score could look at the screen and see which character in the score string produces which note on a piano keyboard  -  it is an integrated composition tool.

`CHR$(30)` at the end is ASCII 30 = **cursor home**  -  it resets the print position to the top-left without clearing the screen, allowing subsequent PRINT output during playback to be correctly repositioned.

---

## Lines 120-130: Screen Colour Setup

```basic
120 ?&7DE0=&84:?&7E30=&82:?&7E80=&81
130 !&7E08=&9D86:!&7E58=&9D86
```

These lines write Teletext attribute bytes directly into MODE 7 screen RAM. All five addresses fall within the `&7C00`-`&7FE7` range. The `?` operator writes a single byte; `!` writes a 32-bit word as four consecutive bytes, little-endian.

In MODE 7 each row is 40 bytes and row N starts at `&7C00 + N * 40`. Checking each address:

| Address | Calculation | Row | Column |
| --------- | ------------- | ----- | -------- |
| `&7DE0` | `&7C00 + 12 x 40` | 12 | 0 |
| `&7E08` | `&7C00 + 13 x 40` | 13 | 0 |
| `&7E30` | `&7C00 + 14 x 40` | 14 | 0 |
| `&7E58` | `&7C00 + 15 x 40` | 15 | 0 |
| `&7E80` | `&7C00 + 16 x 40` | 16 | 0 |

Every address is column 0 of its row - the first character cell on that screen line. These are the five rows that will carry the animated note cursor display.

The values are Teletext foreground colour attributes and background control codes:

| Statement | Row | Bytes written | Teletext meaning |
| ----------- | ----- | --------------- | ----------------- |
| `?&7DE0=&84` | 12 | `&84` | Blue foreground |
| `?&7E30=&82` | 14 | `&82` | Green foreground |
| `?&7E80=&81` | 16 | `&81` | Red foreground |
| `!&7E08=&9D86` | 13 | `&86` then `&9D` | Cyan foreground + New Background |
| `!&7E58=&9D86` | 15 | `&86` then `&9D` | Cyan foreground + New Background |

### Why the Foreground Attributes Matter

The sequencer loop draws each voice's note cursor by writing `&9D` (New Background) to a screen RAM address - this causes the SAA5050 to fill that cell's background with the **current foreground colour** at that point on the row. Whatever foreground attribute was most recently set, that determines the cursor colour.

By placing a foreground attribute at column 0 of each cursor row before the loop ever starts:

- Row 12: Blue foreground set -> cursor blocks on this row appear **blue**
- Row 14: Green foreground set -> cursor blocks on this row appear **green**
- Row 16: Red foreground set -> cursor blocks on this row appear **red**

The cursor formula at line 360 places each voice on the correct row:

```text
Y%(J) = &7E80 + OV%(J) - 60 - 80*J
```

- J=0 (lead, channel 1): base `&7E80` -> row 16 -> **red** cursor
- J=1 (harmony, channel 3): base `&7E30` -> row 14 -> **green** cursor
- J=2 (bass, channel 2): base `&7DE0` -> row 12 -> **blue** cursor

### The Cyan Separator Rows

`!&7E08 = &9D86` stores `&9D86` little-endian: byte 0 at `&7E08` = `&86`, byte 1 at `&7E09` = `&9D`. This places Cyan foreground (`&86`) at column 0 of row 13, immediately followed by New Background (`&9D`) at column 1. In the Teletext sequential attribute model, once New Background fires, every remaining cell on that row displays with that colour as its background. The result is a solid cyan band running the full width of the screen. The identical write to row 15 creates a second cyan band.

These two cyan rows act as visual separators between the three voice cursor tracks - rows 12, 14, and 16 each carry one animated cursor; rows 13 and 15 frame them with solid colour.

This entire setup runs once before the sequencer loop begins. Once the attribute bytes are in place they stay there for the lifetime of the program - the loop only ever writes two bytes per voice per step to animate the cursor, and the correct colour is always already established at column 0.

---

## Lines 140-160: Engine Initialisation

```basic
140 A1 = 30 : A2 = 127 : O = 1 : GT = 2 : DF = 0
150 ENVELOPE 1, 1, 0, 0, 0, 2, 2, 2, A1, 0, 0, 255, 128, 1
160 ENVELOPE 2, 1, 0, 0, 0, 1, 1, 1, A2, 0, 0, 255, 128, 1
```

### Variables

| Variable | Value | Role |
| ---------- | ------- | ------ |
| `A1` | 30 | Attack rate for envelope 1 - slower rise |
| `A2` | 127 | Attack rate for envelope 2 - faster rise |
| `O` | 1 | Octave offset applied to all pitches |
| `GT` | 2 | Starting section - **2 means chorus first** |
| `DF` | 0 | Bass transposition - set per section |

### The ENVELOPE Command

BBC BASIC's `ENVELOPE` command takes 14 parameters and shapes how a note's amplitude (and optionally pitch) changes over time. It runs as part of the OS's 100Hz interrupt service, independently of BASIC. The full syntax is:

```text
ENVELOPE N, T, PI1, PI2, PI3, PN1, PN2, PN3, AA, AD, AS, AR, ALA, ALD
```

| Parameter | Meaning |
| ----------- | --------- |
| `N` | Envelope number (1-4) |
| `T` | Rate: steps fire every T x 10ms (the sound interrupt runs at 100Hz) |
| `PI1, PI2, PI3` | Pitch increment per step in pitch phases 1, 2, 3 |
| `PN1, PN2, PN3` | Number of steps in each pitch phase |
| `AA` | Amplitude added per step during attack |
| `AD` | Amplitude added per step during decay |
| `AS` | Amplitude added per step during sustain |
| `AR` | Amplitude added per step during release |
| `ALA` | Amplitude target at which attack phase ends |
| `ALD` | Amplitude target at which decay/sustain ends |

### Envelope 1 - Lead Melody and Bass

```text
ENVELOPE 1, 1, 0, 0, 0, 2, 2, 2, 30, 0, 0, 255, 128, 1
```

- No pitch modulation (all PI = 0).
- Attack: rises by 30 per step. With T=1 (steps every 10ms), reaching ALA=128 takes approximately 5 steps = **50ms**.
- Decay: AD=0 - the decay phase is instantaneous; amplitude goes straight to sustain at 128.
- Sustain: AS=0 - amplitude holds at 128 while the note is still queued.
- Release: AR=255. Stored as a signed byte, 255 = **-1**: amplitude decreases by 1 per step from 128 to silence over 128 steps = **~1280ms**. This long, gentle fade is what gives the note its sustaining tail.

The result is a **plucked** character: a steady rise to full volume over ~50ms, then a long fade - mimicking the sustain tail of a real harpsichord string.

### Envelope 2 - Harmony

```text
ENVELOPE 2, 1, 0, 0, 0, 1, 1, 1, 127, 0, 0, 255, 128, 1
```

Same structure, but `AA=127`. Attack rises at 127 per step - amplitude reaches ALA=128 in approximately **2 steps (20ms)** compared to 5 steps for Envelope 1. Both envelopes reach the same peak amplitude and release at the same rate, so the decay tails are the same length. The difference is in the attack transient: during the first 50ms, the harmony voice is at full volume while the lead is still rising. This means the harmony strikes hard and reaches full presence immediately, while the lead fades in more gradually - pushing the inner harmony voice forward in the mix during each note onset.

### Envelope Shape Comparison

The two envelopes produce quite different amplitude profiles. The tables below trace each over time, using SOUND `duration=1` (50ms note-on duration before release is triggered):

#### Envelope 1 - AA=30 (lead and bass)

| Step | Time | Amplitude | Phase |
| ------ | ------ | ----------- | ------- |
| 0 | 0ms | 0 | Attack |
| 1 | 10ms | 30 | Attack |
| 2 | 20ms | 60 | Attack |
| 3 | 30ms | 90 | Attack |
| 4 | 40ms | 120 | Attack |
| 5 | 50ms | **128** | Release |
| 6 | 60ms | 127 | Release |
| 7 | 70ms | 126 | Release |
| ... | ... | ... | ... |
| 133 | 1330ms | 0 | Silent |

Attack occupies the entire note duration. At the point the note releases, amplitude has just reached 128. The release then takes ~1280ms to reach silence.

#### Envelope 2 - AA=127 (harmony)

| Step | Time | Amplitude | Phase |
| ------ | ------ | ----------- | ------- |
| 0 | 0ms | 0 | Attack |
| 1 | 10ms | 127 | Attack |
| 2 | 20ms | **128** | Sustain |
| 3 | 30ms | 128 | Sustain |
| 4 | 40ms | 128 | Sustain |
| 5 | 50ms | 128 | Release |
| 6 | 60ms | 127 | Release |
| 7 | 70ms | 126 | Release |
| ... | ... | ... | ... |
| 133 | 1330ms | 0 | Silent |

Attack completes in ~20ms, leaving ~30ms of sustain at full amplitude before release. Both envelopes release from the same peak (128) at the same rate (-1/step), so the decay tails are the same length. The difference is entirely in the first 50ms.

The qualitative shapes, shown schematically:

```text
Amplitude
128 -+        +----------------------------------+------------ ...-> 0
     |       /  Envelope 2 (sustain at 128)      |
     |      /                               ...--+ both release
     |     /                           ..../       identically
     |    /                       ..../              from 128
     |   /                   ..../
     |  /               ..../  Envelope 1 (still attacking)
     | /           ..../
  0  -+--+---------+---------+---------+---------+-
        10ms      20ms      30ms      40ms      50ms
```

During the first 50ms, the harmony voice (Envelope 2) is at or near full volume while the lead (Envelope 1) is still climbing. The SN76489 chip uses a 4-bit attenuation register (0 = full volume, 15 = silence, each step ~2dB) so the volume difference during this attack transient is substantial. At 10ms after a note fires, the harmony is at amplitude 127 (near-maximum output) while the lead is at amplitude 30 (barely audible). This transient difference in character is what sonically separates the harmony from the lead despite both using the same type of square-wave tone generator and both reaching the same peak.

---

## Line 170: The Note Lookup String - The Heart of the Encoding

```basic
170 S$ = "BVCXZQAWSEDFTGYHJIKOLP;:[]_1234567"
```

This 34-character string is the entire pitch encoding system. `INSTR(S$, char)` returns 1-34 for any character found in `S$`, and 0 if not found. The pitch value sent to `SOUND` is:

```text
pitch = 4 x O + 4 x INSTR(S$, char)
```

With `O=1`: minimum pitch = `4+4=8`, maximum = `4 + 4x34 = 140`. Each step of 4 corresponds to one semitone on the BBC Micro's internal pitch table. So `S$` maps directly to a 34-semitone (nearly 3 octave) chromatic scale.

### The Character-to-Position Mapping

```text
Pos:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34
Char: B  V  C  X  Z  Q  A  W  S  E  D  F  T  G  Y  H  J  I  K  O  L  P  ;  :  [  ]  _  1  2  3  4  5  6  7
```

### Why These Specific Characters?

This is not a random assignment. These characters trace a path across the physical BBC Micro keyboard from low-left to upper-right:

```text
BBC Micro keyboard layout (relevant section):

Number row:  1   2   3   4   5   6   7   8   9   0
QWERTY row:  Q   W   E   R   T   Y   U   I   O   P   @   [   _
ASDF row:    A   S   D   F   G   H   J   K   L   ;   :   ]
ZXCV row:    Z   X   C   V   B   N   M
```

Reading `S$` left to right:

- **`B V C X Z`**: the bottom row swept right-to-left  -  `B` sits at the right of the ZXCV cluster, `Z` at the left, so this gives the five lowest pitches.
- **`Q A W S E D F T G Y H J I K O L P ; :`**: the QWERTY and ASDF rows in left-to-right **column pairs**  -  for each column, the QWERTY-row key followed by the ASDF-row key immediately below it: Q+A, W+S, E+D, T+G, Y+H, I+K, O+L, P+;. Three keys are absent from S$: `R`, `U`, and `@`. Their column partners `F`, `J`, and `:` appear as lone entries at those positions, but the column-pair structure is otherwise unbroken throughout.
- **`[ ]`**: a final column pair  -  `[` on the QWERTY row, `]` on the ASDF row directly below it.
- **`_ 1 2 3 4 5 6 7`**: `_` is the rightmost key on the QWERTY row, then the number row for the highest pitches.

Why `R`, `U`, and `@` specifically are excluded is not evident from the code  -  34 notes was sufficient for the arrangement, and their absence leaves the column-pair geometry otherwise clean.

The score strings are therefore written as **keyboard tablature**: the character that appears in `T$`, `M$`, or `N$` is literally the BBC Micro keyboard key you would press to sound that note. This made composing directly in the BASIC editor practical - the musician could type score characters while mentally associating each physical key with its pitch.

The on-screen piano diagram (line 110) reinforces this: it provides a visual mapping between the letter characters and their musical equivalents, so both composer and audience can cross-reference the score with the keyboard.

---

## Line 180: The Section Dispatcher

```basic
180 ON GT GOTO 430, 470, 510, 550 ELSE GT = 1 : GOTO 430
```

`ON GT GOTO` is a BBC BASIC multi-way branch by ordinal:

- `GT=1` -> goto 430
- `GT=2` -> goto 470
- `GT=3` -> goto 510
- `GT=4` -> goto 550
- `GT` out of range -> ELSE fires: `GT = 1 : GOTO 430`

The initial value is `GT=2`, so **the very first section played is 470 - the chorus**. This matches the structure of the original recording, which also opens on the chorus rather than the verse.

Each phrase block ends with `GT = GT + 1 : GOTO 190`. After playing, GT increments. The full cycle is:

```text
Startup: GT=2  ->  section 470 (chorus A)
GT=3           ->  section 510 (chorus B variation)
GT=4           ->  section 550 (bridge)
GT=5 -> ELSE   ->  GT=1 -> section 430 (verse)
GT=2           ->  section 470 (chorus A again)
                   ... repeats indefinitely
```

The song has a natural verse/chorus structure; the ELSE reset ensures it loops cleanly back into the chorus cycle once the verse completes.

---

## Lines 190-420: The Core Sequencer Loop

This is the beating heart of the program. Every note you hear passes through here.

### Lines 190-220: Step Initialisation

```basic
190 DL = 16 : T% = 1
200 FOR K = 1 TO LEN T$
210 T = TIME + DL
220 F$ = MID$(T$, K, 1) : G$ = MID$(M$, K, 1) : H$ = MID$(N$, K, 1)
```

`DL=16` sets the step duration in centiseconds (the BBC Micro `TIME` counter increments 100 times per second). `DL=16` = **160ms per note step**.

The `FOR K` loop steps character-by-character through all three voice strings simultaneously. All three strings in a given section are the same length.

**`T=TIME+DL` is the most important single line in the program** - see the timing section below.

`F$`, `G$`, `H$` each extract one character from the lead, harmony, and bass strings at position `K`. All three voices are always synchronised at the same character index.

### Lines 230-250: Sound Output

```basic
230 IF F$ <> " " THEN SOUND 1, 1, 4*O + 4*INSTR(S$, F$), 1
240 IF G$ <> " " THEN SOUND 3, 2, 4*O + 4*INSTR(S$, G$), 1
250 IF H$ <> " " THEN SOUND 2, 1, 4*O + DF + 4*INSTR(S$, H$), 1
```

**A space character = rest.** Any non-space character triggers a note. The voice-to-channel mapping is:

| Line | Channel | Voice | Envelope |
| ------ | --------- | ------- | --------- |
| 230 | 1 | Lead melody (`T$`) | 1 - slower attack |
| 240 | 3 | Harmony (`M$`) | 2 - sharper attack |
| 250 | 2 | Bass (`N$`) | 1 - slower attack, offset by `DF` |

The `SOUND` duration is always `1`  -  one twentieth of a second (50ms). Notes are never held by the duration parameter. The audible length comes entirely from the ENVELOPE shape: the pluck-and-decay profile described above. This avoids any OS queue buildup from overlapping durations.

**The `DF` transposition for bass:** `DF=48` in section 430 (verse), `DF=0` everywhere else. Since each increment of 4 = one semitone, `48/4=12 semitones` = one full octave. In the verse section, the bass line plays **an entire octave lower** than the lead and harmony. This is the primary structural contrast between verse and chorus - one variable, one value change, total timbral transformation.

### Lines 260-300: Note State Memory - What OV% Holds

```basic
260 IN0 = INSTR(S$, F$) : IN1 = INSTR(S$, G$) : IN2 = INSTR(S$, H$)
270 IF IN0 = 0 THEN IN0 = OV%(0) - 67
280 IF IN1 = 0 THEN IN1 = OV%(1) - 67
290 IF IN2 = 0 THEN IN2 = OV%(2) - 67
300 OV%(0) = IN0 + 67 : OV%(1) = IN1 + 67 : OV%(2) = IN2 + 67
```

When a voice character is a space (rest), `INSTR` returns 0. The program does not want the screen note-cursor for that voice to jump to zero/undefined - it should **hold at the last-played note position** so the visual tracker stays meaningful during rests.

`OV%(0..2)` stores the per-voice last-active note index, offset by +67. The +67 bias avoids the ambiguity of array element 0 meaning "never played" - even the very first note (position 1 in `S$`) stores as 1+67=68, safely non-zero. Reading back: `actual_index = OV%(i) - 67`.

At lines 270-290: if a voice is resting (`INx=0`), substitute `OV%(i)-67` - the last played index - as the effective note position for display purposes. Line 300 always updates `OV%` with whichever index was used (new note or held position).

This array is **not used for audio** - the SOUND commands at 230-250 have already fired. `OV%` exists purely to keep the visual tracker smooth across rests.

### Lines 310-390: The Real-Time Visual Note Tracker

```basic
310 FOR I = 0 TO 2
320 Y%(I) = &7FFF
330 NEXT I
340 FOR J = 0 TO 2
350 ?NY%(J) = 156
360 Y%(J) = &7E80 + OV%(J) - 60 - 80*J
370 NY%(J) = Y%(J)
380 ?Y%(J) = 157 : Y%(J)?1 = 156
390 NEXT J
```

This section draws a **live, animated cursor on the on-screen piano keyboard** that moves in sync with the notes. It is one of the most impressive features of the program - five lines of code producing a real-time multi-voice visualiser by writing directly into screen RAM.

### Why Direct RAM Writes - Not PRINT

The natural BBC BASIC way to put something on screen is `PRINT` or `VDU`. But `PRINT` goes through the full OS VDU driver: it updates the cursor position, checks scroll conditions, interacts with the 6845 CRTC, and processes escape sequences. For a tight real-time loop that needs to erase and redraw three cursors every 160ms while also computing pitches and firing SOUND calls, that overhead is unacceptable.

Direct writes with `?addr=byte` bypass all of that. The 6502 executes a single store instruction. The byte appears in screen RAM. The SAA5050 picks it up on the next 50Hz video frame. Total CPU cost: one memory write. This is only possible because the BBC Micro's memory map is **fully unified** - the 6502's 64KB address space contains RAM, ROM, hardware registers, screen memory, and OS workspace all at fixed addresses. `?` is the same operator used to write the Teletext colour attributes at `&7DE0` in line 120. The CPU does not distinguish between screen RAM and any other address - they are all just memory.

This architectural choice - a flat address space with screen RAM at a known fixed location - is what makes this kind of programming natural on the BBC Micro.

### How the Screen Memory Map Works

In MODE 7, screen RAM occupies `&7C00`-`&7FE7`: 1000 bytes for 25 rows of 40 characters.

```text
Address   Row  Contents
&7C00      0   Top of screen
&7C28      1
&7C50      2
  ...
&7D90     10   Piano keyboard sharps/flats row (line 110)
&7DB8     11   Piano keyboard note names row (line 110 wraps)
&7DE0     12   Voice 2 (bass) cursor row - blue
&7E08     13   Cyan separator row
&7E30     14   Voice 1 (harmony) cursor row - green
&7E58     15   Cyan separator row
&7E80     16   Voice 0 (lead) cursor row - red
  ...
&7FC8     24   Bottom of screen
```

Each row is 40 bytes - one byte per character cell. `&7E80 - &7C00 = 640 = 16 x 40`, confirming row 16. The cursor rows sit immediately below the piano keyboard display, with two cyan separator bands framing the three voice tracks.

### The Two Teletext Bytes Used for the Cursor

The cursor is drawn using two specific Teletext control codes:

- **Byte 157 (`&9D`) = New Background**: instructs the SAA5050 to set the background colour of subsequent cells to the current foreground colour. Lines 120-130 placed a foreground colour attribute at column 0 of each cursor row  -  Red on row 16, Green on row 14, Blue on row 12. When `&9D` fires, it fills the cell's background with that row's foreground colour, creating a coloured block.
- **Byte 156 (`&9C`) = Black Background**: resets the background to black. Written to the cell immediately after the cursor, it prevents the coloured background from continuing rightward across the rest of the row.

The BBC BASIC syntax `Y%(J)?1=156` uses the **indexed poke** form: `base?offset` means `base + offset` bytes. So `Y%(J)?1` = address `Y%(J)+1` - the character cell immediately to the right of the cursor. Writing 156 there cleanly terminates the bright block at exactly one cell wide.

**Line 310: Defensive pre-reset (vestigial).** Before the FOR J loop begins, `FOR I = 0 TO 2 : Y%(I) = &7FFF : NEXT I` pre-loads every `Y%(I)` with `&7FFF`  -  one byte past the top of screen RAM (`&7FE7`). The intent is defensive: a write to `&7FFF` lands outside the screen area, so if a cursor-erase poke were ever issued against an uninitialised `Y%()` it would corrupt nothing visible. In practice this is dead code: line 360 unconditionally overwrites every `Y%(J)` on the same iteration of the FOR J loop before any poke uses it, so the sentinel value is never read. It is most likely a leftover from an earlier version where the initialisation path was structured differently.

#### For each voice J (0, 1, 2)

1. **Line 350: Erase previous cursor.** `?NY%(J)=156` writes Black Background (`&9C`) to the address saved from the *previous* step. This overwrites the New Background (`&9D`) that was drawing the cursor, instantly extinguishing it.

2. **Line 360: Compute new cursor position.**

   ```text
   Y%(J) = &7E80 + OV%(J) - 60 - 80*J
   ```

   - `OV%(J) - 60`: maps the note index (1-34 scale) to a horizontal column offset, positioning the cursor below the corresponding key in the piano diagram.
   - `-80*J`: 80 bytes = 2 rows x 40 bytes/row. Voice 0 -> row 16, Voice 1 -> row 14, Voice 2 -> row 12. Three simultaneous cursors stacked vertically below the piano keyboard, one per voice.

3. **Line 370: Save position for next erase.** `NY%(J) = Y%(J)` saves the address just written, so the next step knows exactly where to erase.

4. **Line 380: Draw cursor.** `?Y%(J) = 157 : Y%(J)?1 = 156` - New Background at the cursor position (creates a coloured block in the row's foreground colour), Black Background at the next cell (stops it spreading right).

The SAA5050 processes the entire screen RAM at 50Hz regardless of whether the CPU has touched it. The CPU's only job is to manage two bytes per voice per step. The result: a smooth, flicker-free three-voice note tracker with essentially zero performance cost - and no operating system involvement whatsoever.

### Line 400: The Timing Wait and Outer Loop

```basic
400 REPEAT UNTIL TIME >= T
410 NEXT K
420 GOTO 180
```

`REPEAT UNTIL TIME >= T` is a **busy-wait**: BASIC spins checking `TIME` until it reaches the pre-recorded target. Then `NEXT` advances `K`. When the `FOR K` loop completes (all characters in the current phrase played), `GOTO 180` returns to the section dispatcher to start the next phrase.

---

## The Timing Mechanism - Why It Stays Perfectly in Tempo

The single most important design decision in the sequencer is **where `T=TIME+DL` is placed**.

It is at the **start** of processing each note step (line 210), not at the end.

```text
K step begins:    T = TIME + DL          <- deadline recorded NOW
                  F$, G$, H$ extracted   <- character lookup
                  SOUND1...              <- audio output
                  SOUND3...
                  SOUND2...
                  IN0, IN1, IN2          <- INSTR calculations
                  OV% updates            <- note state
                  Screen cursor erase    <- ?NY%(J)=156
                  Screen cursor draw     <- ?Y%(J)=157...
                  REPEAT UNTIL TIME>=T   <- wait for remainder
K step ends.      Total elapsed = exactly DL centiseconds.
```

Regardless of how many milliseconds the processing takes, the total step duration is always `DL` centiseconds. If audio + screen processing takes 8cs, the wait is 8cs. If sparse notes need only 2cs, the wait is 14cs. **The tempo is self-compensating.**

This is a BASIC-level implementation of what in professional real-time systems is called deadline scheduling - normally associated with interrupt-driven code. On an interpreted 2MHz 6502, this technique keeps the tempo invariant across sections of differing note density.

`DL=16` at 100Hz = 160ms per step. The phrase strings are authored with note spacing that produces the characteristic waltz feel when played at this rate.

---

## Lines 430-580: The Four Phrase Blocks (The Score)

Each block sets `T$` (lead), `M$` (harmony), `N$` (bass), optionally `DF`, then increments `GT` and jumps to line 180.

### Section 430 - Verse (`DF=48`, bass one octave lower)

```basic
430 T$ = "Y  I PO J T Y  I PO J T Y  I PO J T ..."
440 M$ = "C  C  B B B C  C  B B B C  C  B B B ..."
450 N$ = "  _ PO      I O PO        _ P O   I Y J IJ ..." : DF = 48
460 GT = GT + 1 : GOTO 190
```

`T$` is 96 characters  -  eight repetitions of a 12-step figure: `Y . . I . P O . J . T .` (positions 15, 18, 22, 20, 17, 13). The intervals are +3, +4, -2, -3, -4: a rising leap into a falling scale fragment, with generous rests that let the harpsichord-like envelope articulate each note individually.

`M$` oscillates between just two characters: `C` (pos 3) and `B` (pos 1)  -  a minor second, 2 semitones apart. This tight dissonance against the melody creates the characteristic uneasy inner voice of the verse.

`N$` carries active syncopation against the relatively slow-moving melody. `DF=48` drops the bass a full octave below the lead, creating the dark, low register of the verse:

| Figure | Positions | Motion |
| -------- | ----------- | -------- |
| `_ P O` | 27->22->20 | Descending leap |
| `I O P` | 18->20->22 | Ascending response |
| `Y J IJ` | 15->17->18->17 | Ornamental turn |
| `Y T EW` | 15->13->10->8 | Closing descent |

### Section 470 - Chorus A (`DF=0`)

```basic
470 T$ = "P[ P[[JO JOOIP IPPJOYOTOFOP[ P[[JO JOOIP IPPJOYOTOFO"
480 M$ = "E  E EZ  Z ZQ  Q QWOWOWOWOE  E EZ  Z ZQ  Q QJTYTTTFT"
490 N$ = "ET J EJO : JIP [ IWTWTWTWTET J EJO : JIP [ IWTWTWTWT"
500 GT = GT + 1 : GOTO 190
```

`T$` is 52 characters  -  two identical 26-character halves. It opens `P`(22) `[`(25)  -  an ascending minor third that is **the signature leap of the chorus**  -  then a rapid descending-ascending run through `JO JOOIP IPPJOYOTOFO`. All three voices are dense and active; `DF=0` means bass shares the same register as the lead.

`M$` descends E(10) -> Z(5) -> Q(6), then hits the **octave-bounce engine**: `WOWOWOWO`  -  `W`(pos 8) and `O`(pos 20) are exactly 12 semitones apart. Eight alternating steps at 160ms each drive the rhythmic momentum of the chorus. The second half ends `JTYTTTFT`  -  a cadence fill.

`N$` carries its own ascending pattern: `E T . J` (10->13->17) in thirds, `: . J I P` (24->17->18->22) as chromatic upward fill, then `WTWTWTWT`  -  a 5-semitone bass oscillation. Three simultaneous ostinati (lead pedal, harmony octave, bass fifth) interlock for 8 steps.

### Section 510 - Chorus B (variation, `DF=0`)

```basic
510 T$ = "P[ P[[JO JOOIP IPPJOYOTOFOP[ P[[JO JOOO: O::I J Y T "
520 M$ = "E  E EZ  Z ZQ  Q QWOWOWOWOE  E EZ  Z ZW  W WITJTYTTT"
530 N$ = "ET J EJO : JIP [ IWTWTWTWTET J EJO : JO: : OIIJIYITI"
540 GT = GT + 1 : GOTO 190
```

The first half of all three strings is identical to section 470. The second half diverges  -  a variation matching the natural chorus repeat structure of the original recording.

`T$` ends with a stepwise descent: positions 20->24->24->18->17->15->13  -  **the cadence figure** that closes the chorus. `M$` descends through the cadence in parallel. `N$` moves in the opposite direction  -  chromatic upward counterpoint: `J O : . : O I I J I Y I T I`. Lead descends, bass ascends: **contrary motion** into the verse return.

### Section 550 - Bridge (`DF=0`)

```basic
550 T$ = "Y  I PO J T Y  I PO J T "
560 M$ = "C  C  B B B C  C  B B B "
570 N$ = "YYYYYYTTJ J YYYYYYTTJ J "
580 GT = GT + 1 : GOTO 190
```

A shorter section  -  25 characters. `T$` and `M$` are identical to the verse melody and harmony, but compressed to just 2 repetitions (25 steps vs 96)  -  creating urgency through compression.

`N$` is the bridge's defining element: `YYYYYYTTJ J`. Character `Y`=position 15, repeated six times  -  **a pedal point**, 960ms of the same pitch holding harmonic ground while the melody floats above. Then `T`(13) steps down 2 semitones, and `J`(17) leaps back up with rests. No walking bass  -  a single sustained pitch-centre creates maximum tension before the verse re-enters.

---

## The BBC Micro SN76489 Sound Architecture

The BBC Micro uses the **Texas Instruments SN76489AN** programmable sound generator:

- 3 independent **tone generators** producing square waves, each with programmable frequency and volume.
- 1 **noise generator** (periodic noise or white noise).
- Each channel's volume is controlled by the OS via the ENVELOPE interrupt handler, firing at 100Hz.

BBC BASIC's `SOUND` command syntax:

```text
SOUND channel, envelope, pitch, duration
```

| Parameter | Range | Notes |
| ----------- | ------- | ------- |
| `channel` | 0-3 | 0=noise, 1-3=tone channels |
| `envelope` | 1-4 | References an ENVELOPE number |
| `pitch` | 0-255 | 0=silence; each +4 ~ one semitone |
| `duration` | 1-255 | In units of 5/100 second |

**Pitch value to frequency:** The OS holds a table mapping pitch values to SN76489 frequency divisor words. Each step of 4 = one semitone in 12-tone equal temperament. The range 8-140 used in this program covers roughly three chromatic octaves.

**The OS sound queue:** Each channel maintains a FIFO queue. Notes play when the previous note finishes. Using `duration=1` throughout and constraining all note starts to the 160ms DL grid via the TIME-based wait ensures the queue never accumulates - every note slot is consumed before the next arrives.

---

## Step-by-Step Trace: Section 470, K=1 and K=2

**Setup:** `T$ = "P[ P[[JO..."`, `M$ = "E  E EZ..."`, `N$ = "ET J EJO..."`, `DF=0`, `O=1`

### K=1

```text
F$ = "P",  G$ = "E",  H$ = "E"
```

- Lead:    `INSTR(S$,"P") = 22` -> pitch = `4x1 + 4x22 = 92` -> `SOUND1, 1, 92, 1`
- Harmony: `INSTR(S$,"E") = 10` -> pitch = `4x1 + 4x10 = 44` -> `SOUND3, 2, 44, 1`
- Bass:    `INSTR(S$,"E") = 10` -> pitch = `4x1 + 0 + 4x10 = 44` -> `SOUND2, 1, 44, 1`

All three voices fire simultaneously, reinforcing the opening chord.

**OV% update:** `IN0=22, IN1=10, IN2=10` -> `OV%(0)=89, OV%(1)=77, OV%(2)=77`

### K=2

```text
F$ = "[",  G$ = " " (rest),  H$ = "T"
```

- Lead:    `INSTR(S$,"[") = 25` -> pitch = `4 + 100 = 104` -> `SOUND1, 1, 104, 1`
- Harmony: space -> no SOUND
- Bass:    `INSTR(S$,"T") = 13` -> pitch = `4 + 52 = 56` -> `SOUND2, 1, 56, 1`

Lead leaps upward 3 semitones (P->[, pos 22->25). Bass steps down. Harmony rests - `IN1=0`, so `OV%(1)` stays 77 from the previous step. The harmony cursor holds its position on screen.

This is the characteristic texture: lead and bass moving together, harmony voice holding or moving independently.

---

## Why It Is Extraordinary

Each technique in `goldenbrown.bas` is clever in isolation. Together, they produce a remarkable density of function in 90 lines of interpreted BASIC on a 2MHz processor.

1. **Three simultaneous voices, fully arranged** - not just three notes playing at once, but a proper arrangement: lead melody, inner harmony, and bass line in independent registers, each with distinct articulation from separate envelope definitions. This is compositional thinking, not just technical demonstration.

2. **Envelope differentiation gives timbral separation** - Envelope 1 (slow 50ms attack) for lead and bass; Envelope 2 (fast 20ms attack, 30ms sustain at peak) for harmony. Both share the same long ~1280ms release tail, but the attack transient is where the voices separate: the harmony reaches full volume almost instantly while the lead is still fading in. The two envelope characters push the voices apart in time even when they share pitches.

3. **The bass register shift is architectural** - `DF=48` in the verse and `0` in the chorus is one assignment that restructures the entire sonic landscape. The verse sounds dark and low; the chorus opens up. This is the primary structural contrast of the song, achieved with a single number.

4. **The score encoding is elegantly self-documenting** - `S$` is not an arbitrary lookup. It maps the physical BBC Micro keyboard bottom-to-top onto a chromatic ascending scale  -  lower keyboard rows carry lower pitches, the number row the highest. The score strings are exactly the keys you would press to play those notes. The on-screen piano diagram makes this visible. This is a complete self-contained compositional system embedded in one string literal.

5. **The timing is professional-grade** - `T=TIME+DL` at the *start* of each step is deadline scheduling: a technique normally found in interrupt-driven embedded systems, not in an interpreted high-level language on a 1981 home computer. It means the tempo is invariant regardless of processing load - the sequencer self-corrects every single step.

6. **The visualiser costs almost nothing** - five lines of code draw a live three-voice note cursor that moves in real time across an on-screen piano keyboard, at 50Hz, driven entirely by the SAA5050 chip reading from two bytes changed per voice per step. The `OV%` array - designed solely to keep the display smooth during rests - is a considered data structure in a program most people would not have bothered to give a data structure at all.

7. **Two levels of system access, each in the right place** - `ENVELOPE` and `SOUND` for audio: the MOS handles all interrupt-level channel management and envelope stepping, exactly as intended. Direct `?` and `!` writes to screen RAM for everything visual: the one-time colour setup at lines 120-130 and the per-step cursor animation at lines 310-390. The OS VDU driver never runs during playback. Two clean layers, each used for what it is good at.

For 32KB of RAM, a 2MHz 6502, and a three-voice square-wave chip on a GBP 399 computer - this is extraordinary work.

---

## Full Variable Reference

| Variable | Type | Role |
| ---------- | ------ | ------ |
| `S$` | String | Note lookup: character -> semitone index (1-34) |
| `T$` | String | Lead melody score - one character per step |
| `M$` | String | Harmony score |
| `N$` | String | Bass score |
| `O` | Integer | Octave offset (1 throughout - base pitch multiplier) |
| `GT` | Integer | Section state counter (1-4, wraps via ELSE clause) |
| `DF` | Integer | Bass transposition: 48 = verse (base + 1 oct down), 0 = chorus |
| `DL` | Integer | Step duration in centiseconds (16 = 160ms) |
| `T` | Integer | TIME deadline for end of current step |
| `K` | Integer | Current character position in phrase strings |
| `F$` | String | Lead character at step K |
| `G$` | String | Harmony character at step K |
| `H$` | String | Bass character at step K |
| `IN0, IN1, IN2` | Integer | INSTR results (0 = rest or not in S$) |
| `OV%(0..2)` | Integer array | Per-voice last-active note index, biased +67 |
| `Y%(0..2)` | Integer array | Per-voice current screen cursor address |
| `NY%(0..2)` | Integer array | Per-voice previous screen cursor address (for erase) |
| `A1` | Integer | Envelope 1 attack rate (30) |
| `A2` | Integer | Envelope 2 attack rate (127) |

---

## A Final Note

There are many examples of music on the BBC Micro, but Golden Brown's engine is immediately arresting:  compact, complete, and beautiful in its structure.

The program was written to run on a screen, to play a tune, to delight whoever sat down at that keyboard. It demonstrates deep knowledge of the BBC Micro's internals: its sound chip, its screen architecture, its OS workspace, its BASIC dialect. A sophisticated musical arrangement is encoded using the physical keyboard as a compositional instrument; the timing is correct on the first principles of real-time scheduling.

We still have the program. We can still run it. We can read every line and see what was done and understand why. That is a remarkable thing to be able to say forty years later about a piece of work this dense and this good.

To whoever wrote it: thank you.
