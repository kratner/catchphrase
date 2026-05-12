# Catchphrase Compilation

A YouTube channel scanner that finds every instance of a spoken phrase and compiles them into a supercut video.

## Features

- **Automatic transcript download** — fetches captions from entire YouTube channels (including auto-generated ones)
- **Smart search** — case-insensitive phrase matching across thousands of videos in seconds
- **Clip curation** — review and approve/reject individual hits before downloading
- **One-command supercut** — automatically stitch approved clips into a seamless video with ffmpeg

## Quick Start

**Typical Workflow:**
1. Download transcripts from your channel
2. Search for phrase
3. ⭐ **Deduplicate** search results (removes ~50-70% of VTT artifacts)
4. Download and compile clips
5. Review supercut

### 1. Install Dependencies

```bash
# Python 3 (via Anaconda)
python3 --version

# yt-dlp (YouTube downloader)
pip install yt-dlp

# rich (terminal UI)
conda install -c conda-forge rich

# ffmpeg (video processing)
brew install ffmpeg
```

Verify setup:
```bash
python3 -c "import rich; print('✓ All dependencies installed')"
```

### 2. Run the Pipeline

```bash
# Step 1: Download transcripts from entire channel (takes hours for large channels)
python3 catchphrase_finder.py

# Step 2: Search transcripts for your phrase (fast, authoritative)
python3 vtt_search.py

# Step 3: Download clips and build supercut
python3 clip_downloader.py
```

## How It Works

```
YouTube Channel
      ↓
1. catchphrase_finder.py  → Downloads all captions (.vtt files)
      ↓
2. vtt_search.py          → Finds every match in transcripts
      ↓
3. clip_downloader.py     → Downloads clips + builds supercut
      ↓
supercut.mp4
```

## Configuration

Each script has a `CONFIG` section at the top. Edit these before running:

**catchphrase_finder.py:**
```python
CHANNEL_URL    = "https://www.youtube.com/@YourChannel"
CATCHPHRASE    = "your phrase here"
MAX_VIDEOS     = None  # Set to a number to test on a subset
CLIP_PADDING   = 3     # Seconds before/after the hit
```

**vtt_search.py:**
```python
PHRASE = "your phrase here"
TRANSCRIPTS_DIR = "./catchphrase_output/transcripts"
```

**clip_downloader.py:**
```python
RESULTS_JSON   = "./catchphrase_output/vtt_search_results_*.json"
CLIP_PADDING   = 4  # Can differ from finder
BUILD_SUPERCUT = True
SKIP_EXISTING  = True  # Don't re-download clips already saved
```

## Curating Clips

When `clip_downloader.py` runs, it shows all found hits and lets you select which to include:

| Command | Effect |
|---------|--------|
| `all`   | Include all clips |
| `none`  | Include no clips (then pick manually) |
| `pick`  | Enter numbers: `1 3 5-8 12` |
| `skip`  | Enter numbers to exclude: `2 4 9` |
| `go`    | Proceed with current selection |

## Output Files

All output goes to `catchphrase_output/`:

```
catchphrase_output/
├── transcripts/             ← VTT files (one per video)
├── vtt_search_results_*.json  ← Hit list with timestamps
└── clips/
    ├── 001_Video_Title.mp4
    ├── 002_Video_Title.mp4
    └── supercut.mp4         ← Final output
```

## Common Issues

**Python not finding `rich` or `yt-dlp`**
- Verify you're using Anaconda Python: `which python3`
- Re-install: `pip install yt-dlp` and `conda install -c conda-forge rich`

**No matches found**
- Check phrase capitalization and spacing
- Manually search a transcript to verify: `grep "phrase" catchphrase_output/transcripts/*.vtt`

**Large channels taking too long**
- Run `vtt_search.py` while `catchphrase_finder.py` is still downloading (they don't conflict)
- Use `grep` directly for a quick check: `grep -ri "phrase" catchphrase_output/transcripts/ | wc -l`

**JSON shows 0 hits but VTT files have matches**
- This is expected on large channels. Always use `vtt_search.py` to get authoritative results.

## Example: "Permission Structure" on IHIP News

This skill was tested on the IHIP News podcast (2,666 videos). The phrase "permission structure" appeared in ~1 in 12 videos, yielding 200+ clips for the supercut.

## Adapting to Your Channel

1. Create a new folder: `mkdir catchphrase_my_channel`
2. Copy the three scripts into it
3. Edit the `CONFIG` block in each script with your channel URL and phrase
4. Run the pipeline in order (steps 1–3 above)

The scripts are phrase- and channel-agnostic — any YouTube channel with auto-captions works.

## Potential Enhancements

- [ ] Whisper fallback for channels without auto-captions
- [ ] Multi-phrase search in one pass
- [ ] Clip preview before supercut
- [ ] Transitions/crossfades between clips
- [ ] Export to Premiere XML for professional editing
- [ ] Web UI for non-technical users
