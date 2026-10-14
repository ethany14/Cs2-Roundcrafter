# Product video recorder

Records the Chinese intro video from **your own running app and your own demos**:

- real footage of the app (frame-accurate, scripted cursor, Chinese on-screen captions)
- short motion-graphics cards
- synthesised background music, no voice-over

One command produces `out/roundcrafter_zh.mp4` plus `out/roundcrafter_zh.srt` (captions you can upload to YouTube as CC).

## What the video covers

| Shot | What is shown | Needs |
|---|---|---|
| `library` · `replay` · `stats` · `agent` | import, 2D replay, match stats, Agent evidence | one parsed match |
| `evidence` · `finding` · `modes` · `rag` | motion-graphics: tool calls, finding card, 4 modes, hybrid vector RAG | — |
| `procompare` | review → 职业对照 → matched pro round → side-by-side synced playback | a **pro demo on the same map** (marked 职业比赛) |
| `board` | tactic board: draw, play the round | — |
| `multi` · `filters` · `heat` · `nade` | multi-round overlay; filters (side, result, plant, round list); heatmaps (dwell, reach, kills, deaths, **AWP scope heatmap**); utility clusters by type and player | your match on **Dust2 or Nuke** |
| `wbpro` | 对照职业: your data next to pro matches | pro demo on the same map |
| `career` | 我的生涯: rating, ADR, KAST, trend, per-map table, Steam auto-import | player stats (link Steam, or open a match's 比赛数据 tab once) |
| `lab` | utility lab: pick stand / landing point, local physics solve, candidate, aim view, setpos command | a lab map (`data/maps/all/<map>/scene.npz`) |
| `models` | model and embedding settings | — |

The script picks your data automatically. It uses your newest Dust2/Nuke match and finds one of its rounds that has a comparable pro round. Any shot your library can't support is skipped, and the script tells you why.

## Setup (once)

You need **Node.js 18+**. ffmpeg comes with the package.

```powershell
cd tools/promo-video
npm install
npx playwright install chromium
```

## Record

1. Start the app as usual (`./start-tactics.ps1`), so it runs at http://127.0.0.1:8790.
2. In a second terminal, record. The music step uses numpy from the app's Python environment, so activate it first (`./.venv/Scripts/Activate.ps1`) or set `"python": "../../.venv/Scripts/python.exe"` in the config:

```powershell
cd tools/promo-video
node record.cjs --list      # the plan: which shots will run with your data, and which are skipped
node record.cjs --preview   # quick stills of every shot in out/preview/ — check them first
node record.cjs             # the full video (a few minutes)
```

`--only multi,heat` records just those shots, which is useful while you tune something.

## Settings (optional)

To change settings, copy `video.config.example.json` to `video.config.json`:

| Key | Meaning |
|---|---|
| `match` | Match id or file name to feature. Default: your newest Dust2/Nuke match. |
| `round` | Round for the replay and pro-comparison shots. Default: one that has a pro match. |
| `anonymize` | `"others"` (default) replaces every player name except your own linked account with call-signs (Atlas, Nova, …) and masks SteamIDs on screen. Pro players keep their names. `"all"` also hides your own name and avatar. `"none"` changes nothing. |
| `python` | Python executable for the music step, if `python` isn't the right one. |
| `lab` | `map`, `mode` (`auto`, `auto_all`, `stand_left`, …). `origin` / `target` are either radar points `[u, v]` (0–1) that get clicked on the map, or exact `[x, y, z]` you can copy from the lab's 站位 / 目标 fields. |
| `skip` | Shot ids to leave out, e.g. `["models"]`. |

Captions and timing are all in the `buildShots()` function in `record.cjs`. Each shot is a short list of `move` / `click` / `select` / `fill` / `wait` actions, timed in seconds from the start of the shot.

## Privacy

Everything runs on your machine. The recorder only drives your local app in a private browser, and nothing is uploaded. Check the preview stills before posting, because demo file names and any custom tactic-board names will appear as they are.
