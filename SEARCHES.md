# Catchphrase Search Results

## Summary
Comprehensive searches for "permission structure" across YouTube channels.

## IHIP News Channel
- **Status**: ✓ Completed
- **Videos scanned**: 2,663
- **Videos with matches**: 85
- **Total hits**: 213
- **Deduplication**: No VTT duplicates (all 213 are unique)
- **Output**: `catchphrase_output/vtt_search_results_fresh_3week.json`

### Compilations Generated
1. **Biweekly Supercut** (2026-04-21 to 2026-05-12)
   - Status: ✓ Complete
   - Clips: 20 (from 8 videos)
   - Duration: 1m 45s
   - Size: 19.5 MB
   - Padding: 2 seconds
   - Location: `catchphrase_output/clips_biweekly/biweekly_supercut.mp4`

2. **3-Week Supercut** (2026-04-21 to 2026-05-12)
   - Status: Prepared (213 hits deduplicated)
   - Downloads: Blocked by YouTube rate limiting
   - Expected scope: 85 videos, ~213 clips
   - Folder: `catchphrase_output/clips_3week_2026-04-21_to_2026-05-12/`

## @adammockler Channel
- **Status**: ⏸ Paused - Rate Limited
- **Total videos**: 4,150
- **Transcripts downloaded**: 1/4,150
- **Issue**: YouTube blocking transcript downloads after initial batch from IHIP News
- **Resolution**: Waiting 24-48 hours for rate limit reset

## Notes
- All video files (.mp4, .vtt) are in `.gitignore` and not version-controlled
- Search results (JSON) are stored in `catchphrase_output/` but not committed
- The skill and scripts are fully reproducible once rate limiting clears
- Recommended: Retry @adammockler search after 2026-05-14
