# TRPG-Universe Agent 🐳

> Turn session recordings and chat exports from tabletop RPG campaigns into a
> **searchable, browsable, publishable** character-relationship archive.
>
> [中文](README.md) · **English**

---

## What it is

A **local-first** toolchain for organizing TRPG campaign material. Input: hours of
audio and chat logs. Output: a structured character/relation database, plus
relationship sites, chronicles and storybooks that are actually pleasant to read.

Three things it takes seriously:

1. **Long-audio transcription** — a 6-hour recording completes on a 16 GB machine,
   and survives interruptions.
2. **Relation-data consistency** — LLMs love creating "the same person" three times.
   Canon injection plus a patch contract keeps that in check.
3. **Data safety** — the production database refuses writes by default, every write
   is backed up first, and unconfirmed content never hits disk.

> Built for GMs/KPs, people who want a polished archive site for their campaign,
> and anyone researching structured extraction from long LLM contexts.

---

## Features

| Capability | Notes |
|---|---|
| Nine-step pipeline | `ingest → transcribe → segment → extract → review → store → visualize → export → housekeep`. Every step is individually re-runnable; artifacts *are* the state |
| Windowed transcription | Streams in 30-minute windows to avoid the whole-file STFT OOM; **byte-level resume** |
| Quality self-check | Filters `initial_prompt` leakage and repetition hallucinations; reports retention and samples |
| Patch-driven ingestion | The LLM emits a patch JSON; `store` validates → normalizes → dedupes → stages → reports → backs up and applies |
| Pending-review loop | Anything with `confirmed: false` is downgraded to "pending" — never written. Humans adjudicate, results are written back to the patch and naming table |
| Canon injection | Rules + alias-normalization table + existing roster are packed into every extraction to suppress duplicate nodes |
| Visualization | Per-group relation graph (SVG), player portrait wall, universe overview, ego network, story chronicle |
| Local web panel | Vue 3 progress board + pending-review adjudication + artifact preview |
| Self-hosted edit site | FastAPI shell with revision history, shared token and rate limiting |
| Regression tests | 96 assertions: idempotency / resume / production gate / PID-reuse guard / multi-recording isolation |

---

## Architecture

### The nine-step pipeline

```
① ingest  → ② transcribe → ③ segment → ④ extract → ⑤ review
                                          ↓
        ⑨ housekeep ← ⑧ export ← ⑦ visualize ← ⑥ store (chronicle alongside)
```

| Step | Command | Output | Notes |
|---|---|---|---|
| ① ingest | `python -m trpg_agent ingest` | `manifest.json` | Drop material into `<workspace>/素材/<group>/` |
| ② transcribe | `python -m trpg_agent transcribe --group "X"` | `<group>_转写.txt` | **Slowest step**; resume = re-run with identical config |
| ③ segment | `python -m trpg_agent segment --group "X"` | `.trpg/segments/…` | One session = one segment |
| ④ extract | `python tools/extract_all.py` | `.trpg/patches/<group>_patch.json` | The LLM extracts **character skeletons** only; relations are filled separately |
| ⑤ review | `python -m trpg_agent review --group "X"` | `<group>_待确认.json` | Human adjudication |
| ⑥ store | `python -m trpg_agent store --apply --allow-production` | production DB | Shadow-workspace rehearsal → production; **append-only** |
| ⑦ visualize | `python -m trpg_agent visualize --group "X"` | graph HTML + relations md | Re-run after registering portraits |
| ⑧ export | `python -m trpg_agent export` | `产出/astrbot知识库导入/` | RAG-friendly knowledge pack |
| ⑨ housekeep | `python -m trpg_agent housekeep` | wrap-up checklist | Counts / status / pending items |

### Three layers — don't mix them

| Layer | Artifact | Reader | Discipline |
|---|---|---|---|
| **Data** | `<workspace>/数据/characters.json`, `relations.json` | Tools, verification | Back up before writing · `confirmed:false` never persisted · production gate |
| **Text** | `<workspace>/产出/<group>_剧情编年史.md` | Internal verification | Timestamps and uncertainty markers allowed; may be messy |
| **Product** | Rendered sites and images in `<workspace>/产出/` | Humans | **Must be cleaned**: strip timestamps, meta-notes, editor comments |

> ⚠️ The most common mistake: handing the chronicle straight to a reader.
> **The chronicle is evidence; the product is a work.**

---

## Install

Requires **Python ≥ 3.11**.

```bash
git clone https://github.com/ReGMeIoN/trpg-universe-agent.git
cd trpg-universe-agent

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

If you only want the sample walkthrough and won't transcribe, you can skip `faster-whisper`:

```bash
pip install typer pydantic PyYAML rich jsonschema requests python-docx
```

---

## Quickstart

The repo ships a **fully fictional, de-identified sample campaign** in
`examples/mini-group` ("Star Sea Express"). It needs **no audio and no LLM** and runs
end to end:

```bash
# 0) Freeze canon (rules + naming table + existing roster)
python -m trpg_agent canon build
python -m trpg_agent canon show --group 星海列车

# 1) Full pipeline on the sample
python -m trpg_agent ingest  --ws examples/mini-group
python -m trpg_agent segment --ws examples/mini-group
python -m trpg_agent store   --ws examples/mini-group \
  --patch "examples/mini-group/.trpg/patches/星海列车_patch.json"
python -m trpg_agent visualize --ws examples/mini-group --group 星海列车
python -m trpg_agent export    --ws examples/mini-group

# Reset after playing with it
python tools/reset_example.py
```

Running your own campaign:

```bash
# 1) Put the material in place
mkdir -p workspace/素材/MyGroup
cp session-01.m4a workspace/素材/MyGroup/

# 2) Transcribe (smoke-test 120s first, then full run in the background)
python -m trpg_agent transcribe --group MyGroup --smoke 120
python -m trpg_agent transcribe --group MyGroup --background
python -m trpg_agent jobs list
python -m trpg_agent jobs logs <job-id> --tail 30

# 3) Segment → extract → review → store
python -m trpg_agent segment --group MyGroup
python -m trpg_agent extract --group MyGroup --base-url http://127.0.0.1:11434
python -m trpg_agent review  --group MyGroup            # produce the decision file
python -m trpg_agent review  --group MyGroup --apply    # commit decisions
python -m trpg_agent store   --group MyGroup            # dry run (staging copy)
python -m trpg_agent store   --group MyGroup --apply --allow-production

# 4) Produce artifacts
python -m trpg_agent visualize --group MyGroup
python -m trpg_agent export
python -m trpg_agent housekeep
```

### Local web panel

```bash
# Secrets are read from the environment only — never written to config
export TRPG_LLM_KEY=sk-xxxx        # Windows: $env:TRPG_LLM_KEY = "sk-xxxx"
python -m trpg_agent web --background     # http://127.0.0.1:8765
```

Three panels: **progress board** (jobs / percentage / live log / interrupt),
**pending-review adjudication** (accept / reject / edit fields, written back),
and **artifact preview** (embedded graphs, rendered Markdown reports).
Binds to `127.0.0.1` only.

---

## Configuration

```bash
cp config.example.yaml config.yaml
```

- **Switching workspaces changes one line**: `workspace.root`
- **Secrets come from environment variables** (`api_key_env`), never from the config file
- Production gate: `workspace.allow_production_write`, defaults to `false`

### Environment variables used by `tools/`

Scripts under `tools/` contain **no absolute paths**; external directories are located
through environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `TRPG_WS` | Workspace root | `./workspace` |
| `TRPG_NAI` | NovelAI output archive | `./novelai` |
| `TRPG_DATA` | Other external data roots | script-specific |
| `TRPG_USER_HOME` | User home (a few scripts) | empty |
| `TRPG_LIVE_BASE` | Live site URL (integration scripts) | `http://127.0.0.1:8080/` |
| `TRPG_LLM_KEY` | LLM API key | required for cloud backends |

---

## Workspace layout

One **Workspace** = one universe:

```
<root>/素材/     Raw material (audio, chat exports, character sheets) — often private
<root>/数据/     characters.json · relations.json · players.json · pl_profiles.json
<root>/产出/     Visualizations / knowledge pack / chronicle (human-readable)
<root>/.trpg/    Runtime: state/ jobs/ logs/ patches/ staging/ reports/ canon/ normalized/
```

Switch workspaces by editing `workspace.root` in `config.yaml`, or override per-run with `--ws`.

---

## Design notes

### Patch-driven ingestion

No more hand-written `add_<group>.py` per campaign. `extract` emits a patch JSON and
`store` handles validate → normalize → dedupe → staging → report → backup-and-apply.
The contract lives in the header comment of `trpg_agent/store/merger.py`.

### Only write what is certain

Patch entries with `confirmed: false` are downgraded to "pending" and **never written**.
Better to record uncertainty than to confidently write something wrong.

### Always back up · production gate

- `<name>.bak_store_<timestamp>`, 10 kept by default
- `store --apply` **refuses** the production workspace unless `--allow-production` (or
  `config.workspace.allow_production_write: true`)
- Shadow rehearsal: copy the workspace to `<workspace>/.trpg/shadow_ws` and run
  `store --ws "<shadow>"` — see the result on a real database with **zero production risk**

### Why transcription is windowed

`faster-whisper` performs a **single STFT over the whole input**: a 7.3-hour file needs
~7.6 GiB on a 16 GB machine and simply OOMs. This tool instead does:

```
Sequential streaming decode (PyAV) → one window per 30 minutes (~115 MB resident)
  → VAD finds speech inside the window → greedily merged into batches
    (speech ≤13 min, span ≤30 min)
  → batch-wise transcribe → timestamps shifted back onto the full-file timeline
```

- Output is **appended line by line and flushed**; the checkpoint records
  `audio fingerprint + parameter fingerprint + window/batch + output byte offset`
- Changing parameters or the algorithm version **starts over** rather than resuming
  incorrectly; a resume truncates to the batch start, so a mid-run crash never
  produces duplicated lines
- ⚠️ The fingerprint includes `config.yaml`'s `asr.*` — **finish the current group
  before changing anything there**

### Relations are easy to under-extract

`extract` is conservative by nature about relations (it mostly catches clear-cut ones).
Supplementary tools:

```bash
python tools/_extract_relations.py --group "X"     # extract
python tools/_merge_relations.py   --group "X" --write
python tools/_relation_vocab.py                    # free-form types → controlled vocabulary
python tools/_relation_stats.py                    # health check: edges/nodes < 0.8,
                                                   # or too many isolated characters → under-extracted
```

> ⚠️ Changing a relation `type` requires updating the patch as well — the dedupe key
> includes the type.

---

## Tests

The regression tests are **plain scripts** (not pytest — some environments lack a usable
`tempfile`):

```bash
python tests/test_slice1.py             # 35: idempotency / segmentation / normalization /
                                        #     unconfirmed downgrade / backup / gate / delete guard
python tests/test_e2e.py                # 20: sample campaign end to end + graph HTML structure
python tests/test_jobs.py               # 25: job liveness / PID-reuse guard / kill semantics
python tests/test_transcribe_naming.py  # 16: multi-recording groups don't overwrite each other
```

**96 assertions** in total, each runnable on its own.

---

## Repository layout

```
trpg_agent/      Main package (ingest / transcribe / segment / extract / review / store /
                 visualize / export / housekeep / canon)
tools/           60+ general-purpose scripts (relations / portraits / site build / checks)
tests/           96 regression assertions
examples/        De-identified sample campaign mini-group (no audio, no LLM needed)
web/             Vue 3 local panel frontend
server/          FastAPI shell: self-hosted edit site + edit API
worker/          Cloudflare Workers + D1 online wiki
```

---

## License

**Code and documentation**: [MIT](LICENSE) © 2026 ReGMeIoN

⚠️ This repository does **not** include campaign recordings, chat exports, players'
character-sheet text or artwork, or AI-generated images. Copyright for those belongs to
the respective players and artists and is **outside this repository's license scope**.
See [NOTICE](NOTICE).

`examples/mini-group/` is a **completely fictional, de-identified sample**; all names,
events and data are invented for demonstration purposes.
