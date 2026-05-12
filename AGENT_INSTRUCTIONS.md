# Agent Instructions: Resuming Catchphrase Compilation Searches

## Quick Status

**Current State (as of 2026-05-12):**
- ✓ IHIP News search: Complete (85 videos, 213 hits)
- ✓ Biweekly supercut: Complete and validated (20 clips, 1m 45s)
- ⏸ 3-week supercut: Prepared but blocked by rate limit (213 clips ready to download)
- ⏸ @adammockler search: Not started (4,150 videos available)

**Blocker:** YouTube rate-limiting all operations (video downloads, transcript downloads). Expected reset: ~2026-05-14.

See `ACTIVITY_LOG.json` for detailed status.

---

## How to Resume on Another Machine

### 1. Clone and Setup
```bash
git clone <repo>
cd catchphrase
pip install yt-dlp rich
brew install ffmpeg  # or: sudo apt install ffmpeg
```

### 2. Check Current Status
```bash
cat ACTIVITY_LOG.json | jq '.rate_limit_status'
```

### 3. Resume IHIP News 3-Week Supercut (once rate limit clears)

**Before starting:** 
```bash
# Update yt-dlp to latest version
pip install --upgrade yt-dlp

# Verify Node.js is installed (required for JavaScript n-challenge solving)
which node  # should return path like /usr/bin/node or /usr/local/bin/node
node --version  # should show v14+
```

**Step 1: Download clips (with JavaScript challenge solver and rate-limit prevention)**
```bash
python3 << 'EOF'
import json
import subprocess
from pathlib import Path
import os
import time

# Configuration from ACTIVITY_LOG
source_json = "./catchphrase_output/clips_3week_2026-04-21_to_2026-05-12/vtt_search_results_dedup.json"
output_dir = Path("./catchphrase_output/clips_3week_2026-04-21_to_2026-05-12")
clip_padding = 2

with open(source_json) as f:
    results = json.load(f)

clips = []
for video in results:
    for hit in video['hits']:
        clips.append({
            'video_id': video['id'],
            'start_sec': hit['start_sec'],
            'end_sec': hit['end_sec']
        })

print(f"Downloading {len(clips)} clips with {clip_padding}s padding")
print(f"Using 15s sleep between downloads to avoid rate limiting\n")

downloaded = []
for idx, clip in enumerate(clips, 1):
    video_id = clip['video_id']
    start = max(0, clip['start_sec'] - clip_padding)
    end = clip['end_sec'] + clip_padding
    duration = end - start
    
    filename = f"{idx:03d}_{video_id}.mp4"
    output_path = output_dir / filename
    
    if output_path.exists() and output_path.stat().st_size > 100000:
        if idx % 50 == 1:
            print(f"[{idx}/{len(clips)}] ✓ (cached)")
        downloaded.append(str(output_path))
        continue
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    # Get Node.js path for JavaScript challenge solving
    node_path = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
    
    cmd = [
        "yt-dlp",
        "--js-runtimes", f"node:{node_path}",  # Use Node.js for n-challenge solving
        "--remote-components", "ejs:github",  # Download challenge solver from GitHub
        "--cookies-from-browser", "chrome",  # or firefox, safari, edge (higher rate limit)
        "--sleep-interval", "15",  # Wait 15 seconds between downloads
        "-f", "best[ext=mp4]",
        "-o", str(output_path),
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if output_path.exists() and output_path.stat().st_size > 100000:
            if idx % 50 == 1:
                print(f"[{idx}/{len(clips)}] ✓")
            downloaded.append(str(output_path))
        else:
            if idx % 50 == 1:
                print(f"[{idx}/{len(clips)}] ✗")
    except subprocess.TimeoutExpired:
        if idx % 50 == 1:
            print(f"[{idx}/{len(clips)}] ✗ (timeout)")
    except Exception as e:
        if idx % 50 == 1:
            print(f"[{idx}/{len(clips)}] ✗ ({str(e)[:30]})")

print(f"\nDownloaded {len(downloaded)} clips")
EOF
```

**Rate Limit Notes:**
- Guest sessions: ~300 videos/hour
- Authenticated sessions (with cookies): ~2000 videos/hour
- `--cookies-from-browser`: Extracts cookies from logged-in browser (Chrome/Firefox/Safari/Edge)
- `--sleep-interval 15`: Waits 15 seconds between downloads (mimic human behavior)

**Step 2: Build supercut**
```bash
cd catchphrase_output/clips_3week_2026-04-21_to_2026-05-12

# Create concat file
find . -maxdepth 1 -name "*.mp4" ! -name "supercut.mp4" | sort | \
  sed 's/^\.\///' | sed "s/^/file '/" | sed "s/$/'/\" > concat.txt

# Build supercut
ffmpeg -f concat -safe 0 -i concat.txt -c copy -y supercut.mp4
```

### 4. Start @adammockler Search (once rate limit clears)

**Step 1: Download transcripts (with rate-limit prevention)**
```bash
# First, update yt-dlp
yt-dlp -U

python3 << 'EOF'
import subprocess
import json
from pathlib import Path
import time

output_base = "./catchphrase_output/adammockler_search"
transcripts_dir = Path(output_base) / "transcripts"
transcripts_dir.mkdir(parents=True, exist_ok=True)

# Get video list
channel_url = "https://www.youtube.com/@adammockler"
cmd = ["yt-dlp", "--flat-playlist", "-j", channel_url]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

videos = []
for line in result.stdout.strip().split('\n'):
    if line.strip():
        try:
            data = json.loads(line)
            if 'id' in data:
                videos.append(data['id'])
        except:
            pass

print(f"Found {len(videos)} videos\n")
print("Downloading transcripts with rate-limit prevention:")
print("- Using authenticated cookies (higher limit ~2000/hour vs 300/hour guest)")
print("- 20s sleep between subtitle requests\n")

# Download transcripts
downloaded = 0
for idx, video_id in enumerate(videos, 1):
    transcript_path = transcripts_dir / f"{video_id}.en.vtt"
    
    if transcript_path.exists():
        downloaded += 1
        continue
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    # Get Node.js path for JavaScript challenge solving
    node_path = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
    
    cmd = [
        "yt-dlp",
        "--js-runtimes", f"node:{node_path}",  # Use Node.js for n-challenge solving
        "--remote-components", "ejs:github",  # Download challenge solver from GitHub
        "--cookies-from-browser", "chrome",  # or firefox, safari, edge
        "--write-auto-subs",
        "--sub-langs", "en",
        "--sleep-subtitles", "20",  # 20 seconds between subtitle requests
        "--skip-download",
        "-o", str(transcripts_dir / "%(id)s"),
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if transcript_path.exists():
            downloaded += 1
            if idx % 100 == 0:
                print(f"[{idx}/{len(videos)}] ✓ {downloaded} transcripts")
    except:
        if idx % 100 == 0:
            print(f"[{idx}/{len(videos)}] ✗")

print(f"\nDownloaded {downloaded}/{len(videos)} transcripts")
EOF
```

**Step 2: Search transcripts**
```bash
python3 vtt_search.py
# When prompted for phrase, enter: permission structure
```

**Step 3: Deduplicate and download (same as IHIP News process above)**

---

## Key Files

- `ACTIVITY_LOG.json` - Detailed status of all activities
- `SEARCHES.md` - Human-readable summary
- `catchphrase_output/vtt_search_results_fresh_3week.json` - IHIP News search results
- `catchphrase_output/clips_3week_2026-04-21_to_2026-05-12/` - IHIP News 3-week folder (prepared)
- `catchphrase_output/clips_biweekly/` - IHIP News biweekly supercut (complete)

---

## Troubleshooting

**If downloads fail with "n challenge solving failed" error:**

YouTube is blocking the download with an anti-bot n-parameter challenge that requires JavaScript runtime to solve.

*Solution:*
1. Ensure Node.js is installed: `which node` (if not, install via `brew install node`)
2. Add these flags to yt-dlp commands:
   ```
   --js-runtimes node:/path/to/node
   --remote-components ejs:github
   ```
3. These flags enable JavaScript challenge solving (first run downloads the solver from GitHub)

This is **NOT** the same as rate limiting—this is a permanent anti-bot measure that requires these flags.

**If downloads fail with HTTP 429, empty files, or missing formats:**

YouTube rate limiting detected. Guest sessions limited to ~300 videos/hour.

*Immediate fixes:*
- Wait 15-60 minutes (usually resets in 15-60 min, worst case 24 hours)
- Update yt-dlp: `yt-dlp -U`
- Use cookies from logged-in browser: `--cookies-from-browser chrome` (raises limit to ~2000/hour)
- Add sleep delays: `--sleep-interval 15` (between downloads) or `--sleep-subtitles 20` (between subtitles)

*If still failing:*
- Switch VPN to different exit IP (caveat: may violate YouTube ToS)
- Check browser is logged into YouTube before using `--cookies-from-browser`

**If transcripts won't download:**
- Same as above — YouTube rate limiting applies to transcripts too
- Use `--sleep-subtitles 20` for transcript-specific throttling
- Must wait or use authenticated cookies

**If ffmpeg concat fails:**
- Ensure all .mp4 files are valid: `ffmpeg -i <file.mp4>` (should show Duration and streams)
- Verify concat.txt format: each line should be `file '/path/to/clip.mp4'`
- All files must be from same source (same video codec) for concat demuxer

**Rate limit reference:**
- Guest session: ~300 videos/hour
- Authenticated session: ~2000 videos/hour (use `--cookies-from-browser`)
- Sleep between requests mitigates but doesn't eliminate limits

---

## Next Agent Checklist

- [ ] Check `ACTIVITY_LOG.json` for current status
- [ ] Verify YouTube rate limit has cleared (check as-of date vs current date)
- [ ] Resume appropriate task:
  - [ ] IHIP News 3-week supercut (download + build)
  - [ ] @adammockler search (download transcripts + search + download clips + build)
- [ ] Update `ACTIVITY_LOG.json` with completion status
- [ ] Commit updated activity log to GitHub
