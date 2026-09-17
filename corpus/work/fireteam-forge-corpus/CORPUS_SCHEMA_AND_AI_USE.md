# Corpus Structure and AI Use

## Directory map

- `00_project_context`: Markdown conversions of the three project documents.
- `01_core`: Infantry T&R source plus JMAP and S.P.E.A.R. public evidence.
- `02_training_system`: Marine Corps standards-based training, SATE, event design, evaluation, and data-management publications.
- `03_readiness_and_systems`: METL, MCTIMS, MCCRE, and readiness-reporting policy.
- `04_doctrine`: Learning, warfighting, tactics, and infantry battalion doctrine.
- `05_strategy`: TECOM and service strategy.
- `06_army_cross_service`: Army guides expressly cited by the training deck.
- `07_structured_infantry_events`: One Markdown record per extracted NAVMC 3500.44D event.
- `08_small_unit_doctrine`: Full-text public-release infantry publications supporting battalion-and-below tasks.
- `machine_indexes`: Supplemental JSON indexes for ingestion and validation.

## Publication record schema

Every converted publication begins with YAML front matter containing bibliographic and provenance metadata. The body contains extracted source content. No generated doctrinal content is added.

## Infantry event record schema

Each event file contains YAML fields for `event_code`, `title`, `functional_area`, `event_level`, `source_publication`, `source_date`, `source_currency`, and `classification`. The body preserves labeled fields such as supported METs, evaluation coding, sustainment interval, description, condition, standard, event components or performance steps, references, prerequisites, supporting events, and support requirements.

## Content boundary

Publication bodies contain extracted public-source text. Corpus-created material is limited to file organization, bibliographic and provenance metadata, indexes, hashes, and explicit acquisition or currency warnings. No generated tactics, procedures, standards, definitions, performance thresholds, S.P.E.A.R. metrics, or rubric criteria are included.
