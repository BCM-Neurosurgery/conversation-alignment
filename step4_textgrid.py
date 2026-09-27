#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
STEP 4 of 4 — MFA output -> the final word TextGrid (+ the lab's Excel layout).

Takes MFA's alignment, puts every word back on its speaker's tier with its ORIGINAL punctuated spelling, and
writes the two files the lab works with.

Two things this has to get right, both learned the hard way:
 1. ⚠️ Read MFA's DATABASE, not its exported TextGrids. MFA 3.1.0's exporter DROPS THE FIRST WORD of each
    utterance (11 of 12 files in one project) while the database is complete. `--mfa-out` is a fallback only.
 2. ⚠️ MFA does not return your tokens one-for-one: it splits hyphenated words ("u-shaped" -> "u" + "shaped"),
    splits clitics ("afo's" -> "afo" + "'s"), and can drop an utterance it failed to align. Matching by
    position would then mis-label every later word, so words are matched INSIDE each utterance by gluing
    characters together until they account for the original token.

    python step4_textgrid.py <stem>.sidecar.json <out_dir> [--db <corpus>.db] [--mfa-out <dir>]

Outputs:
    <stem>_words.TextGrid   one interval tier per speaker, one word per interval  <- open this in Praat
    <stem>_words.xlsx       onset | offset | Duration (ms) + one column per speaker + timing_source
                            ('mfa' = properly aligned; 'whisper' = MFA merged/dropped it, timing is Whisper's
                            and therefore ~65 ms late — check those first in Praat; 'tag' = an annotation marker
                            like ?? or haha, which MFA cannot align, so it keeps the time it already had)
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys
from pathlib import Path

SIL = {"<eps>", "", "sil", "spn_sil", "sp", "spn", "<unk>"}


def letters(t: str) -> str:
    return re.sub(r"[^a-z0-9']", "", str(t).lower())


def utterances_from_db(db_path):
    """[(speaker, utt_begin, [(start, end, word), ...]), ...] straight from MFA's database."""
    c = sqlite3.connect(str(db_path))
    utts = c.execute("select u.id, s.name, u.begin from utterance u join speaker s on u.speaker_id = s.id "
                     "order by u.begin").fetchall()
    out = []
    for uid, spk, begin in utts:
        rows = c.execute("select wi.begin, wi.end, w.word from word_interval wi join word w on wi.word_id = w.id "
                         "where wi.utterance_id = ? order by wi.begin", (uid,)).fetchall()
        rows = [(float(b), float(e), str(w)) for b, e, w in rows if str(w) not in SIL and e > b]
        if rows:
            out.append((str(spk), float(begin), rows))
    return out


def utterances_from_textgrids(mfa_out, sidecar_utts):
    """Fallback: group exported-TextGrid words into the sidecar's utterance windows."""
    from praatio import textgrid as ptg
    words = []
    for f in sorted(Path(mfa_out).glob("*.TextGrid")):
        tg = ptg.openTextgrid(str(f), includeEmptyIntervals=False)
        for name in tg.tierNames:
            if "phone" in name.lower():
                continue
            spk = name.replace(" - words", "").strip()
            for e in tg.getTier(name).entries:
                if e.label.strip() and e.label.strip() not in SIL:
                    words.append((spk, float(e.start), float(e.end), e.label.strip()))
    out = []
    for u in sidecar_utts:
        rows = [(s, e, w) for spk, s, e, w in words
                if spk == u["speaker"] and s >= u["start"] - 0.01 and e <= u["end"] + 0.01]
        if rows:
            out.append((u["speaker"], u["start"], sorted(rows)))
    return out


def match_utterance(mfa_rows, tokens):
    """Glue MFA's (possibly split) words back onto the original tokens.
    MFA sometimes merges or drops a token; those keep Whisper's own time so no word is ever lost.
    -> [(start, end, original, source)] with source 'mfa' | 'whisper'"""
    out, i = [], 0
    for tok in tokens:
        if not tok["mfa"]:                            # annotation tag (??, haha): MFA never saw it
            ws, we = tok.get("whisper_start"), tok.get("whisper_end")
            if ws is not None:
                out.append((float(ws), float(we), tok["original"], "tag"))
            continue
        want, got, s, e = letters(tok["mfa"]), "", None, None
        while i < len(mfa_rows) and len(got) < len(want):
            b, en, w = mfa_rows[i]
            s = b if s is None else s
            e = en
            got += letters(w)
            i += 1
        if s is None:                                     # MFA had nothing left for this token
            ws, we = tok.get("whisper_start"), tok.get("whisper_end")
            if ws is None:
                continue
            out.append((float(ws), float(we), tok["original"], "whisper"))
        else:
            out.append((s, e, tok["original"], "mfa"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sidecar"); ap.add_argument("out_dir")
    ap.add_argument("--db", help="MFA database; if omitted, searched for under --mfa-root")
    ap.add_argument("--mfa-out", help="fallback: MFA's exported TextGrid dir (loses the first word per utterance)")
    ap.add_argument("--mfa-root", default=str(Path.home() / "Documents" / "MFA"))
    ap.add_argument("--corpus-name", help="MFA names its database after the corpus FOLDER (default: sidecar's)")
    a = ap.parse_args()
    import pandas as pd
    from praatio import textgrid as ptg

    side = json.loads(Path(a.sidecar).read_text(encoding="utf-8"))
    stem, dur = side["stem"], float(side["duration"])
    if not a.db and not a.mfa_out:
        # MFA writes ~/Documents/MFA/<corpus folder name>/<corpus folder name>.db (NOT "corpus.db")
        corpus = a.corpus_name or Path(a.sidecar).parent.name
        hits = sorted(Path(a.mfa_root).glob(f"{corpus}/*.db")) or sorted(Path(a.mfa_root).glob("*/*.db"))
        if not hits:
            raise SystemExit(f"no MFA database under {a.mfa_root} — pass --db or --mfa-out")
        a.db = str(max(hits, key=lambda q: q.stat().st_mtime))
        print(f"  [mfa] database {a.db}")

    mfa_utts = utterances_from_db(a.db) if a.db else utterances_from_textgrids(a.mfa_out, side["utterances"])
    print(f"  [mfa] {len(mfa_utts)} aligned utterances, {sum(len(r) for _, _, r in mfa_utts)} words")

    # pair each MFA utterance with the corpus utterance it came from (same speaker, nearest start)
    final, used, n_missing_utt, n_mismatch = [], set(), 0, 0
    for spk, begin, rows in mfa_utts:
        cands = [(i, u) for i, u in enumerate(side["utterances"]) if u["speaker"] == spk and i not in used]
        if not cands:
            continue
        i, u = min(cands, key=lambda c: abs(c[1]["start"] - begin))
        if abs(u["start"] - begin) > 0.5:
            print(f"  [warn] MFA utterance at {begin:.2f}s ({spk}) has no close corpus utterance — skipped")
            continue
        used.add(i)
        got = match_utterance(rows, u["words"])
        n_mismatch += sum(1 for g in got if g[3] == "whisper")
        final += [(spk, s, e, w, src) for s, e, w, src in got]
    n_missing_utt = len(side["utterances"]) - len(used)
    final.sort(key=lambda r: r[1])

    n_corpus = sum(len(u["words"]) for u in side["utterances"])
    print(f"  [map ] {len(final)}/{n_corpus} words placed; {n_mismatch} kept Whisper's timing (MFA merged or "
          f"dropped them — check these in Praat)"
          + (f"; {n_missing_utt} utterance(s) MFA did not align" if n_missing_utt else ""))
    if n_mismatch > 0.15 * n_corpus:
        print("  [warn] >15% of words fell back to Whisper timing — check the MFA log before using this file")

    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    tg = ptg.Textgrid()
    for spk in sorted({r[0] for r in final}):
        ents, last = [], 0.0
        for _, s, e, w, _src in [r for r in final if r[0] == spk]:
            s, e = max(s, last), min(e, dur)
            if e - s > 1e-6:
                ents.append((s, e, w)); last = e
        tg.addTier(ptg.IntervalTier(spk, ents, 0, dur))
    tg.save(str(out / f"{stem}_words.TextGrid"), format="long_textgrid", includeBlankSpaces=True)

    speakers = sorted({r[0] for r in final})
    rows = [{"onset": round(s * 1000, 2), "offset": round(e * 1000, 2), "Duration": round((e - s) * 1000, 2),
             **{sp: (w if sp == spk else "") for sp in speakers}, "timing_source": src}
            for spk, s, e, w, src in final]
    pd.DataFrame(rows, columns=["onset", "offset", "Duration"] + speakers + ["timing_source"]).to_excel(
        out / f"{stem}_words.xlsx", index=False)
    print(f"[done] {len(final)} words, speakers {speakers}")
    print(f"       -> {out / (stem + '_words.TextGrid')}\n       -> {out / (stem + '_words.xlsx')}")


if __name__ == "__main__":
    main()
