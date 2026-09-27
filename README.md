# Conversation transcripts: recording → word-level TextGrid → spreadsheet

Turns a conversation recording into a word-by-word transcript with **trustworthy timings**, which a person then
cleans in Praat. Built for the Hayden Lab conversation study.

```
   audio.wav
      │
      ├─ 1. WHISPER      what was said, who said it, rough word times
      ├─ 2. MFA          re-finds those words in the audio  →  accurate word ONSETS
      ├─ 3. YOU, IN PRAAT  fix the words, the speakers, and the boundaries
      └─ 4. SPREADSHEET  one command → the Excel table the lab analyses
```

**Why the timings matter:** neural responses to a word are measured in bins tens of milliseconds wide, and
Whisper's word onsets run about **65 ms late** on room-mic recordings. That error does not average away — it
shifts every response. Step 2 is what removes it, and step 3 is what catches what step 2 got wrong.

---

## Start here

### I was given a recording and told to transcribe it
Do all four steps. Setup below, then read the guide.

### I was given a `.wav` and a `.TextGrid` someone already made
You do **not** need anything in this repository except the guide. Install Praat and start at section 4 of
**[the annotator's guide](docs/SOP_Convo_Praat_Cleaning.pdf)** — no Python, no conda, no command window.

---

## Setup (once, 30–45 minutes, mostly waiting)

**1 · Get the code.** Green **Code** button at the top of this page → **Download ZIP** → unzip it into your
**Documents** folder. You do not need git, and you do not need to know what git is.

**2 · Install Miniconda** — <https://docs.conda.io/en/latest/miniconda.html>. On a Mac, check the Apple menu →
*About This Mac* first: choose the **Apple Silicon** build for M1/M2/M3, the **Intel** build otherwise.

**3 · Run the setup script.** It builds both environments and downloads the aligner's English models.

<table>
<tr><th>Windows</th><th>Mac</th></tr>
<tr><td>

Open **Anaconda Prompt** (Start menu — *not* Command Prompt), then:
```bat
cd "path\to\this\folder"
setup_windows.bat
```
</td><td>

Open **Terminal** (⌘+Space), then:
```bash
cd "path/to/this/folder"
bash setup_mac.sh
```
</td></tr>
</table>

It finishes by checking itself and printing **Ready**. You can re-run that check any time:

```bash
python check_setup.py
```

**4 · Optional — let it separate the speakers.** Make a free account at huggingface.co, accept the terms on
[segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) and
[speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1), then
`conda activate whisper && huggingface-cli login`. Skip it and every word lands on one row, which you split by
hand in Praat.

---

## Transcribe a recording

```bash
conda activate whisper
cd "path/to/this/folder"
python run_all.py
```

It asks three questions — **drag the sound file into the window**, press Enter for the results folder, and type
**how many people are talking**. Then it runs the whole pipeline, including the aligner, without you switching
environments.

> Answer the speaker question if you can. Counting voices is the thing the code is worst at and the thing you
> already know. A number pins it to exactly that many rows; a guess is what splits one person across two.

You get `<name>_words.TextGrid`. Open it with the `.wav` in Praat and clean it — that part is
**[the annotator's guide](docs/SOP_Convo_Praat_Cleaning.pdf)**, which is written for someone who has never
programmed. Then:

```bash
python textgrid_to_excel.py "cleaned.TextGrid" "cleaned.xlsx" --exclude
```

---

## Patient data

Recordings and transcripts are PHI. **Nothing in this repository is a place to put them** — `.gitignore` blocks
audio, TextGrids and spreadsheets on purpose. Every stage runs locally or on lab hardware; no audio is sent to
any API. Model weights download from HuggingFace the first time, which uploads nothing.

## Further reading

- **[docs/SOP_Convo_Praat_Cleaning.pdf](docs/SOP_Convo_Praat_Cleaning.pdf)** — the annotator's guide (the human step)
- **[TECHNICAL_NOTES.md](TECHNICAL_NOTES.md)** — what each step does, the known traps, validation numbers
