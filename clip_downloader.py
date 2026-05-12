#!/usr/bin/env python3
"""
Catchphrase Clip Downloader
----------------------------
Reads the results JSON produced by catchphrase_finder.py, lets you
review and approve individual hits, then downloads only the clips you
want — with padding, quality control, and an optional ffmpeg supercut.

Requirements:
    pip install yt-dlp rich
    brew install ffmpeg  (or: sudo apt install ffmpeg)

Usage:
    python3 clip_downloader.py
"""

import re
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn,
        TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn, TaskProgressColumn
    )
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich import box
    import rich.traceback
    rich.traceback.install()
except ImportError:
    print("Missing dependency: pip install rich")
    sys.exit(1)

console = Console()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
RESULTS_JSON   = "./catchphrase_output/results_*.json"  # glob — picks latest
OUTPUT_DIR     = "./catchphrase_output/clips"
CLIP_PADDING   = 4          # seconds before/after the hit
VIDEO_QUALITY  = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
BUILD_SUPERCUT = True       # stitch approved clips into one file at the end
SUPERCUT_NAME  = "supercut.mp4"
SKIP_EXISTING  = True       # skip re-downloading clips already on disk
# ─────────────────────────────────────────────


def seconds_to_hms(s):
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def check_dependencies():
    tools = [
        ("yt-dlp",  ["yt-dlp",  "--version"], "pip install yt-dlp"),
        ("ffmpeg",  ["ffmpeg",  "-version"],  "brew install ffmpeg"),
        ("ffprobe", ["ffprobe", "-version"],  "brew install ffmpeg"),
    ]
    table = Table(title="Dependency Check", box=box.ROUNDED, border_style="dim")
    table.add_column("Tool",               style="bold")
    table.add_column("Status")
    table.add_column("Install if missing", style="dim")

    all_ok = True
    for name, cmd, install in tools:
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            table.add_row(name, "[green]✔  Found[/green]", "")
        except (subprocess.CalledProcessError, FileNotFoundError):
            table.add_row(name, "[red]✘  Missing[/red]", install)
            all_ok = False

    console.print(table)
    console.print()
    if not all_ok:
        console.print("[red bold]Please install missing tools and re-run.[/red bold]")
        sys.exit(1)


# ── Load results JSON ─────────────────────────────────────────────────────────

def load_results():
    """Find and load the most recent results JSON from catchphrase_finder."""
    import glob
    matches = sorted(glob.glob(RESULTS_JSON))

    if not matches:
        # Also try without glob if user provides exact path
        console.print(f"[yellow]No results JSON found at:[/yellow] {RESULTS_JSON}")
        path = Prompt.ask("[cyan]Enter path to your results JSON file[/cyan]")
        matches = [path]

    latest = matches[-1]
    console.print(f"[dim]Loading:[/dim] [cyan]{latest}[/cyan]\n")

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    # Flatten into a list of clip candidates, deduplicating VTT double-entries
    clips = []
    seen  = set()
    for video in data:
        if not video.get("hits"):
            continue
        for hit in video["hits"]:
            key = (video["id"], int(hit["start_sec"]))
            if key in seen:
                continue
            seen.add(key)
            clips.append({
                "video_id":  video["id"],
                "title":     video["title"],
                "start_sec": hit["start_sec"],
                "end_sec":   hit["end_sec"],
                "text":      hit["text"],
                "approved":  True,   # default all approved; review step can change
            })

    return clips, latest


# ── Review table ──────────────────────────────────────────────────────────────

def show_review_table(clips, catchphrase="permission structure"):
    """Print a numbered table of all hits for review."""
    table = Table(
        title=f"[bold]Found [yellow]{len(clips)}[/yellow] unique hits — review before downloading[/bold]",
        box=box.ROUNDED, border_style="cyan", show_lines=True,
        header_style="bold cyan"
    )
    table.add_column("#",         width=4,  justify="right", style="dim")
    table.add_column("Video",     min_width=30, max_width=44, style="bold white")
    table.add_column("Timestamp", width=10, style="green")
    table.add_column("Caption",   min_width=34)
    table.add_column("Keep",      width=6,  justify="center")

    for i, clip in enumerate(clips, 1):
        ts  = seconds_to_hms(clip["start_sec"])
        cap = re.sub(
            re.escape(catchphrase),
            f"[bold yellow]{catchphrase}[/bold yellow]",
            clip["text"], flags=re.IGNORECASE
        )
        keep = "[green]✔[/green]" if clip["approved"] else "[red]✘[/red]"
        table.add_row(str(i), clip["title"][:44], ts, cap, keep)

    console.print()
    console.print(table)
    console.print()


def review_clips(clips):
    """Interactively let user approve/reject clips."""
    console.print(Panel(
        "[bold]Review Options[/bold]\n\n"
        "  [cyan]all[/cyan]     → approve everything and start downloading\n"
        "  [cyan]none[/cyan]    → reject all, then manually approve by number\n"
        "  [cyan]pick[/cyan]    → enter clip numbers to keep (e.g. [dim]1 3 5-8 12[/dim])\n"
        "  [cyan]skip[/cyan]    → enter clip numbers to remove (e.g. [dim]2 4 9[/dim])\n"
        "  [cyan]go[/cyan]      → proceed with current selection",
        border_style="cyan", title="[bold]Curation Mode[/bold]"
    ))

    while True:
        choice = Prompt.ask(
            "[cyan]Choice[/cyan]",
            choices=["all", "none", "pick", "skip", "go"],
            default="all"
        ).strip().lower()

        if choice == "all":
            for c in clips:
                c["approved"] = True
            break

        elif choice == "none":
            for c in clips:
                c["approved"] = False
            console.print("[dim]All rejected. Use 'pick' to select clips to keep.[/dim]")

        elif choice in ("pick", "skip"):
            raw = Prompt.ask(
                f"[cyan]Enter clip numbers to {'keep' if choice == 'pick' else 'remove'}[/cyan] "
                f"[dim](e.g. 1 3 5-8)[/dim]"
            )
            nums = parse_number_range(raw, len(clips))
            for i, c in enumerate(clips, 1):
                if choice == "pick":
                    c["approved"] = i in nums
                else:
                    if i in nums:
                        c["approved"] = False
            show_review_table(clips)

        elif choice == "go":
            break

    approved = [c for c in clips if c["approved"]]
    console.print(f"\n[green]✔[/green]  [bold]{len(approved)}[/bold] clips approved for download.\n")
    return approved


def parse_number_range(raw, max_n):
    """Parse '1 3 5-8 12' into a set of integers."""
    nums = set()
    for part in raw.split():
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                nums.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            nums.add(int(part))
    return {n for n in nums if 1 <= n <= max_n}


# ── Download ──────────────────────────────────────────────────────────────────

def safe_filename(title, video_id, index):
    safe = re.sub(r'[^\w\-]', '_', title)[:40]
    return f"{index:03d}_{safe}_{video_id}.mp4"


def download_clip(clip, out_path, index, total):
    url   = f"https://www.youtube.com/watch?v={clip['video_id']}"
    start = max(0, clip["start_sec"] - CLIP_PADDING)
    end   = clip["end_sec"] + CLIP_PADDING

    cmd = [
        "yt-dlp",
        "-f", VIDEO_QUALITY,
        "--download-sections", f"*{seconds_to_hms(start)}-{seconds_to_hms(end)}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        "--no-warnings",
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


# ── Supercut ──────────────────────────────────────────────────────────────────

def build_supercut(clip_paths, out_path):
    """Concatenate all clips into a single supercut using ffmpeg concat demuxer."""
    console.print()
    console.print(Rule("[bold cyan]Building Supercut[/bold cyan]"))
    console.print()

    # Write concat list file
    list_path = out_path.parent / "concat_list.txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            # ffmpeg requires escaped paths
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(out_path),
    ]

    with console.status(
        f"[bold magenta]Stitching {len(clip_paths)} clips into supercut…[/bold magenta]",
        spinner="dots"
    ):
        result = subprocess.run(cmd, capture_output=True)

    if result.returncode == 0:
        # Get duration via ffprobe
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
            capture_output=True, text=True
        )
        duration = ""
        if probe.returncode == 0:
            secs = float(probe.stdout.strip())
            duration = f"  [dim]({seconds_to_hms(secs)} total)[/dim]"
        console.print(f"[green]✔[/green]  Supercut saved: [cyan]{out_path}[/cyan]{duration}")
    else:
        console.print(f"[red]✘  Supercut failed:[/red]\n{result.stderr.decode()}")

    list_path.unlink(missing_ok=True)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(approved, downloaded, failed, out_dir, supercut_path, elapsed):
    stats = Table.grid(expand=True, padding=(0, 4))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")

    def cell(v, label, color):
        return f"[{color} bold]{v}[/{color} bold]\n[dim]{label}[/dim]"

    stats.add_row(
        cell(len(approved),  "clips approved",   "cyan"),
        cell(len(downloaded),"downloaded",        "green"),
        cell(len(failed),    "failed",            "red"),
    )

    console.print()
    console.print(Rule("[bold cyan]Download Complete[/bold cyan]"))
    console.print()
    console.print(Panel(stats, title="[bold]Summary[/bold]", border_style="cyan", padding=(1, 4)))

    files = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    files.add_column(style="dim", width=14)
    files.add_column(style="cyan")
    files.add_row("🎬 Clips folder",  str(out_dir))
    if supercut_path and supercut_path.exists():
        files.add_row("🎞  Supercut",     str(supercut_path))
    console.print(Panel(files, title="[bold]Output[/bold]", border_style="dim"))

    if failed:
        console.print("\n[yellow]Failed clips (you can retry manually):[/yellow]")
        for clip in failed:
            console.print(f"  [dim]https://youtu.be/{clip['video_id']}?t={int(clip['start_sec'])}[/dim]")

    console.print(f"\n[dim]Total runtime: {elapsed}[/dim]\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    console.print()
    console.print(Panel.fit(
        "[bold yellow]🎬 Catchphrase Clip Downloader[/bold yellow]\n"
        "[dim]Review hits, approve clips, download segments, build supercut[/dim]",
        border_style="yellow"
    ))
    console.print()

    check_dependencies()

    # Load hits
    clips, json_path = load_results()

    if not clips:
        console.print("[yellow]No hits found in results file. Run catchphrase_finder.py first.[/yellow]")
        sys.exit(0)

    # Detect catchphrase from first hit for highlighting
    catchphrase = "permission structure"  # fallback
    try:
        with open(json_path) as f:
            raw = json.load(f)
        # Try to infer from the JSON filename or just use default
    except Exception:
        pass

    # Show all hits
    show_review_table(clips, catchphrase)

    console.print(f"[bold]{len(clips)}[/bold] unique hits across "
                  f"[bold]{len(set(c['video_id'] for c in clips))}[/bold] videos.\n")

    # Review / approve
    approved = review_clips(clips)

    if not approved:
        console.print("[yellow]No clips selected. Exiting.[/yellow]")
        sys.exit(0)

    # Confirm padding
    global CLIP_PADDING
    console.print(f"\n[dim]Clip padding: [bold]{CLIP_PADDING}s[/bold] before and after each hit.[/dim]")
    change = Confirm.ask("[cyan]Change padding?[/cyan]", default=False)
    if change:
        CLIP_PADDING = IntPrompt.ask("[cyan]Padding in seconds[/cyan]", default=4)

    # Setup output
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    downloaded = []
    failed     = []

    # Download loop
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=34),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:

        task = progress.add_task("[cyan]Downloading clips…[/cyan]", total=len(approved))

        for i, clip in enumerate(approved, 1):
            fname    = safe_filename(clip["title"], clip["video_id"], i)
            out_path = out_dir / fname
            short    = (clip["title"][:42] + "…") if len(clip["title"]) > 43 else clip["title"]
            ts       = seconds_to_hms(clip["start_sec"])

            progress.update(task, description=f"[cyan]Clip {i}/{len(approved)}:[/cyan] [white]{short}[/white]")

            if SKIP_EXISTING and out_path.exists():
                progress.console.print(f"  [dim]↷  skipped (exists)  {fname}[/dim]")
                downloaded.append(out_path)
                progress.advance(task)
                continue

            ok = download_clip(clip, out_path, i, len(approved))

            if ok:
                # Get file size
                size_mb = out_path.stat().st_size / 1_048_576 if out_path.exists() else 0
                progress.console.print(
                    f"  [green]✔[/green]  [white]{short}[/white]  "
                    f"[green]⏱ {ts}[/green]  [dim]{size_mb:.1f} MB[/dim]"
                )
                downloaded.append(out_path)
            else:
                progress.console.print(
                    f"  [red]✘  failed:[/red] [dim]https://youtu.be/{clip['video_id']}?t={int(clip['start_sec'])}[/dim]"
                )
                failed.append(clip)

            progress.advance(task)

    # Supercut
    supercut_path = None
    if BUILD_SUPERCUT and len(downloaded) > 1:
        build = Confirm.ask(
            f"\n[cyan]Build supercut from all {len(downloaded)} downloaded clips?[/cyan]",
            default=True
        )
        if build:
            supercut_path = out_dir / SUPERCUT_NAME
            build_supercut(downloaded, supercut_path)

    elapsed = str(datetime.now() - start_time).split(".")[0]
    print_summary(approved, downloaded, failed, out_dir, supercut_path, elapsed)


if __name__ == "__main__":
    main()
