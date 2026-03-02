#!/usr/bin/env python3
"""
VTT Transcript Search
----------------------
Searches all downloaded .vtt transcript files for a phrase and produces
a comprehensive results JSON + TXT report with deduplicated timestamps.

Requirements:
    pip install rich

Usage:
    python3 vtt_search.py
"""

import re
import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn, TextColumn,
        MofNCompleteColumn, TimeElapsedColumn, TimeRemainingColumn, TaskProgressColumn
    )
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.rule import Rule
    from rich.live import Live
    from rich.layout import Layout
    from rich.align import Align
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
TRANSCRIPTS_DIR = "./catchphrase_output/transcripts"
OUTPUT_DIR      = "./catchphrase_output"
PHRASE          = "permission structure"   # edit or leave blank to be prompted
MAX_FEED_LINES  = 12   # how many recent hits to show in the live feed panel
# ─────────────────────────────────────────────


def vtt_time_to_seconds(ts):
    ts = ts.split(".")[0]
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return int(parts[0])


def seconds_to_hms(s):
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def parse_vtt(vtt_path):
    """Parse a VTT file into deduplicated segments with timestamps."""
    text = vtt_path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"WEBVTT.*?\n\n", "", text, flags=re.DOTALL, count=1)

    segments  = []
    seen_keys = set()

    for block in re.split(r"\n\n+", text.strip()):
        lines   = block.strip().splitlines()
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue
        m = re.match(r"(\S+)\s+-->\s+(\S+)", ts_line)
        if not m:
            continue
        start   = vtt_time_to_seconds(m.group(1))
        end     = vtt_time_to_seconds(m.group(2))
        caption = " ".join(l for l in lines if "-->" not in l and not re.match(r"^\d+$", l))
        caption = re.sub(r"<[^>]+>", "", caption).strip()

        key = (start, caption)
        if not caption or key in seen_keys:
            continue
        seen_keys.add(key)
        segments.append({"start_sec": start, "end_sec": end, "text": caption})

    return segments


# ── Live dashboard builder ────────────────────────────────────────────────────

def make_stats_panel(scanned, total, matched_videos, total_hits, current_title):
    """Build the live stats panel shown during scanning."""
    pct = (scanned / total * 100) if total else 0

    grid = Table.grid(expand=True, padding=(0, 3))
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)

    def cell(value, label, color="white"):
        return f"[{color} bold]{value}[/{color} bold]\n[dim]{label}[/dim]"

    grid.add_row(
        cell(f"{scanned:,}", "scanned",       "cyan"),
        cell(f"{total:,}",   "total files",   "dim white"),
        cell(f"{matched_videos:,}", "matched videos", "green"),
        cell(f"{total_hits:,}",    "hits found",     "yellow"),
    )

    title_line = f"\n[dim]Current:[/dim] [white]{current_title[:60]}[/white]" if current_title else ""
    return Panel(
        Align.center(grid),
        title=f"[bold cyan]🔍 Scanning… {pct:.1f}%[/bold cyan]{title_line}",
        border_style="cyan",
        padding=(1, 2),
    )


def make_feed_panel(feed_lines, phrase):
    """Build the rolling hits feed panel."""
    if not feed_lines:
        content = "[dim]No hits yet…[/dim]"
    else:
        content = "\n".join(feed_lines[-MAX_FEED_LINES:])
    return Panel(
        content,
        title=f'[bold yellow]⚡ Live Hits — "[yellow]{phrase}[/yellow]"[/bold yellow]',
        border_style="yellow",
        padding=(0, 1),
    )


def search_vtt_files(transcripts_dir, phrase):
    vtt_files = sorted(Path(transcripts_dir).glob("*.vtt"))

    if not vtt_files:
        console.print(f"[red]No .vtt files found in:[/red] {transcripts_dir}")
        sys.exit(1)

    needle         = phrase.lower()
    results        = []
    total_hits     = 0
    matched_videos = 0
    feed_lines     = []

    # ── Progress bar setup ────────────────────────────────────────────────────
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=15,
        expand=True,
    )
    task = progress.add_task(
        f"[cyan]Searching transcripts for[/cyan] [yellow]\"{phrase}\"[/yellow]",
        total=len(vtt_files)
    )

    # ── Live layout: stats + feed stacked above the progress bar ─────────────
    layout = Layout()
    layout.split_column(
        Layout(name="stats",    size=7),
        Layout(name="feed",     size=MAX_FEED_LINES + 4),
        Layout(name="progress", size=3),
    )
    layout["progress"].update(progress)
    layout["stats"].update(make_stats_panel(0, len(vtt_files), 0, 0, ""))
    layout["feed"].update(make_feed_panel([], phrase))

    with Live(layout, console=console, refresh_per_second=15, screen=False):
        for i, vtt_path in enumerate(vtt_files, 1):
            video_id = vtt_path.name.split(".")[0]

            # Update stats panel with current file
            layout["stats"].update(
                make_stats_panel(i, len(vtt_files), matched_videos, total_hits, video_id)
            )

            segments = parse_vtt(vtt_path)
            hits     = []
            for seg in segments:
                if needle in seg["text"].lower():
                    hits.append(seg)

            if hits:
                total_hits     += len(hits)
                matched_videos += 1
                results.append({
                    "video_id":  video_id,
                    "vtt_file":  vtt_path.name,
                    "hit_count": len(hits),
                    "hits":      hits,
                })

                for hit in hits:
                    ts  = seconds_to_hms(hit["start_sec"])
                    # Highlight phrase in caption
                    cap = re.sub(
                        re.escape(phrase), f"[bold yellow]{phrase}[/bold yellow]",
                        hit["text"], flags=re.IGNORECASE
                    )
                    # Truncate caption for feed display
                    cap_short = cap[:70] + ("…" if len(cap) > 70 else "")
                    feed_lines.append(
                        f"  [green]✔[/green] [dim]{video_id}[/dim]  "
                        f"[green]⏱ {ts}[/green]  {cap_short}"
                    )

                # Refresh both panels after new hits
                layout["stats"].update(
                    make_stats_panel(i, len(vtt_files), matched_videos, total_hits, video_id)
                )
                layout["feed"].update(make_feed_panel(feed_lines, phrase))

            progress.advance(task)

    return results, len(vtt_files), total_hits


# ── Results table ─────────────────────────────────────────────────────────────

def print_results_table(results, phrase):
    if not results:
        console.print(Panel("[yellow]No matches found.[/yellow]", border_style="yellow"))
        return

    total_hits = sum(r["hit_count"] for r in results)

    table = Table(
        title=f'[bold]{total_hits} total hits for "[yellow]{phrase}[/yellow]" '
              f'across {len(results)} videos[/bold]',
        box=box.ROUNDED, border_style="cyan", show_lines=True,
        header_style="bold cyan"
    )
    table.add_column("#",         width=4,  justify="right", style="dim")
    table.add_column("Video ID",  width=14, style="bold")
    table.add_column("Timestamp", width=10, style="green")
    table.add_column("Caption",   min_width=42)
    table.add_column("YouTube Link", min_width=40, style="blue dim")

    n = 0
    for r in results:
        for hit in r["hits"]:
            n += 1
            yt_ts = int(hit["start_sec"])
            cap   = re.sub(
                re.escape(phrase),
                f"[bold yellow]{phrase}[/bold yellow]",
                hit["text"], flags=re.IGNORECASE
            )
            table.add_row(
                str(n),
                r["video_id"],
                seconds_to_hms(hit["start_sec"]),
                cap,
                f"https://youtu.be/{r['video_id']}?t={yt_ts}",
            )

    console.print()
    console.print(table)


# ── Save ──────────────────────────────────────────────────────────────────────

def save_results(results, phrase, total_files, total_hits, out_dir):
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # JSON — compatible with clip_downloader.py
    json_data = [
        {"id": r["video_id"], "title": r["video_id"], "hits": r["hits"]}
        for r in results
    ]
    json_path = out_path / f"vtt_search_results_{ts}.json"
    json_path.write_text(json.dumps(json_data, indent=2))

    # Human-readable TXT
    txt_path = out_path / f"vtt_search_results_{ts}.txt"
    lines = [
        "VTT Transcript Search Results",
        f'Phrase        : "{phrase}"',
        f"Transcripts   : {total_files}",
        f"Videos matched: {len(results)}",
        f"Total hits    : {total_hits}",
        f"Date          : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 60, "",
    ]
    for r in results:
        lines.append(f"📺  {r['video_id']}  ({r['hit_count']} hit{'s' if r['hit_count'] > 1 else ''})")
        for hit in r["hits"]:
            yt_ts = int(hit["start_sec"])
            lines.append(f"    ⏱  {seconds_to_hms(hit['start_sec'])}  →  \"{hit['text']}\"")
            lines.append(f"       https://youtu.be/{r['video_id']}?t={yt_ts}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


# ── Final summary ─────────────────────────────────────────────────────────────

def print_summary(results, total_files, total_hits, json_path, txt_path, elapsed):
    stats = Table.grid(expand=True, padding=(0, 4))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")

    def cell(v, label, color):
        return f"[{color} bold]{v}[/{color} bold]\n[dim]{label}[/dim]"

    stats.add_row(
        cell(f"{total_files:,}",   "transcripts searched", "cyan"),
        cell(f"{len(results):,}",  "videos matched",       "green"),
        cell(f"{total_hits:,}",    "total hits",           "yellow"),
    )

    console.print()
    console.print(Rule("[bold cyan]Search Complete[/bold cyan]"))
    console.print()
    console.print(Panel(stats, title="[bold]Final Results[/bold]", border_style="cyan", padding=(1, 4)))

    files = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    files.add_column(style="dim", width=28)
    files.add_column(style="cyan")
    files.add_row("📄 Text report",              str(txt_path))
    files.add_row("📦 JSON (for clip_downloader)", str(json_path))
    console.print(Panel(files, title="[bold]Output Files[/bold]", border_style="dim"))

    console.print(
        f"\n[dim]Runtime: {elapsed}[/dim]  ·  "
        "[dim]Next step:[/dim]  [bold cyan]python3 clip_downloader.py[/bold cyan]\n"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global PHRASE

    console.print()
    console.print(Panel.fit(
        "[bold yellow]🔍 VTT Transcript Search[/bold yellow]\n"
        "[dim]Search all downloaded transcripts for a phrase with full timestamps[/dim]",
        border_style="yellow"
    ))
    console.print()

    if not PHRASE:
        PHRASE = Prompt.ask("[cyan]Phrase to search for[/cyan]")

    console.print(
        f"Searching [bold]{TRANSCRIPTS_DIR}[/bold] for "
        f"[bold yellow]\"{PHRASE}\"[/bold yellow]…\n"
    )

    start_time = datetime.now()
    results, total_files, total_hits = search_vtt_files(TRANSCRIPTS_DIR, PHRASE)

    print_results_table(results, PHRASE)
    json_path, txt_path = save_results(results, PHRASE, total_files, total_hits, OUTPUT_DIR)
    elapsed = str(datetime.now() - start_time).split(".")[0]
    print_summary(results, total_files, total_hits, json_path, txt_path, elapsed)


if __name__ == "__main__":
    main()
