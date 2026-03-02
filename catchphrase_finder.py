#!/usr/bin/env python3
"""
YouTube Catchphrase Finder
--------------------------
Scans all videos on a YouTube channel for a specific catchphrase,
extracts timestamps, and optionally downloads the matching clips.

Requirements:
    pip install yt-dlp rich
    brew install ffmpeg  (or: sudo apt install ffmpeg)

Usage:
    python catchphrase_finder.py
"""

import re
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── Rich imports ──────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn,
        TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn, MofNCompleteColumn
    )
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.rule import Rule
    from rich import box
    import rich.traceback
    rich.traceback.install()
except ImportError:
    print("Missing dependency: pip install rich")
    sys.exit(1)

console = Console()

# ─────────────────────────────────────────────
# CONFIG — edit these or leave blank to be prompted
# ─────────────────────────────────────────────
CHANNEL_URL    = ""       # e.g. "https://www.youtube.com/@SomeChannel"
CATCHPHRASE    = ""       # e.g. "and that's a wrap"
OUTPUT_DIR     = "./catchphrase_output"
DOWNLOAD_CLIPS = False    # Set True to auto-download matching clips
CLIP_PADDING   = 3        # Seconds before/after phrase for context
MAX_VIDEOS     = None     # Limit scan to N videos (None = all)
FUZZY_MATCH    = True     # Case-insensitive partial matching
# ─────────────────────────────────────────────


# ── Helpers ───────────────────────────────────────────────────────────────────

def seconds_to_hms(s):
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def vtt_time_to_seconds(ts):
    ts = ts.split(".")[0]
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return int(parts[0])


# ── Config & dependency setup ─────────────────────────────────────────────────

def prompt_config():
    global CHANNEL_URL, CATCHPHRASE, DOWNLOAD_CLIPS

    console.print()
    console.print(Panel.fit(
        "[bold yellow]🎬 YouTube Catchphrase Finder[/bold yellow]\n"
        "[dim]Scan an entire channel and extract every moment a phrase is spoken[/dim]",
        border_style="yellow"
    ))
    console.print()

    if not CHANNEL_URL:
        CHANNEL_URL = Prompt.ask("[cyan]YouTube channel URL[/cyan]")
    if not CATCHPHRASE:
        CATCHPHRASE = Prompt.ask("[cyan]Catchphrase to search for[/cyan]")
    DOWNLOAD_CLIPS = Confirm.ask("[cyan]Download matching clips?[/cyan]", default=False)
    console.print()


def check_dependencies():
    deps = [("yt-dlp", ["yt-dlp", "--version"], "pip install yt-dlp")]
    if DOWNLOAD_CLIPS:
        deps.append(("ffmpeg", ["ffmpeg", "-version"], "brew install ffmpeg  OR  sudo apt install ffmpeg"))

    table = Table(title="Dependency Check", box=box.ROUNDED, border_style="dim")
    table.add_column("Tool",              style="bold")
    table.add_column("Status")
    table.add_column("Install if missing", style="dim")

    all_ok = True
    for name, cmd, install in deps:
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            table.add_row(name, "[green]✔  Found[/green]", "")
        except (subprocess.CalledProcessError, FileNotFoundError):
            table.add_row(name, "[red]✘  Missing[/red]", install)
            all_ok = False

    console.print(table)
    console.print()

    if not all_ok:
        console.print("[red bold]Please install missing dependencies and re-run.[/red bold]")
        sys.exit(1)


# ── Video discovery ───────────────────────────────────────────────────────────

def get_channel_videos(channel_url, max_videos=None):
    cmd = [
        "yt-dlp", "--flat-playlist",
        "--print", "%(id)s\t%(title)s\t%(duration)s",
        "--no-warnings",
    ]
    if max_videos:
        cmd += ["--playlist-end", str(max_videos)]
    cmd.append(channel_url)

    with console.status("[bold cyan]Fetching video list from channel…[/bold cyan]", spinner="dots"):
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]yt-dlp error:[/red]\n{result.stderr}")
        sys.exit(1)

    videos = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            videos.append({
                "id":       parts[0],
                "title":    parts[1],
                "duration": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
            })

    console.print(f"[green]✔[/green]  Found [bold]{len(videos)}[/bold] videos on channel.\n")
    return videos


# ── Transcript fetch & parse ──────────────────────────────────────────────────

def download_transcript(video_id, out_dir):
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp", "--skip-download",
        "--write-auto-subs", "--write-subs",
        "--sub-lang", "en", "--sub-format", "vtt",
        "--no-warnings",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        url,
    ]
    subprocess.run(cmd, capture_output=True)
    matches = list(out_dir.glob(f"{video_id}*.vtt"))
    return matches[0] if matches else None


def parse_vtt(vtt_path):
    text = vtt_path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"WEBVTT.*?\n\n", "", text, flags=re.DOTALL, count=1)
    segments = []
    for block in re.split(r"\n\n+", text.strip()):
        lines = block.strip().splitlines()
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue
        m = re.match(r"(\S+)\s+-->\s+(\S+)", ts_line)
        if not m:
            continue
        start = vtt_time_to_seconds(m.group(1))
        end   = vtt_time_to_seconds(m.group(2))
        caption = " ".join(l for l in lines if "-->" not in l and not re.match(r"^\d+$", l))
        caption = re.sub(r"<[^>]+>", "", caption).strip()
        if caption:
            segments.append({"start_sec": start, "end_sec": end, "text": caption})
    return segments


def search_segments(segments, phrase):
    needle = phrase.lower() if FUZZY_MATCH else phrase
    hits = []
    for seg in segments:
        haystack = seg["text"].lower() if FUZZY_MATCH else seg["text"]
        if needle in haystack:
            hits.append(seg)
    return hits


# ── Clip download ─────────────────────────────────────────────────────────────

def download_clip(video_id, start_sec, end_sec, out_path):
    url   = f"https://www.youtube.com/watch?v={video_id}"
    start = max(0, start_sec - CLIP_PADDING)
    end   = end_sec + CLIP_PADDING
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--download-sections", f"*{seconds_to_hms(start)}-{seconds_to_hms(end)}",
        "--force-keyframes-at-cuts",
        "-o", str(out_path),
        "--no-warnings",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


# ── Results output ────────────────────────────────────────────────────────────

def print_hit_table(results):
    total_hits = sum(len(r["hits"]) for r in results)
    if total_hits == 0:
        console.print(Panel("[yellow]No matches found for that phrase.[/yellow]", border_style="yellow"))
        return

    table = Table(
        title=f'[bold]All Hits for "[yellow]{CATCHPHRASE}[/yellow]"[/bold]',
        box=box.ROUNDED, border_style="cyan", show_lines=True,
        header_style="bold cyan"
    )
    table.add_column("#",         style="dim",      width=4,  justify="right")
    table.add_column("Video",     style="bold",     min_width=28, max_width=42)
    table.add_column("Timestamp", style="green",    width=10)
    table.add_column("Caption",   style="white",    min_width=30)
    table.add_column("Link",      style="blue dim", min_width=36)

    n = 0
    for r in results:
        for hit in r["hits"]:
            n += 1
            yt_ts = int(hit["start_sec"])
            highlighted = re.sub(
                re.escape(CATCHPHRASE),
                f"[bold yellow]{CATCHPHRASE}[/bold yellow]",
                hit["text"], flags=re.IGNORECASE
            )
            table.add_row(
                str(n),
                r["title"][:42],
                seconds_to_hms(hit["start_sec"]),
                highlighted,
                f"https://youtu.be/{r['id']}?t={yt_ts}",
            )

    console.print()
    console.print(table)


def save_results(results, out_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"results_{ts}.json"
    json_path.write_text(json.dumps(results, indent=2))

    txt_path = out_dir / f"results_{ts}.txt"
    total_hits = sum(len(r["hits"]) for r in results)
    lines = [
        "YouTube Catchphrase Search Results",
        f'Phrase   : "{CATCHPHRASE}"',
        f"Channel  : {CHANNEL_URL}",
        f"Date     : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Total hits: {total_hits}",
        "=" * 60, "",
    ]
    for r in results:
        if r["hits"]:
            lines.append(f"📺  {r['title']}")
            lines.append(f"    https://www.youtube.com/watch?v={r['id']}")
            for hit in r["hits"]:
                yt_ts = int(hit["start_sec"])
                lines.append(f"    ⏱  {seconds_to_hms(hit['start_sec'])}  →  \"{hit['text']}\"")
                lines.append(f"       Direct: https://youtu.be/{r['id']}?t={yt_ts}")
            lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def print_summary(results, json_path, txt_path, clips_dir, elapsed):
    total      = len(results)
    hits_vids  = sum(1 for r in results if r["hits"])
    no_cap     = sum(1 for r in results if r.get("note") == "no transcript")
    total_hits = sum(len(r["hits"]) for r in results)

    stats = Table.grid(expand=True, padding=(0, 4))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")

    def stat_cell(value, label, color="white"):
        return f"[{color} bold]{value}[/{color} bold]\n[dim]{label}[/dim]"

    stats.add_row(
        stat_cell(total,      "videos scanned", "cyan"),
        stat_cell(total_hits, "total hits",     "yellow"),
        stat_cell(hits_vids,  "videos matched", "green"),
        stat_cell(no_cap,     "no captions",    "red"),
    )

    console.print()
    console.print(Rule("[bold cyan]Search Complete[/bold cyan]"))
    console.print()
    console.print(Panel(stats, title="[bold]Results Summary[/bold]", border_style="cyan", padding=(1, 4)))

    files = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    files.add_column(style="dim", width=14)
    files.add_column(style="cyan")
    files.add_row("📄 Text report", str(txt_path))
    files.add_row("📦 JSON data",   str(json_path))
    if DOWNLOAD_CLIPS and clips_dir:
        files.add_row("🎬 Clips dir",   str(clips_dir))

    console.print(Panel(files, title="[bold]Output Files[/bold]", border_style="dim"))
    console.print(f"\n[dim]Total runtime: {elapsed}[/dim]\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    prompt_config()
    check_dependencies()

    out_dir         = Path(OUTPUT_DIR)
    transcripts_dir = out_dir / "transcripts"
    clips_dir       = out_dir / "clips"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    if DOWNLOAD_CLIPS:
        clips_dir.mkdir(parents=True, exist_ok=True)

    videos     = get_channel_videos(CHANNEL_URL, MAX_VIDEOS)
    results    = []
    total_hits = 0
    start_time = datetime.now()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=36),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:

        scan_task  = progress.add_task("[cyan]Scanning videos…[/cyan]", total=len(videos))
        fetch_task = progress.add_task("[blue]  ↳ Fetching transcript[/blue]", total=1, visible=False)

        for video in videos:
            vid_id = video["id"]
            title  = video["title"]
            short  = (title[:44] + "…") if len(title) > 45 else title

            progress.update(scan_task, description=f"[cyan]Scanning:[/cyan] [white]{short}[/white]")

            # Fetch transcript
            progress.update(fetch_task, description="[blue]  ↳ Fetching transcript…[/blue]",
                            completed=0, visible=True)
            vtt_file = download_transcript(vid_id, transcripts_dir)
            progress.update(fetch_task, completed=1, visible=False)

            if not vtt_file:
                progress.console.print(f"  [yellow]⚠[/yellow]  [dim]{short}[/dim]  [yellow]no captions available[/yellow]")
                results.append({**video, "hits": [], "note": "no transcript"})
                progress.advance(scan_task)
                continue

            # Parse & search
            segments = parse_vtt(vtt_file)
            hits     = search_segments(segments, CATCHPHRASE)

            if hits:
                total_hits += len(hits)
                n_label = f"{len(hits)} hit{'s' if len(hits) > 1 else ''}"
                progress.console.print(f"  [bold green]✔  {n_label}[/bold green]  [white]{short}[/white]")

                for hit in hits:
                    ts  = seconds_to_hms(hit["start_sec"])
                    cap = re.sub(
                        re.escape(CATCHPHRASE),
                        f"[bold yellow]{CATCHPHRASE}[/bold yellow]",
                        hit["text"], flags=re.IGNORECASE
                    )
                    progress.console.print(f"       [green]⏱ {ts}[/green]  {cap}")

                if DOWNLOAD_CLIPS:
                    clip_task = progress.add_task(
                        f"[magenta]  ↳ Downloading {len(hits)} clip(s)…[/magenta]",
                        total=len(hits)
                    )
                    for j, hit in enumerate(hits, 1):
                        safe  = re.sub(r'[^\w\-]', '_', title)[:40]
                        cpath = clips_dir / f"{safe}_{vid_id}_{j}.mp4"
                        ok    = download_clip(vid_id, hit["start_sec"], hit["end_sec"], cpath)
                        hit["clip"] = str(cpath) if ok else "download failed"
                        icon  = "[green]✔[/green]" if ok else "[red]✘[/red]"
                        progress.console.print(f"         {icon}  {cpath.name}")
                        progress.advance(clip_task)
                    progress.remove_task(clip_task)
            else:
                progress.console.print(f"  [dim]–  {short}[/dim]")

            results.append({**video, "hits": hits})
            progress.advance(scan_task)

    # Final report
    json_path, txt_path = save_results(results, out_dir)
    elapsed = str(datetime.now() - start_time).split(".")[0]

    print_hit_table(results)
    print_summary(results, json_path, txt_path,
                  clips_dir if DOWNLOAD_CLIPS else None, elapsed)


if __name__ == "__main__":
    main()
