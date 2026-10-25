# Web Novel Writing Skill

[![CI](https://github.com/lenmo181/novel-writing-skill/actions/workflows/verify.yml/badge.svg)](https://github.com/lenmo181/novel-writing-skill/actions/workflows/verify.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Version: v7.51** (2026-10-25) · Author: Yuchen (豫晨) · License: Apache-2.0
> An industrial-grade authoring engine for long-form Chinese web novels, packaged as an **Agent Skill** — a single `SKILL.md` that runs on any Agent Skills–compatible assistant (WorkBuddy, Claude Code, Cursor, Codex, Gemini CLI, Qoder, TRAE, and 20+ more).

This is not a prompt collection, and it is not a novel generator. It is a **traceable, verifiable, regressible production system** for writing Chinese web fiction at scale.

## When to use this skill

Use it when the request involves **Chinese web-novel (网文) writing or manuscript maintenance**:

- Initialize a novel project, build a four-level outline, or scaffold a standard project tree
- Draft chapter N / continue serialization / daily-update writing / one-click generation
- Write short stories (Zhihu Salt-Select, Tomato short stories), or vertical-drama scripts
- Market research (trend scanning), book deconstruction, importing a legacy manuscript
- Chapter review, outline review, continuity checks, "de-AI-flavor" rewriting, read-through smoothing
- Export a submission-ready `.txt`, generate a cover, or render a project dashboard

It does **not** trigger on ordinary copywriting, poetry, or non-fiction writing.

## What makes it different

Most writing skills are a wall of prose rules. This one wraps those rules in an executable pipeline.

- **Nine modes behind one entry point** — long-form, short story, vertical-drama script, trend scanning, book deconstruction, legacy import, review, de-AI-flavor, cover generation.
- **A 30-item chapter gate** — 13 script-enforced hard checks + 17 AI semantic checks. A chapter that fails the hard checks **cannot be delivered**; the validator exits non-zero.
- **Failure codes with defined recoveries** — e.g. `[F-blueprint-mismatch]` forces you to write the outline before the prose; `[F-hook-out-of-bounds]` forces a re-conceived hook; `[F-causality-gap]` forces you to add foreshadowing or cost.
- **Long-series memory** — layered recap archiving, an information-asymmetry matrix, a setting-priority chain, and continuity checks across hundreds of chapters.
- **Optional AI-detection loops** — Zhuque (online) and Mochi (local) checks with targeted 8-gate rewriting.
- **Zero third-party dependencies** — every script is pure Python 3.10+ standard library.

## Installation

This repository is a single Agent Skill. Clone it, or drop it into your assistant's skill directory.

```bash
git clone https://github.com/lenmo181/novel-writing-skill.git
```

For Agent Skills–compatible tools, install the folder into your skills directory (for example `~/.workbuddy/skills/` or `~/.agents/skills/`), then start a new session so the skill list refreshes.

Verify the installation:

```bash
python tools/doctor.py
```

## Quick start

**Step 1 — initialize a project**

> Initialize a project. Title: *Your Title*. Genre: xuanhuan (fantasy). Planned length: 1,000,000 words.

**Step 2 — supply the setting** (or let the AI draft it, then confirm before continuing)

> [Worldview] ... [Protagonist] name, personality, ability, catchphrase, quirk [Relationship equation] ... [Outline] what happens in each volume and chapter

**Step 3 — write chapters**

> Write chapter 1.

Continue with `Write chapter 2`, and so on. To resume after an interruption, just say `continue` or `one-click generate` — progress lives on disk, not in the conversation.

## The 30-item gate

```bash
python tools/check_chapter.py "<path/to/chapter.md>"              # 13 script-enforced hard checks
python tools/review_skeleton.py "<project-root>" <chapter-no>      # scaffold semantic checks 14-30
python tools/chapter_readiness.py "<project-root>" <chapter-no> --full --json   # delivery gate
```

Hard failures (`[✗]`) exit with code 1 and block delivery. Warnings (`[!]`) pass but must be handled one by one. The gate covers pacing, hooks, suspense, POV discipline, "show don't tell", dialogue ratio, causality and cost conservation, and plot-advancement force.

## Repository layout

```
.
├── SKILL.md              # Skill definition (YAML frontmatter + instructions)
├── references/           # 40+ handbooks: writing rules, pacing, review, de-AI-flavor ...
├── tools/                # 40 pure-stdlib Python scripts (validators, generators, dashboards)
├── schemas/              # JSON Schemas for semantic review artifacts
├── templates/            # Project scaffolding templates
├── versions/             # CHANGELOG and historical skill versions
└── tests/                # Regression test suite
```

In published packages, `tools/` is renamed to `scripts/` to match the open-platform convention; relative references are rewritten accordingly.

## Design principles

- **Local-first.** Writing and validation run entirely on your machine. External detection (Zhuque/Mochi) and third-party image generation are opt-in and require explicit consent, because they send text off-device.
- **Read-only by default where it matters.** Pre-release checks never upload; uploading always requires explicit authorization.
- **Fail in place, not in bulk.** Every failure is repaired in the current chapter — the pipeline never "destroys a batch and rewrites it".

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Community

- QQ group: 1016190748 (冷漠网络小说科技交流群①)
- Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
