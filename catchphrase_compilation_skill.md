# YouTube Catchphrase Compilation — Claude Code Skill

A repeatable pipeline for scanning a YouTube channel, finding every instance
of a spoken phrase, and compiling matching clips into a supercut video.

**Test bed:** The phrase `"permission structure"` on the IHIP News podcast channel.

---

## Overview

```
Channel URL + Phrase
       │
       ▼
catchphrase_finder.py     ← scans channel, downloads transcripts (.vtt)
       │
       ▼
vtt_search.py             ← searches all .vtt files, produces results JSON
       │
       ▼
clip_downloader.py        ← user reviews hits, downloads clips, builds supercut
```

---

## Environment

| Tool      | Install                          | Purpose                        |
|-----------|----------------------------------|--------------------------------|
| Python 3  | Anaconda (`/anaconda3/bin/python3`) | Runtime                     |
| yt-dlp    | `pip install yt-dlp`             | Video/transcript downloader    |
| rich      | `conda install -c conda-forge rich` | Terminal UI / progress bars |
| ffmpeg    | `brew install ffmpeg`            | Clip extraction + supercut     |

> **Important:** Always run with `python3`, not `python`. Both `python3` and
> `pip` must resolve to the same Anaconda environment. Verify with:
> ```bash
> which python3 && which pip && python3 -c "import rich; print('rich OK')"
> ```

---

## Scripts

### 1. `catchphrase_finder.py`
Fetches the full video list from a YouTube channel, downloads auto-generated
captions (`.vtt`) for every video, and searches them for the target phrase.

**Config block (top of file):**
```python
CHANNEL_URL    = ""       # e.g. "https://www.youtube.com/@SomeChannel"
CATCHPHRASE    = ""       # e.g. "permission structure"
OUTPUT_DIR     = "./catchphrase_output"
DOWNLOAD_CLIPS = False    # keep False for large channels
CLIP_PADDING   = 3        # seconds before/after hit
MAX_VIDEOS     = None     # None = entire channel; set a number to test
FUZZY_MATCH    = True     # case-insensitive
```

**Outputs:**
- `catchphrase_output/transcripts/*.vtt` — one file per video
- `catchphrase_output/results_[timestamp].json` — hits with timestamps
- `catchphrase_output/results_[timestamp].txt` — human-readable report

**Known issue:** The results JSON captures only transcripts downloaded
at the moment the script ends. If the channel is large (2,000+ videos),
the JSON may show 0 hits even when VTT files contain matches. Always
follow up with `vtt_search.py` to search the full transcript folder.

**VTT duplication:** YouTube's `.vtt` format repeats caption blocks. Even after
deduplication at parse time, the search may find the same phrase occurrence
multiple times with slightly different timestamp windows. This is expected and
can be cleaned up post-search (see "Deduplication" section below).

**Run:**
```bash
python3 catchphrase_finder.py
```

---

### 2. `vtt_search.py`
Searches the entire `transcripts/` folder of `.vtt` files directly —
bypasses the JSON timing issue entirely. This is the authoritative
search step for large channels.

**Config block:**
```python
TRANSCRIPTS_DIR = "./catchphrase_output/transcripts"
OUTPUT_DIR      = "./catchphrase_output"
PHRASE          = "permission structure"   # or leave blank to be prompted
MAX_FEED_LINES  = 12
```

**Live dashboard while running:**
- Stats panel — files scanned / total / matched videos / hits found
- Live hits feed — scrolling view of every new match as it's found
- Progress bar — count, percentage, elapsed time, ETA

**Outputs:**
- `catchphrase_output/vtt_search_results_[timestamp].json` — feed into `clip_downloader.py`
- `catchphrase_output/vtt_search_results_[timestamp].txt` — human-readable with clickable links

**Run:**
```bash
python3 vtt_search.py
```

---

### 3. `clip_downloader.py`
Reads a results JSON, presents a numbered review table of all hits,
lets the user approve/reject clips, downloads only selected segments,
and optionally stitches them into a supercut.

**Config block:**
```python
RESULTS_JSON   = "./catchphrase_output/vtt_search_results_*.json"  # auto-picks latest
OUTPUT_DIR     = "./catchphrase_output/clips"
CLIP_PADDING   = 4        # seconds before/after hit
VIDEO_QUALITY  = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
BUILD_SUPERCUT = True
SUPERCUT_NAME  = "supercut.mp4"
SKIP_EXISTING  = True     # won't re-download clips already on disk
```

> After running `vtt_search.py`, update `RESULTS_JSON` to point at the
> `vtt_search_results_*.json` pattern instead of `results_*.json`.

**Curation options at runtime:**
| Command | Effect |
|---------|--------|
| `all`   | Approve every hit, start downloading |
| `pick`  | Enter numbers to keep, e.g. `1 3 5-8 12` |
| `skip`  | Enter numbers to remove, e.g. `2 4 9` |
| `none`  | Reject all, then pick manually |
| `go`    | Proceed with current selection |

**Supercut:** Uses ffmpeg concat demuxer (`-c copy`) — no re-encoding,
very fast. Output is `clips/supercut.mp4`.

**Run:**
```bash
python3 clip_downloader.py
```

---

## Folder Structure

```
catchphrase/                        ← project root (VS Code workspace)
├── catchphrase_finder.py
├── vtt_search.py
├── clip_downloader.py
└── catchphrase_output/
    ├── transcripts/
    │   ├── ABC123.en.vtt
    │   ├── XYZ789.en.vtt
    │   └── ...                     ← one per video (2,666 for IHIP News)
    ├── results_[timestamp].json    ← from catchphrase_finder (may be incomplete)
    ├── results_[timestamp].txt
    ├── vtt_search_results_[timestamp].json   ← authoritative, use this
    ├── vtt_search_results_[timestamp].txt
    └── clips/
        ├── 001_Video_Title_ABC123.mp4
        ├── 002_Video_Title_XYZ789.mp4
        └── supercut.mp4
```

---

## Full Workflow (Step by Step)

```bash
# 1. Scan channel and download all transcripts (long — allow hours for large channels)
python3 catchphrase_finder.py
# Enter channel URL and phrase when prompted
# Let it run fully before proceeding

# 2. While it runs, check for hits in a second terminal
grep -ri "permission structure" catchphrase_output/transcripts/ | sort -u

# 3. After catchphrase_finder finishes, run the authoritative search
python3 vtt_search.py

# 4. Review the TXT report, then download and compile clips
python3 clip_downloader.py
```

---

## Deduplication (Post-Search)

After running `vtt_search.py`, you may have duplicate or near-duplicate hits from
the same occurrence captured at different timestamp boundaries due to VTT format quirks.

**To deduplicate:**

1. Load the `vtt_search_results_*.json` file
2. Group hits by video ID
3. For each video, cluster hits that overlap or are within 2 seconds of each other
4. Keep only the longest/most comprehensive hit from each cluster
5. Save as a new deduplicated JSON
6. Run `clip_downloader.py` with the deduplicated JSON

**Example Python deduplication:**
```python
import json
from pathlib import Path

# Load search results
results_file = Path('catchphrase_output/vtt_search_results_*.json')
with open(results_file) as f:
    results = json.load(f)

def cluster_overlapping_hits(hits):
    hits = sorted(hits, key=lambda h: h['start_sec'])
    clusters = []
    current_cluster = [hits[0]]
    for hit in hits[1:]:
        cluster_end = max(h['end_sec'] for h in current_cluster)
        if hit['start_sec'] <= cluster_end + 2:
            current_cluster.append(hit)
        else:
            clusters.append(current_cluster)
            current_cluster = [hit]
    clusters.append(current_cluster)
    return clusters

# Deduplicate each video's hits
for video in results:
    clusters = cluster_overlapping_hits(video['hits'])
    video['hits'] = [max(c, key=lambda h: h['end_sec'] - h['start_sec']) 
                     for c in clusters]

# Save deduplicated results
with open('catchphrase_output/vtt_search_results_dedup.json', 'w') as f:
    json.dump(results, f, indent=2)
```

**Impact:** Typical reduction is 50-70% of hits, resulting in a cleaner, more concise supercut
without redundant occurrences of the same phrase moment.

---

## Lessons Learned (IHIP News Test)

- **Channel size:** 2,666 videos; transcript scan takes several hours
- **Hit rate:** ~1 in 12 videos contained "permission structure" across the
  first 272 scanned — projected 200+ total hits for the full channel
- **VTT duplicates:** YouTube's `.vtt` format repeats every caption block.
  All three scripts handle deduplication at parse time
- **JSON timing bug:** `catchphrase_finder.py` writes its JSON at exit;
  for large channels the JSON will show 0 hits because transcripts
  hadn't been downloaded yet when the search ran. `vtt_search.py` was
  written specifically to solve this by searching the folder directly
- **Python environment:** Must use `python3` (Anaconda). Using bare `python`
  invokes macOS system Python which doesn't have the installed packages
- **rich install on Anaconda:** Use `conda install -c conda-forge rich`,
  not `pip install rich`, to avoid environment conflicts

---

## Adapting This Skill to a New Channel

1. Create a new project folder
2. Copy the three scripts in
3. Edit the `CONFIG` block at the top of each script:
   - `CHANNEL_URL` → target channel
   - `CATCHPHRASE` / `PHRASE` → target phrase
   - `OUTPUT_DIR` / `TRANSCRIPTS_DIR` → point to new folder
4. Run the pipeline in order

The scripts are phrase- and channel-agnostic. Any YouTube channel with
auto-captions and any spoken phrase works out of the box.

---

## Potential Enhancements

- [ ] Whisper fallback for videos with no auto-captions
- [ ] Multi-phrase search (search for several phrases in one pass)
- [ ] Add video titles to `vtt_search.py` output by cross-referencing
      a `videos.json` manifest from `yt-dlp --flat-playlist`
- [ ] Clip trimming UI — review each clip before stitching the supercut
- [ ] Transition/crossfade between clips in the supercut (requires re-encode)
- [ ] Export an EDL or Premiere XML so clips can be edited in a proper NLE
- [ ] Web UI wrapper (Flask/FastAPI) for non-technical collaborators
