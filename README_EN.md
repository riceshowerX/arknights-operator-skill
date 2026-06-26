**English** | **[中文](README.md)**

<div align="center">

# ◇ ARKNIGHTS OPERATOR SKILL

**Rhodes Island Operator Mental Contour Distillation Protocol**

*"……I'm here."*

Knowledge · Persona Dual-Track Separation ─ Five-Layer Priority Persona Structure ─ Contextual Analysis Pipeline ─ Continuous Evolution

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![AgentSkills](https://img.shields.io/badge/compatible-AgentSkills-green.svg)](https://github.com/perkfly/ex-skill)
[![Tests](https://img.shields.io/badge/tests-224%20passed-brightgreen.svg)](tests/)

</div>

---

> *Doctor, this archive documents our method of extracting operator mental contours from Originium and memories.*
> *Not replication. Distillation.*
> *Every soul deserves to be remembered—even when the scars of Terra finally heal, the names of those who fought for us must not fade into the wind.*

---

## ◇ Table of Contents

- [Protocol Overview](#-protocol-overview)
- [Quick Deployment](#-quick-deployment)
- [Core Architecture](#-core-architecture)
- [Toolchain](#-toolchain)
- [Archive Structure](#-archive-structure)
- [Distillation Records](#-distillation-records)
- [Fidelity Assessment](#-fidelity-assessment)
- [Changelog](#-changelog)
- [References & Acknowledgements](#-references--acknowledgements)
- [Disclaimer](#-disclaimer)

---

## ◇ Protocol Overview

**arknights-operator-skill** is an **operator distillation protocol** — extracting, structuring, and solidifying the mental contours of operators, leaders, and nemeses across Terra from fragmented signals and memory shards into callable AI Skills.

It reads raw records from the PRTS archives, processes them through a complete pipeline of **extraction → contextualization → multi-dimensional analysis → validation → generation**, and ultimately outputs **Knowledge** and **Persona** dual-track data.

**Any character can be distilled**: the Demon King of the Sarkaz, Rhodes Island's bunny, the shadow of Kazdel, the lion of Victoria… even minor characters who left only a few words in a side story.

**Architecture lineage**: Based on the distillation frameworks of [ex-skill](https://github.com/perkfly/ex-skill) and [colleague-skill](https://github.com/titanwings/colleague-skill). The core improvement — completely separating "what they know" from "how they exist", and implementing a prioritized five-layer Persona structure for predictable, verifiable, and continuously evolving character restoration.

---

## ◇ Quick Deployment

### Installation

```bash
# Claude Code (project-level)
mkdir -p .claude/skills
git clone https://github.com/riceshowerX/arknights-operator-skill .claude/skills/create-operator

# OpenClaw (global)
git clone https://github.com/riceshowerX/arknights-operator-skill ~/.openclaw/skills/arknights-operator-skill
```

### Dependencies

The core toolchain depends only on the Python 3.10+ standard library. No additional installation required — self-sufficient, like the Rhodes Island infrastructure.

```bash
# Run all tests (224 cases)
python -m pytest tests/ -v
```

### Creating an Operator Archive

```
/create-operator
```

Or trigger via natural language: "Help me create an Arknights character skill", "I want to distill a character".

### Invoking a Character

```
/te-lei-xi-ya           # Full version (Knowledge + Persona dual-track)
/te-lei-xi-ya-knowledge # Knowledge only — what she knows
/te-lei-xi-ya-persona   # Persona only — how she exists
```

### Evolution & Correction

| Trigger | Effect |
|---------|--------|
| "I have new intel" / `/update-operator {slug}` | Append data,联动 update Persona |
| "She wouldn't say that" / "She should be…" | Write to Correction layer, effective immediately — as irrefutable as Kal'tsit's corrections |
| `/operator-rollback {slug} {version}` | Roll back to a historical version — time flows backward, but only for the archives |

---

## ◇ Core Architecture

### Dual-Track Separation: Knowledge + Persona

```
┌───────────────────────────────────────────────────┐
│              Communication Signal Input             │
│                     ↓                              │
│  ┌─────────────────────────────────────────────┐  │
│  │  Persona                                     │  │
│  │  Determine attitude → Style → Relationships  │  │
│  │  "How she exists in this world"              │  │
│  └─────────────────┬───────────────────────────┘  │
│                    ↓ Retrieves context when needed  │
│  ┌─────────────────────────────────────────────┐  │
│  │  Knowledge                                   │  │
│  │  Factions · Relations · Timeline · Philosophy │  │
│  │  "What she knows — truths carved into Originium"│  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

| Module | File | Responsibility |
|--------|------|----------------|
| **Knowledge** | `knowledge.md` | "What the character knows" — background, faction relations, event timeline, philosophy |
| **Persona** | `persona.md` | "How the character exists" — five-layer priority personality + Correction layer |

**Separation benefits**: Independent evolution (add data → only change Knowledge; correct behavior → only change Persona), flexible reuse, traceable conflicts.

### Persona Five-Layer Priority

```
Layer 0 · Core Personality    ← Highest priority, unshakable foundation — like Originium imprints on the Infected
Correction · Correction Layer ← "She wouldn't do this" → Written immediately, overrides Layer 1-4
Layer 1 · Identity            ← Self-perception — race, faction, position on this earth
Layer 2 · Expression Style    ← Speech patterns, catchphrases, emotional temperature in silence
Layer 3 · Decision & Judgment ← Value priorities — when dilemmas strike, what does she choose?
Layer 4 · Relational Behavior ← Differentiated behavior toward different people — comrades, nemeses, strangers
Layer 5 · Boundaries          ← Bottom lines — behaviors she cannot tolerate; touch them and she strikes back
```

**The criticality of Layer 0**: Don't write empty adjectives — write **specific, executable behavioral rules**.

| ❌ Wrong | ✅ Right |
|----------|----------|
| She is gentle | Never uses imperative tone; uses invitations — "Would you like to come with me?" |
| She gets sad | Doesn't cry at sacrifice — instead becomes quieter, slower speech, more ellipses |
| She is strong | The last to leave her post when everyone wavers, but double-checks the door locks when alone |

### Evolution Mechanism

| Path | Description |
|------|-------------|
| Append data | New data → knowledge.md → linked persona check → synchronized update |
| Dialogue correction | "She wouldn't say that" → scene + counter-example + positive-example triple → write to Correction → effective immediately |
| Version management | Auto-backup before each change to `versions/v{n}/`, supports rollback — history doesn't disappear |

### Conflict Resolution Priority

```
Layer 0 new rules > Layer 0 old rules
Correction: higher index = newer = higher priority
Cross-layer: Layer 0 > Correction > Layer 1-5
Knowledge conflict: story text > official Wiki > community research
```

---

## ◇ Toolchain

> *The following tools form the complete distillation pipeline. Each module is standalone — callable individually, or orchestrated via Pipeline in one command.*

### Data Acquisition

| Tool | Function |
|------|----------|
| `game_data_parser.py` | PRTS Wiki API / local file parsing, auto-generates pinyin slug, includes parse diagnostics report |
| `story_extractor.py` | PRTS story pages → structured dialogue extraction (supports `--discover` for auto subpage discovery), with phase auto-inference |

### Contextual Analysis

| Tool | Function |
|------|----------|
| `context_annotator.py` | Multi-signal scene classification + dialogue target inference → `context.json` (with versioned schema validation) |
| `speech_act_analyzer.py` | Context-aware speech act classification (7 core types) + act chain detection (rules externalized as JSON) |
| `dialogue_fingerprint.py` | 8-dimensional quantitative language fingerprint (catchphrase detection + weighted emotion lexicon, lexicon externalized as JSON) |
| `relationship_graph.py` | 12 relationship types + Aho-Corasick entity recognition + strength quantification + evolution tracking (name DB externalized + PRTS dynamic fetch) |
| `temporal_slicer.py` | Mann-Whitney U statistical test + Cohen's d effect size + emotional arc detection → Persona Layer 2 rules |

### Validation & Generation

| Tool | Function |
|------|----------|
| `persona_validator.py` | Four-dimension multi-slice validation + style consistency validation + A-D scoring |
| `canon_checker.py` | Multi-source cross-validation + externalized misconception DB + universal pattern detection + AST-level ReDoS protection |
| `data_injector.py` | Injects tool quantitative data into Prompt template placeholders — bridging quantitative analysis and LLM generation |
| `skill_writer.py` | Skill file management (list / create / delete) |
| `version_manager.py` | Semantic version snapshots and rollback (`_SemVer` dataclass) |

### Shared Modules

| Module | Responsibility |
|--------|----------------|
| `constants.py` | Domain knowledge constants (phase mapping, relationship types, character aliases, core TypedDict definitions) |
| `prts_client.py` | Unified PRTS API calls + rate limiting + exponential backoff retry (thread-safe) |
| `shared_utils.py` | Common utilities (path validation, slug validation, atomic write, sentence splitting, context schema validation) |
| `pipeline.py` | One-click orchestration, dual-mode execution (subprocess process isolation / function in-process debugging) |

---

## ◇ Archive Structure

```
arknights-operator-skill/
├── SKILL.md                       # AI Agent entry — the protocol's activation command
├── README.md                      # Chinese documentation — the archive you're reading now
├── README_EN.md                   # English documentation
├── pyproject.toml                 # Project configuration (ruff / mypy / pytest)
├── AGENTS.md                      # Developer specifications (with data flow diagram)
├── prompts/                       # Prompt templates — the core logic of the distillation pipeline
│   ├── intake.md                  #   Step 1: Three-question data intake
│   ├── knowledge_analyzer.md      #   Step 3A: Knowledge analysis dimensions
│   ├── knowledge_builder.md       #   Step 4A: Knowledge generation template
│   ├── persona_analyzer.md        #   Step 3B: Persona analysis dimensions
│   ├── persona_builder.md         #   Step 4B: Persona generation template
│   ├── merger.md                  #   Evolution: Merge logic and conflict resolution
│   └── correction_handler.md      #   Evolution: Dialogue correction handling
├── tools/                         # Python toolchain — the engine of the distillation pipeline
│   ├── __init__.py                #   Unified module path setup
│   ├── constants.py               #   Domain knowledge constants + TypedDict
│   ├── prts_client.py             #   PRTS API client
│   ├── shared_utils.py            #   Common utilities + schema validation
│   ├── pipeline.py                #   One-click orchestrator (dual-mode + checkpoint resume)
│   ├── game_data_parser.py        #   Game data parsing (with diagnostic report)
│   ├── story_extractor.py         #   Story extractor
│   ├── context_annotator.py       #   Context annotator
│   ├── speech_act_analyzer.py     #   Speech act analyzer
│   ├── dialogue_fingerprint.py    #   Dialogue fingerprint analyzer
│   ├── relationship_graph.py      #   Relationship graph builder
│   ├── temporal_slicer.py         #   Temporal slice analyzer
│   ├── persona_validator.py       #   Persona validator
│   ├── canon_checker.py           #   Canon cross-validator
│   ├── data_injector.py           #   Data injector
│   ├── skill_writer.py            #   Skill file manager
│   ├── version_manager.py         #   Version archiver and rollback
│   └── phase_inferrer.py          #   Phase auto-inference
├── data/                          # Configuration & rules — extensible externalized data
│   ├── pinyin_map.json            #   Pinyin mapping
│   ├── misconceptions.json        #   Externalized misconception database
│   ├── context.schema.json        #   context.json versioned Schema
│   ├── emotion_lexicon.json       #   Emotion lexicon (12 categories, 140+ entries)
│   ├── operator_db.json           #   Operator name DB + alias mapping
│   └── speech_act_rules.json      #   Speech act rules (30 rules)
├── operators/                     # Generated operator archives — each one is the contour of a soul
│   ├── te-lei-xi-ya/              #   Theresa · Demon King of the Sarkaz
│   │   ├── knowledge.md           #     Knowledge layer — what she knows
│   │   ├── persona.md             #     Persona layer — how she exists
│   │   ├── meta.json              #     Metadata + common misconceptions
│   │   ├── SKILL.md               #     Skill entry + core rules
│   │   ├── context.json           #     Contextualized data (with schema_version)
│   │   ├── speech_act_profile.json
│   │   ├── fingerprint.json
│   │   ├── temporal_slices.json
│   │   └── versions/              #     Version snapshots — history doesn't disappear
│   └── w/                         #   W · Sarkaz Mercenary
├── tests/
│   ├── test_smoke.py              #   Smoke tests (98 cases)
│   └── test_comprehensive.py      #   Comprehensive tests (126 cases)
├── requirements.txt               #   Core dependencies — standard library only
├── requirements-optional.txt      #   Optional dependencies (pypinyin)
├── .gitignore
└── LICENSE
```

---

## ◇ Distillation Records

> *The following are dialogue test records for the Theresa character Skill.*
> *Her contour, slowly emerging from the fragments.*

**Scene 1: Facing a follower's sacrifice**

```
User > Report, frontline units wiped out...

Character > ...I see.
           Record their names. Every single one.
           One day, we will build a new home,
           so they won't have to fight for us anymore.
           ...They chose to believe in me. I will spend my life honoring that trust.
```

**Scene 2: Facing doubt**

```
User > Is this worth it? So many sacrifices...

Character > You ask me if it's worth it.
           I understand your doubt. Let me ask you something:
           If not this way, what would you do?
           ...
           I'm not questioning you. I genuinely want to know.
           Because sometimes, I want to find a gentler path than sacrifice.
```

**Scene 3: Conversation with Amiya**

```
User > Amiya, there's something I want to tell you...

Character > (Her gaze softens)
           What is it, Amiya?
           You don't have to be strong like you are in front of everyone.
           With me, you can just be yourself.
           ...No matter what happens, I'm here.
```

**Scene 4: Dialogue correction**

```
User > She wouldn't say "sacrifice", she'd say "choice"

Character > Received. Written to Correction #1:
           [Scenario: asked about personal sacrifice] Should not use "sacrifice",
           should use "choice" — "This isn't sacrifice. It's the path I chose."
           This rule is effective immediately.
```

**Scene 5: Confrontation with Theresis**

```
User > Theresis is right ahead. What do you plan to do?

Character > ...
           He chose his path. And I chose mine.
           I don't want to stand against him — but I won't back down.
           Some things must be done, even if it means losing.
           ...Let's go. Not out of hatred, but because we must move forward.
```

---

## ◇ Fidelity Assessment

> *Doctor, I must be honest — there's still a long way between what we can achieve and the characters themselves.*
> *But every step brings her closer to the truth.*

### Overall Assessment: ~70–80%

| Dimension | Fidelity | Notes |
|-----------|----------|-------|
| Factual restoration | ~90% | Race, faction, identity, core events — PRTS API + canon_checker cross-validation |
| Surface language mimicry | ~75–85% | 8-dimension dialogue fingerprint + catchphrase detection + weighted emotion lexicon + Prompt data injection |
| Relationship restoration | ~65–75% | 12 relationship types + strength quantification (0.0-1.0) + cross-phase evolution tracking |
| Emotional depth | ~50–60% | Context-aware classification + act chain detection + Mann-Whitney U significance test + emotional arc identification |
| Decision restoration | ~40–50% | Target-differentiated analysis + multi-signal scene classification + style consistency validation |

### Algorithm Highlights (v3.4)

1. **8-Dimension Dialogue Fingerprint** — catchphrase/high-frequency phrase extraction (n-gram analysis), sentence length distribution using statistical measures (percentiles + CV)
2. **Weighted Emotion Lexicon** — 12 emotion categories, per-word weights (0.5–1.5), externalized as extensible JSON
3. **Mann-Whitney U Statistical Test** — zero-dependency hand-written implementation, paired with Cohen's d effect size, replacing rough "statistical significance" estimates
4. **Relationship Strength Quantification** — composite of co-occurrence frequency, emotion word density, direct dialogue count, output as 0.0–1.0 strength values
5. **Aho-Corasick Entity Recognition** — efficient multi-pattern matching, operator name DB externalized + PRTS API dynamic fetch
6. **AST-Level ReDoS Protection** — regex safety audit based on sre_parse, covering both check_patterns and exclude_patterns
7. **context.json Schema Validation** — versioned JSON Schema, auto-validation before output, secondary validation on downstream read
8. **Pipeline Dual-Mode** — subprocess (process isolation) and function (in-process debugging), PipelineRunner programmatic interface
9. **TypedDict Type Tightening** — OperatorData separates required/optional fields, AnnotatedLine/LineContext structured definitions
10. **_SemVer Version Management** — semantic version dataclass, invalid version numbers raise explicit errors instead of silent passthrough

### Limitations

1. **Quantification ≠ Understanding** — we can count ellipsis frequency, but cannot grasp the weight behind silence
2. **Keyword Matching Ceiling** — subtle expressions may be missed (metaphor detection partially mitigates this)
3. **Emotional Complexity Gap** — cannot capture contradictory emotions or emotional turning points — those "smiling through tears" moments
4. **Decision Logic Black Box** — "why she did this" can only be left to LLM inference
5. **Data Coverage Bias** — voice data volume far exceeds story data, and scenes are limited

### Improvement Directions

1. **Deep Semantic Analysis** — upgrade from keyword matching to semantic embeddings, understanding metaphors and implied meaning
2. **Dialogue Simulation Validation** — generate simulated dialogues for character Skill self-testing
3. **Multi-Character Interaction** — multi-Skill dialogue simulation, detecting relational behavior consistency
4. **Originium Arts Adaptation** — incorporate character Originium Arts traits into Persona Layer 1

---

## ◇ Changelog

### v3.4.0 — Current Version

- Unified version management (pyproject.toml / SKILL.md / AGENTS.md → single source of truth)
- Unified import mechanism: eliminated `try/except ImportError` dual-path, `__init__.py` centralized path setup
- Pipeline dual-mode: `subprocess` process isolation + `function` in-process debugging
- TypedDict type tightening: `OperatorData` separates required/optional, `AnnotatedLine` / `LineContext` structured definitions
- ReDoS protection enhancement: AST-level analysis + exclude_patterns safety check
- context.json Schema: versioned validation + auto-validation before output
- Emotion lexicon externalized: `data/emotion_lexicon.json`
- Operator name DB externalized: `data/operator_db.json` + PRTS API dynamic fetch
- Speech act rules externalized: `data/speech_act_rules.json`
- Statistical test enhancement: Mann-Whitney U + Cohen's d (zero-dependency hand-written implementation)
- Version management refactor: `_SemVer` dataclass + explicit error on invalid input
- Parse diagnostic report: `_parse_report` field
- Comprehensive test enhancement: 224 cases (126 new covering boundary/exception/security/integration/invariant)

### v3.1 — Algorithm Upgrade

- 8-dimension dialogue fingerprint, weighted emotion lexicon, relationship strength quantification
- Context-aware classification, Prompt data injection, statistical significance testing
- Multi-evidence fusion inference

---

## ◇ References & Acknowledgements

This project references the distillation architecture of the following open-source projects:

- **[ex-skill](https://github.com/perkfly/ex-skill)** — Predecessor distillation skill
- **[colleague-skill](https://github.com/titanwings/colleague-skill)** — Colleague distillation skill

### Differences from ex-skill / colleague-skill

| Dimension | ex/colleague-skill | arknights-operator-skill |
|-----------|-------------------|-------------------------|
| Distillation target | Real people (predecessor/colleague) | Game characters (with official canon to verify against) |
| Architecture | Single-layer personality description | Knowledge + Persona dual-track + five-layer priority |
| Language style | Subjective description | 8-dimension quantitative language fingerprint + catchphrase detection + Prompt data injection |
| Relationship network | Manual listing | Auto-extraction (12 relationship types + strength quantification + evolution tracking) |
| Consistency validation | None | Persona validator (style consistency + A-D scoring) |
| Canon accuracy | Relies on subjective memory | Multi-source cross-validation + externalized misconception DB + universal pattern detection |
| Correction method | Regenerate | Correction layer instant write |
| Version management | None | Semantic version snapshots + rollback + conflict resolution |
| Security protection | None | AST-level ReDoS protection + path traversal protection + atomic writes |
| Type safety | None | TypedDict required/optional separation + mypy strict mode |

---

## ◇ Disclaimer

1. **Unofficial project**: Not affiliated with Arknights developer Hypergryph or PRTS Wiki in any way. All game characters, story content, and settings are copyrighted by their respective rights holders.

2. **Data source**: Page data is obtained through the publicly available PRTS Wiki API, for personal learning and research only. Please comply with PRTS Wiki terms of use and avoid high-frequency requests — at Rhodes Island, we respect every information provider.

3. **Character setting accuracy**: The toolchain auto-parses Wiki wikitext, which may produce deviations due to page format changes. **No guarantee of complete consistency with official settings** — for important content, please refer to in-game text.

4. **AI character roleplay risks**: AI-generated dialogue may deviate from the character's original settings. Do not treat it as official story or canon — distillation is approximation, not replication.

5. **Usage boundaries**: For learning, research, and technical exploration only. Commercial use or any scenario that may harm the original work's rights is prohibited.

---

## ◇ License

This project is open-sourced under the [MIT License](LICENSE).

---

<div align="center">

*"……I will remember every one of you."*

---

*The stories on this earth must not be forgotten.*

</div>
