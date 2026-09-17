# Requirements Document

## Introduction

This document defines the requirements for a **2-day hackathon prototype** of the T&R Rubric Evaluation Generator. The prototype automates two stages of the ADDIE instructional design lifecycle for Marine Corps infantry training: the **Design Stage** (generating a structured performance rubric from a Training & Readiness task standard) and the **Evaluate Stage** (scoring an observed performance against an approved rubric).

The build is deliberately scoped down. It is the smallest working end-to-end slice that a two-person, non-software-engineering team can operate for a live demo. The fuller AWS/ADDIE production architecture (Bedrock multi-agent orchestration, five knowledge bases, Neptune, multi-tenant IAM, GovCloud, offline-first PWA, and related infrastructure) is an explicit **post-event roadmap** and is out of scope for this build. The Analyze, Develop, and Implement ADDIE stages are also out of scope and are referenced only as future phases.

The system generates rubrics built from KSTs (Knowledge/Skill/Task statements), organized under the S.P.E.A.R. dimensions, using BARS (Behaviorally Anchored Rating Scale) methodology. Tier names, competency ladder, and S.P.E.A.R. dimensions are configuration-driven so the tool is honestly reusable for other tasks later. Every behavioral anchor must be traceable to source standard text; unsupported content is flagged rather than invented. A human Subject Matter Expert reviews and approves rubrics before they are finalized.

The Design Stage sources tasks and text from a structured Source Corpus. The selectable task list is populated from a machine-readable Event Index (`machine_indexes/events.json`), and the source text for a selected task is loaded by an exact index-based lookup of the corresponding Structured Event Record file. There is no filename matching, keyword retrieval, embeddings, vector store, or fuzzy matching in this build. The corpus works from a public proxy of the controlled T&R manual, and every generated rubric surfaces provenance (source currency and date) and a visible caveat to that effect. The S.P.E.A.R. dimension framework is never grounded in corpus text; it is sourced exclusively from the local Config File.

## Glossary

- **System**: The T&R Rubric Evaluation Generator web application built in this prototype.
- **ADDIE**: The instructional design lifecycle (Analyze, Design, Develop, Implement, Evaluate). Only Design and Evaluate are in scope.
- **T&R**: Training & Readiness. The source standard used to generate rubrics. For this demo, tasks originate from the Infantry T&R Manual (NAVMC 3500.44D).
- **T&R Task**: A single training task standard identified by a T&R code (e.g., INF-MAN-4001), which serves as the source for rubric generation. Corresponds to an event_code in the Event Index.
- **Source Corpus**: A locally provided folder structure of doctrine, T&R manuals, and publications that serve as reference source text. Includes the `07_structured_infantry_events/` records, the `machine_indexes/` folder, `01_core/`, and supporting folders `02` through `08`.
- **Event Index**: The machine-readable index file `machine_indexes/events.json`, a flat array of all 538 events. Each entry carries `event_code`, `title`, `functional_area`, `event_level`, `file` (bare filename), and boolean population flags (`has_condition`, `has_standard`, `has_components_or_steps`). The index does NOT carry `source_publication`, `source_date`, or `source_currency` — those live in the Structured Event Record front matter. The index is the task selector's data source for the list; the corpus folder is never scanned directly. The selectable task list is restricted to NAVMC 3500.44D events, evaluated against the record `source_publication` field; in the current corpus all 538 events are NAVMC 3500.44D.
- **Structured Event Record**: A single pre-extracted T&R event file under `07_structured_infantry_events/` (one file per event). Each record has YAML front matter (event_code, title, functional_area, event_level, source_publication, source_date, source_currency, classification) and labeled sections: Condition, Standard, Performance Steps, Primary Reference, and provenance fields.
- **Grounding Fields**: The Condition, Standard, and Performance Steps labeled sections of a Structured Event Record, used specifically as the source text passed to generation and as the basis for the traceability check.
- **source_currency**: A provenance field on a Structured Event Record describing how current the source is relative to the controlled publication (notes that NAVMC 3500.44D was superseded by NAVMC 3500.44E, which was not publicly downloadable when the corpus was built).
- **source_date**: A provenance field on a Structured Event Record indicating the date of the source publication.
- **Provenance Caveat**: A visible, non-hideable statement displayed on every generated rubric stating that the corpus works from a public proxy of the controlled T&R manual, not the current controlled version.
- **Project Context Files**: Files under `00_project_context/` (thesis proposal, hackathon gameplan, training intro doc). Internal project reference only; never retrieved as doctrinal source material for a generated rubric.
- **KST**: A Knowledge/Skill/Task statement. The atomic unit of a rubric.
- **S.P.E.A.R. Dimension**: One of the performance dimensions a KST is organized under (default: Speed, Precision, Executive Control, Adaptability, Risk Exposure). Configuration-driven, not hardcoded. The five dimensions and their definitions are sourced exclusively from the Config File and are never present in or grounded from the Source Corpus.
- **Competency Level**: A tag on each KST indicating difficulty (default ladder: Foundation, Intermediate, Expert). Configuration-driven.
- **Rubric Tier**: A rating level with a behavioral anchor (default: Unsatisfactory (1) / Satisfactory (2) / Proficient (3)). Configuration-driven in name and count.
- **BARS**: Behaviorally Anchored Rating Scale. Each rubric tier carries a concrete behavioral anchor.
- **Behavioral Anchor**: A concrete, observable description of performance at a specific rubric tier.
- **Traceability Flag**: A per-anchor indicator (yes/no plus supporting excerpt) showing whether the anchor is supported by the source standard text.
- **SME**: Subject Matter Expert. The human reviewer who edits, approves, or rejects generated rubric content.
- **Rubric Version**: An immutable snapshot of an approved rubric.
- **Config File**: A single local JSON file holding tier names/count, competency ladder, and S.P.E.A.R. dimensions.
- **Model_Client**: The single abstraction function through which all model calls are made, enabling one-line model/endpoint swaps.
- **Model_Endpoint**: The local or remote inference endpoint (default: Nemotron-3-Lightning-30b) invoked through the Model_Client.
- **Performance Description**: Free text describing an observed performance, entered for scoring during the Evaluate Stage.
- **Demo Scenario**: A prewritten Performance Description available for selection during a demo.
- **Rubric Schema**: The fixed structured output format for a generated KST (kst_id, statement, competency_level, spear_dimension, tier, behavioral_anchor, traceable_to_source).

## Requirements

### Requirement 1: Task and Source Selection

**User Story:** As an instructional designer, I want to select a T&R task from the Event Index and have its structured event record loaded by exact index reference, so that rubric generation is grounded in the correct pre-extracted source text.

#### Acceptance Criteria

1. WHEN the Design Stage loads, THE System SHALL populate the selectable T&R Task list from the Event Index (`machine_indexes/events.json`) using each event's event_code and title.
2. THE System SHALL derive the selectable T&R Task list exclusively from the Event Index and SHALL NOT scan the `07_structured_infantry_events/` folder or use a hardcoded task list.
3. THE System SHALL restrict the selectable T&R Task list to events whose Structured Event Record `source_publication` front-matter field is the Infantry T&R Manual (NAVMC 3500.44D) and SHALL exclude any event sourced from another publication. NOTE: the Event Index does not carry `source_publication`; this constraint is evaluated against the record front matter. In the current corpus all events are NAVMC 3500.44D, so no event is excluded, but the constraint guards against future mixed-source corpora.
4. WHEN the instructional designer selects a T&R Task, THE System SHALL load the corresponding Structured Event Record file from `07_structured_infantry_events/` using the `file` field of that event's Event Index entry as an exact reference.
5. THE System SHALL load the Structured Event Record by exact index reference and SHALL NOT perform filename matching, section matching, keyword retrieval, fuzzy matching, embeddings, or vector-store lookup against the Source Corpus.
6. IF the Structured Event Record file referenced by the selected event's `file` field cannot be found or read, THEN THE System SHALL display an error indicating the source record could not be loaded.
7. THE System SHALL display the loaded Structured Event Record source text to the instructional designer before rubric generation.
8. THE System SHALL display the selected event's source_currency and source_date to the instructional designer before rubric generation.

### Requirement 2: Design Stage Rubric Generation

**User Story:** As an instructional designer, I want the system to generate a rubric whose observable metrics are anchored to the task's performance steps, using S.P.E.A.R. as the lens for phrasing each metric, so that every metric is legitimately derived from what the task requires.

#### Acceptance Criteria

1. WHEN the instructional designer initiates rubric generation for a selected T&R Task, THE System SHALL call the Model_Client with the selected Structured Event Record's Grounding Fields (Condition, Standard, and Performance Steps) as the source text, the S.P.E.A.R. and BARS scaffold, and one to two hand-written example rubrics as few-shot grounding.
2. THE System SHALL parse the selected event's Performance Steps into an ordered list of discrete Performance Steps and use that list as the organizing backbone of the generated rubric.
3. THE System SHALL generate one or more Observable Metrics for each Performance Step, where each Observable Metric conforms to the Rubric Schema containing metric_id, statement, spear_dimension, competency_level, step_ref, anchors (one behavioral anchor per Rubric Tier), and step_derived.
4. THE System SHALL tag each Observable Metric with exactly one S.P.E.A.R. Dimension from the Config File, using S.P.E.A.R. as the lens through which the metric views its Performance Step rather than as the top-level organizing structure.
5. THE System SHALL assign each Observable Metric a competency_level from the competency ladder defined in the Config File and one behavioral anchor per Rubric Tier defined in the Config File.
6. WHEN an Observable Metric is derived from a Performance Step, THE System SHALL set step_ref to that Performance Step's number and set step_derived to yes.
7. IF an Observable Metric cannot be tied to any Performance Step, THEN THE System SHALL set step_derived to no and flag the metric for SME review as not step-derived.
8. THE System SHALL produce generated output matching the structural shape of the reference rubric, including a Task Attributes header (T&R Code, Echelon, Sustainment Interval, Condition, Standard, Key Performance Steps, Reference), Performance Steps as the backbone, a per-metric Observable Metric statement, and a table with one behavioral anchor per Rubric Tier.
9. IF the Model_Endpoint returns output that does not conform to the Rubric Schema, THEN THE System SHALL display an error indicating the output could not be parsed.
10. THE System SHALL display the selected event's source_currency and source_date next to the generated rubric.
11. THE System SHALL display the Provenance Caveat on every generated rubric, stating that the corpus works from a public proxy of the controlled T&R manual (NAVMC 3500.44D superseded by NAVMC 3500.44E, which was not publicly downloadable when the corpus was built) and not the current controlled version.
12. THE System SHALL keep the Provenance Caveat visible on every generated rubric.

### Requirement 3: Rubric Review and Approval

**User Story:** As an SME, I want to review the generated rubric side-by-side with the source standard and edit or approve each KST, so that I can ensure the final rubric is accurate and grounded in the source.

#### Acceptance Criteria

1. THE System SHALL display the source standard (including the ordered Performance Steps) alongside the generated Observable Metrics on the review screen.
2. THE System SHALL allow the SME to inline edit any field of a generated Observable Metric.
3. THE System SHALL allow the SME to approve or reject each Observable Metric individually.
4. THE System SHALL visually distinguish Observable Metrics with step_derived set to no from Observable Metrics with step_derived set to yes.
5. WHEN the SME initiates locking a rubric that contains one or more Observable Metrics whose step_derived is set to no, THE System SHALL warn the SME identifying the metrics that are not step-derived and SHALL require the SME to explicitly acknowledge them before locking.
6. IF the SME does not acknowledge the metrics that are not step-derived identified in the warning, THEN THE System SHALL NOT lock the rubric as a Rubric Version.
7. WHEN the SME locks a rubric, THE System SHALL exclude any Observable Metric marked rejected from the locked Rubric Version.
8. WHEN the SME approves and locks a rubric, THE System SHALL lock the rubric as a Rubric Version.
9. WHILE a rubric is locked as a Rubric Version, THE System SHALL prevent edits to that Rubric Version.

### Requirement 4: Evaluate Stage Performance Scoring

**User Story:** As an evaluator, I want to score an observed performance against an approved rubric, so that I can produce a structured result to hand to a commander.

#### Acceptance Criteria

1. THE System SHALL allow the evaluator to select an approved Rubric Version for scoring.
2. THE System SHALL allow the evaluator to enter or paste a Performance Description.
3. THE System SHALL allow the evaluator to select a prewritten Demo Scenario as the Performance Description.
4. WHEN the evaluator submits a Performance Description for a selected Rubric Version, THE System SHALL call the Model_Client to score the performance against each KST and Rubric Tier.
5. THE System SHALL produce a structured score per KST and Rubric Tier.
6. THE System SHALL produce a plain-language summary of the scoring result.
7. THE System SHALL display the Provenance Caveat on the evaluation result, stating that the underlying rubric derives from a public proxy of the controlled T&R manual and not the current controlled version.
8. IF no approved Rubric Version exists, THEN THE System SHALL display a message indicating that an approved rubric is required before evaluation.

### Requirement 5: Configuration-Driven Rubric Structure

**User Story:** As an instructional designer, I want tier names, the competency ladder, and the S.P.E.A.R. dimensions to live in a single local config file, so that the tool is reusable for other tasks without code changes.

#### Acceptance Criteria

1. THE System SHALL read Rubric Tier names and count from the Config File.
2. THE System SHALL read the competency ladder from the Config File.
3. THE System SHALL read the S.P.E.A.R. Dimensions from the Config File.
4. THE System SHALL store the Config File as a single local JSON file.
5. WHEN the Config File defines Rubric Tiers, THE System SHALL use those tier names and count in both the Design Stage and the Evaluate Stage.
6. IF the Config File is missing or cannot be parsed, THEN THE System SHALL display an error indicating the configuration could not be loaded.
7. IF the Config File defines an empty or zero-length Rubric Tier list, competency ladder, or S.P.E.A.R. Dimension list, THEN THE System SHALL display an error identifying the invalid configuration section.

### Requirement 6: Model Abstraction

**User Story:** As a developer, I want all model calls routed through a single function, so that swapping models or endpoints later is a one-line change rather than a rewrite.

#### Acceptance Criteria

1. THE System SHALL route all model inference calls through a single Model_Client function.
2. THE System SHALL use Nemotron-3-Lightning-30b at the local Model_Endpoint as the default model.
3. WHERE an alternate model is configured, THE System SHALL invoke the alternate Model_Endpoint through the Model_Client using the same Rubric Schema.
4. THE System SHALL confine the Model_Endpoint selection to a single configurable location in the code.

### Requirement 7: Scope Boundaries and Documentation

**User Story:** As a stakeholder, I want the prototype to clearly document what is built now versus deferred, so that the demo accurately represents scope and the production roadmap.

#### Acceptance Criteria

1. THE System SHALL name the Analyze, Develop, and Implement stages as future phases in the user interface or README.
2. THE System SHALL provide a README documenting what is built in this prototype and what is deferred to the production roadmap.
3. THE System SHALL exclude Bedrock multi-agent orchestration, Step Functions, ECS/Fargate, segmented knowledge bases, OpenSearch, Aurora pgvector, Neptune, DynamoDB, multi-tenant IAM, Cognito, offline-first PWA, AppSync/DataStore, IoT Greengrass, Snowball Edge, CodePipeline/GitHub contributor path, training-provider integration, and GovCloud/compliance controls from the prototype implementation.

### Requirement 8: Demo Operability and Resilience

**User Story:** As a two-person non-software team, I want the app to run as a simple live demo with a recorded backup, so that we can present reliably even if something breaks on stage.

#### Acceptance Criteria

1. THE System SHALL run as a web application covering the Design Stage and the Evaluate Stage.
2. THE System SHALL operate without cloud infrastructure provisioning beyond default hosting.
3. THE System SHALL provide at least one prewritten Demo Scenario for the Evaluate Stage so a demo can proceed without live authoring.
4. IF the Model_Endpoint is unavailable, THEN THE System SHALL display an error indicating the model could not be reached.

### Requirement 9: S.P.E.A.R. Framework Grounding Boundary

**User Story:** As an instructional designer, I want the S.P.E.A.R. dimension definitions to come only from the Config File, so that the tool never invents or grounds the framework in corpus text that does not contain it.

#### Acceptance Criteria

1. THE System SHALL source the S.P.E.A.R. Dimensions and their definitions used in any prompt or generation step exclusively from the Config File.
2. THE System SHALL exclude S.P.E.A.R. Dimension definitions from any source text retrieved from the Source Corpus.
3. WHEN the System constructs a generation prompt, THE System SHALL populate the S.P.E.A.R. framework from the Config File and SHALL ground S.P.E.A.R. Dimension definitions only in the Config File.
4. IF the Config File does not define the S.P.E.A.R. Dimensions, THEN THE System SHALL display an error indicating the S.P.E.A.R. configuration is required.

### Requirement 10: Source Content and Step-Derivation Boundaries

**User Story:** As a stakeholder, I want the task's Performance Steps to be the source of truth for observable metrics and internal project files excluded from doctrinal retrieval, so that generated rubrics stay grounded in what the task actually requires.

#### Acceptance Criteria

1. THE System SHALL treat the selected event's Performance Steps as the source of truth against which each Observable Metric's step_derived judgment is made.
2. THE System SHALL treat Source Corpus publication content as source input for generation and SHALL NOT treat it as already-generated rubric material.
3. THE System SHALL exclude Project Context Files (`00_project_context/`) from any doctrinal source retrieval used for rubric generation.
4. WHEN the System determines step_derived for an Observable Metric, THE System SHALL evaluate whether the metric corresponds to one of the selected event's Performance Steps and SHALL record the referenced Performance Step number when it does.
4. WHEN the System evaluates traceable_to_source, THE System SHALL compare generated behavioral anchors against the selected event's Grounding Fields extracted from public-source text.
