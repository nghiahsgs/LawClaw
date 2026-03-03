# Clip Cutter

Cut the best moments from a YouTube video into short clips.

## Prerequisites

- `yt-dlp` installed (brew install yt-dlp)
- `ffmpeg` installed (brew install ffmpeg)

## When to use

- User pastes a YouTube link and wants clips
- User says "cắt clip", "clip hay", "highlight", "shorts" with a video URL
- User wants transcript/summary from a YouTube video

## Pipeline

Follow these steps **in order**. Execute each step immediately using `exec_cmd`.

### Step 1: Create working directory

```
exec_cmd command="mkdir -p ~/.lawclaw/workspace/clips && echo 'ready'" timeout=5
```

### Step 2: Download video + subtitles

Download at max 1080p with auto-generated subtitles:

```
exec_cmd command="cd ~/.lawclaw/workspace/clips && yt-dlp -f 'bestvideo[height<=1080]+bestaudio/best[height<=1080]' --write-auto-sub --sub-lang en,vi --convert-subs srt --merge-output-format mp4 -o 'source.%(ext)s' --no-playlist 'YOUTUBE_URL'" timeout=300
```

### Step 3: Get transcription

**Priority order** — try each until one works:

#### 3a. YouTube auto-subs (preferred, free)

Subtitles are downloaded alongside the video in Step 2. Check for existing files:
```
exec_cmd command="ls ~/.lawclaw/workspace/clips/source.*.vtt ~/.lawclaw/workspace/clips/source.*.srt 2>/dev/null || echo 'no subs found'"
```

If no subs from Step 2, download separately:
```
exec_cmd command="cd ~/.lawclaw/workspace/clips && yt-dlp --write-auto-sub --sub-lang en,vi --skip-download -o 'transcript' 'YOUTUBE_URL'" timeout=60
```

Then read whichever subtitle file exists (.vtt or .srt):
```
read_file path="~/.lawclaw/workspace/clips/source.en.vtt"
```
If Vietnamese:
```
read_file path="~/.lawclaw/workspace/clips/source.vi.vtt"
```

Note: VTT files contain inline timestamps like `<00:00:19.039><c> word</c>`. Ignore the inline tags and focus on the main timestamps (HH:MM:SS.mmm --> HH:MM:SS.mmm) and the plain text.

#### 3b. No transcript available
If no subtitles found, tell the user and fall back to scene-based cutting:
```
exec_cmd command="cd ~/.lawclaw/workspace/clips && ffmpeg -i source.mp4 -filter:v 'select=gt(scene\\,0.4)' -vsync vfr -f null - 2>&1 | grep 'select' | head -20" timeout=120
```

### Step 4: Analyze transcript & cut clips immediately

After reading the transcript, select **3-5 best moments** based on:

1. **Hook strength** — does the first sentence grab attention?
2. **Self-contained** — can the clip be understood without context?
3. **Emotional peak** — strong reaction, surprise, humor
4. **Insight density** — valuable information packed in short time
5. **Controversial/bold** — strong opinion or contrarian take

Optimal clip length: **30-90 seconds** for shorts, **1-3 minutes** for highlights.

**CRITICAL**: Do NOT stop to present a table or text summary of the clips. You MUST immediately proceed to cut each clip using `exec_cmd` with ffmpeg in the SAME turn. If you output text without tool calls, the pipeline stops and the user gets nothing. Analyze internally, then cut immediately.

### Step 5: Cut clips with ffmpeg

For each selected moment, call `exec_cmd` immediately (do NOT present a summary first):

```
exec_cmd command="cd ~/.lawclaw/workspace/clips && ffmpeg -ss HH:MM:SS -to HH:MM:SS -i source.mp4 -c:v libx264 -c:a aac -preset fast clip_01.mp4 -y" timeout=120
```

### Step 6: (Optional) Crop to vertical 9:16 for shorts

```
exec_cmd command="cd ~/.lawclaw/workspace/clips && ffmpeg -i clip_01.mp4 -vf 'crop=ih*9/16:ih' -c:a copy clip_01_vertical.mp4 -y" timeout=120
```

### Step 7: Send clips to user

After ALL clips are cut, send each one immediately via `send_file`. Do NOT stop between cutting and sending.

```
send_file path="~/.lawclaw/workspace/clips/clip_01.mp4" caption="Clip 1: [title]"
send_file path="~/.lawclaw/workspace/clips/clip_02.mp4" caption="Clip 2: [title]"
```

**CRITICAL**: You MUST call `send_file` for EVERY clip. Do NOT just describe the clips or show a table — the user needs the actual video files delivered to their chat.

### Step 8: Cleanup

After all clips are sent:

```
exec_cmd command="rm -rf ~/.lawclaw/workspace/clips/source.* ~/.lawclaw/workspace/clips/audio.* ~/.lawclaw/workspace/clips/transcript.*" timeout=10
```

## Tips

- Always download video BEFORE extracting subtitles separately (yt-dlp may bundle them)
- Use `-ss` BEFORE `-i` in ffmpeg for fast seeking (input seeking vs output seeking)
- If video is longer than 2 hours, warn user it may take longer
- Keep clip files small — Telegram has 50MB limit for bots
- If a clip exceeds 50MB, re-encode with lower bitrate:
  ```
  ffmpeg -i clip.mp4 -b:v 2M -c:a aac -b:a 128k clip_small.mp4
  ```
- Vietnamese YouTube videos often have auto-generated Vietnamese subs — try `vi` first
- For SRT timestamp format: `00:01:23,456` → ffmpeg uses `00:01:23.456` (dot not comma)
- The workspace for clips is `~/.lawclaw/workspace/clips/` — always clean up source files after done
