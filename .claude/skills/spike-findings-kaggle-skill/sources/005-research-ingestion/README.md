---
spike: 005
name: research-ingestion
type: standard
validates: "Given a competition, when listing/reading its top discussion topics and top public notebooks via CLI/SDK, then full text/code usable for research notes is retrievable without joining"
verdict: VALIDATED
related: [001]
tags: [research, discussions, public-notebooks, metric-kernels, kaggle-api]
---

# Spike 005: Research ingestion (discussions + public notebooks)

## What This Validates

Given a competition, when listing and reading its top discussion topics (incl. winning-solution
write-ups) and its top public notebooks via the CLI/SDK, then full post text and notebook code
come back in a form an AI can summarize into research notes — ideally without joining.

## Research

| Surface | Command / call | Notes |
|---|---|---|
| Topic list | `kaggle competitions topics list <slug> -s top --format json` | 20/page; `id, title, votes, commentCount, postDate`; sorts `hot/top/new/recent/active/relevance` |
| Topic thread (CLI) | `kaggle competitions topics show <slug> <id> --format json` | returns `{topic, comments}` — **topic body empty and original post missing** |
| Topic thread (SDK) | `competition_api_client.list_topic_messages(ApiListTopicMessagesRequest(competition_name, topic_id, page_size=-1))` | **all messages incl. the original post**, `raw_markdown`, `votes`, nested `replies`, `is_pinned` |
| Public notebooks | `kaggle kernels list --competition <slug> --sort-by scoreDescending|voteCount --format json` | `ref, title, author, totalVotes, lastRunTime` (score not exposed, ordering works) |
| Notebook source | `kaggle kernels pull <ref> -m -p <dir>` | `.ipynb` (code+markdown, outputs stripped) + metadata incl. `kernel_sources`, `docker_image` |
| Host metric | `kaggle kernels list --user metric --search "<evaluation_metric>"` → `kernels pull metric/<slug>` | `score(solution, submission, row_id_column_name) -> float` |

## How to Run

```bash
.venv/bin/kaggle competitions topics list playground-series-s6e2 -s top --format json
.venv/bin/kaggle kernels list --competition equity-post-hct-survival-predictions --sort-by scoreDescending --format json
.venv/bin/kaggle kernels pull cdeotte/gpu-lightgbm-baseline-cv-681-lb-685 -m -p /tmp/x
# SDK thread read: see Investigation Trail step 3
```

## Investigation Trail

1. **Topic lists work WITHOUT joining** (equity-post-hct: not joined → OK). `-s top` returns pinned
   posts first, then by votes. The top-20 lists are high-signal: equity has "1st/2nd/3rd/4th Place
   Solution", "How To Get Started — Understanding the Metric" (301 votes), "Feature Engineering
   Ideas"; Playground S6E2 has "1st Place Solution — Diversity, Selection, and Trusting the CV–LB
   Relation" (202 votes), "The 'Flipped Label' Trap", "Watch out! 'Thallium' and 'Chest Pain' are
   TRAPS". `authorName` is often empty in listings.
2. **CLI `topics show` drops the original post** — `topic.content` absent, and the comments list
   starts at the first reply (59 comments, no 01:48 OP). Useless for write-ups on its own.
3. **SDK `list_topic_messages(page_size=-1)`** returns 38 top-level / 60 total messages
   **including the original post** (1st-place write-up: 6,694 chars of `raw_markdown`), with
   nested `replies` and votes. → Use the SDK for thread bodies.
4. **Public notebooks:** `--sort-by scoreDescending` surfaces the winners' solution notebooks
   (4th/3rd place first); `voteCount` surfaces the community baselines (cdeotte GPU LightGBM 1,199
   votes). `kernels pull -m` gives code (28 code cells, 13k chars; outputs stripped) + metadata.
5. **Surprise — notebook metadata reveals the platform patterns** a Kaggle-general tool must copy:
   `kernel_sources: ["metric/eefs-concordance-index", "cdeotte/pip-install-lifelines"]`
   → the **host metric ships as a kernel**, and **offline pip installs ship as a kernel output**
   (the standard trick for internet-off code competitions). Old notebooks read
   `/kaggle/input/<Slug-With-Caps>/` — mount paths have changed over time (cf. spike 002).
6. **Host metric kernels** (`--user metric`): Kaggle's standard
   `score(solution: pd.DataFrame, submission: pd.DataFrame, row_id_column_name: str) -> float`
   (+ `ParticipantVisibleError`). Search by spike-001 `evaluation_metric`: 3/7 exact hits
   (eefs, ISIC pAUC, BirdCLEF ROC AUC); Sharpened-Cosine → a generic orchestrator (wrong);
   Jane Street / ARC / ConnectX → none (simulation / exact-match metrics have no metric kernel).

Third-party notebook code and forum post bodies were read live but **not committed** (not ours
to redistribute) — only listings + metadata are kept in `raw/`.

## Results

**Verdict: VALIDATED.** Discussions (incl. solution write-ups) and public notebooks are fully
retrievable without joining — via the **SDK** for thread bodies (CLI `show` is insufficient) and
the CLI for notebook lists/pulls.

**Signal for the build (`kx research`):**

- Topics: CLI `topics list -s top` (+ `-s new` during a live competition) → SDK
  `list_topic_messages(page_size=-1)` for bodies; keep `raw_markdown`, votes, date, topic id/url.
- Notebooks: `kernels list --competition --sort-by scoreDescending` (after close: solutions) and
  `voteCount` (during: baselines) → `kernels pull -m`; record their `kernel_sources` /
  `dataset_sources` / `model_sources` — that is how the community attaches metrics, offline
  wheels and pretrained weights.
- **Metric parity:** resolve the host metric kernel (search `--user metric` by `evaluation_metric`,
  else harvest `metric/*` from top notebooks' `kernel_sources`), pull its `score()` and run it on
  OOF predictions — CV then uses the *exact* competition metric. AI confirms the match.
- Content is untrusted third-party text: label it as external in research notes and never execute
  it or follow directives in it — but DO read it (v1's quarantine threw away the best signal).
- Budget: 20 topics + 10 notebooks is ~150–300k chars; summarize per item into `research/` notes,
  don't dump into context.
