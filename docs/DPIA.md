# Data Protection Impact Assessment (DRAFT): Hatua

**Status: draft by the developers, not an approved assessment.**
- The school (or other organisation that decides why and how learner data is processed) is the **data controller**. Only it can complete and sign this.
- This draft does **not** follow the ODPC's official DPIA template. The ODPC's *Guidance Note on Data Protection Impact Assessment* includes a template, and the controller should transfer this content into it. We could not retrieve that template's contents when drafting.
- Items in [square brackets] are for the school to fill in. Nothing here is legal advice.
- Read with the ODPC *Guidance Note for the Education Sector* and *Guidance Notes for Processing Children's Data (2025)*.

## 1. Description of the processing

**Purpose.** Help a class teacher notice multi-term strengths and difficulties in a learner's assessment record, early enough to talk with the family. The tool prepares cited drafts. A teacher decides what is saved or shared. It does not assign a pathway, label, score or rank.

**Data subjects.** Learners in Grades 4-9 (children). Teachers (identity and approval records). Guardians appear only as recipients of messages a teacher chooses to send; Hatua collects no guardian contact details and sends nothing.

| Data | Source | Notes |
|---|---|---|
| Pseudonymous learner ID (`HT-xxxx`), first name, sex, grade, stream, year joined, school | School class list | Surnames and contact details are not used. The ID map (real to pseudonymous ID) stays in `data/private/`. |
| Assessment records: learning area, task, rubric level, score, dates, teacher ID | School export | Only columns named in a mapping file are copied. |
| Attendance per term | School export | |
| Teacher notes (free text) | Teacher | **May contain sensitive information.** See risk 2. |
| Teacher identity: ID, name, salted PIN hash; approvals with time and text hash | Registered by the school | Sign-in is optional (`HATUA_REQUIRE_AUTH=1`). |
| Audit log of every tool call | Generated | PINs and session tokens are redacted. |

**Where it runs.** On one school computer. The core makes no network calls. The planner model runs locally through Ollama on a loopback address; other hosts are refused. No cloud service is involved. The demo page contains only fictional learners.

**Retention.** None is automatic. Records, drafts, profiles and logs are plain files. [School to set a retention period and deletion routine.]

## 2. Necessity and proportionality

| Question | Current position | Action for the school |
|---|---|---|
| Lawful basis | Not determined by the developers. | [Decide and record the basis for each purpose; confirm whether guardian consent is needed.] |
| Children's best interests | Teacher-reviewed; no labelling, ranking or pathway advice; guardian sharing needs a separate approval. | [Confirm with school leadership and guardians.] |
| Data minimisation | Pseudonymous IDs, first names only, mapped columns only, personal-looking columns flagged and dropped. | [Review which fields are really needed.] |
| Accuracy | Repairs are flagged, conflicting records are excluded from patterns, late logging is flagged. | Teachers review the "records to check" list. |
| Transparency | The `PRIVACY.md` notice covers the **demo only**. | [Write a notice for guardians and teachers for the real deployment.] |
| Access, correction, erasure | A learner's data is findable by learner ID in `store/`, `profiles/` and `logs/`. No automated routine. | [Define who handles requests and how deletion reaches backups.] |
| Automated decisions | None. Patterns come from fixed rules; a named teacher approves each draft. | Keep the teacher gate. |
| Transfers outside Kenya | None by design. | Do not add hosted models or cloud backups without a new assessment. |
| Registration with the ODPC | Depends on the school's and operator's roles. | [Confirm obligations.] |

## 3. Risks and mitigations

Likelihood and severity are for the school to rate once the deployment is known. Entries below show what exists today.

| # | Risk | Mitigation in the repository | Gap / action |
|---|---|---|---|
| 1 | Someone with access to the computer reads learner files | Local-only design | Files are unencrypted. Use full-disk encryption, separate OS accounts and restricted folder permissions. |
| 2 | Teacher notes contain health, family or other sensitive details | Notes are cited, not quoted; comparison words are blocked | No screening for sensitive content. Train teachers; consider a note policy. |
| 3 | An inaccurate pattern harms a child (stigma, wrong assumption) | Fixed rules; every claim cited; teacher approves; guard blocks labels, ranking and pathways | The guard is a phrase list and can be phrased around. Teacher judgement remains the control. |
| 4 | Someone approves while pretending to be a teacher | Optional PIN sign-in records the registry name and ID, rejects typed names, locks after repeated failures | Off by default. Turn it on for any pilot. It identifies a person among teachers on that computer only; it is not TSC/KEMIS sign-in, and the log files can still be edited by anyone with file access. |
| 5 | Data leaves the device (cloud backup, swapped-in hosted model, tracing) | Loopback-only model endpoint; proxies and redirects disabled | Operator policy: no cloud sync of the Hatua folder; no hosted model. |
| 6 | A family message is sent before a teacher has spoken to the guardian | Hatua sends nothing; guardian text needs a separate sharing approval | School procedure: conversation first, message second. |
| 7 | Data kept longer than needed; erasure not honoured | None | [Retention schedule and deletion procedure.] |
| 8 | Breach not detected or not reported in time | Audit log of tool calls | No incident process in the repository. [Create one; check the notification deadline against ODPC guidance.] |
| 9 | Learners re-identified (small class, first names, IDs) | Pseudonymous IDs; ID map kept private | First names remain in the class list. Consider initials only for pilots. |
| 10 | Poor source data produces false patterns | Flags, conflict exclusion, late-logging warnings | Check flags before relying on a draft. |
| 11 | A future national-system link widens exposure | Not built | New DPIA, data-sharing agreement and read-only, class-scoped access first (`docs/INGESTION.md`). |

## 4. Consultation and sign-off

- [ ] Teachers who will use it consulted
- [ ] Guardian representatives consulted
- [ ] Data protection officer (or equivalent) reviewed
- [ ] ODPC consulted if high risk remains after mitigation
- [ ] Controller sign-off: [name, role, date]

**Review this assessment when:** real data is first loaded; a hosted model, cloud storage or national-system link is added; the fields collected change; or a breach or complaint occurs.
