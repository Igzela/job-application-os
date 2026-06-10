# Workflow: Job Application OS

The core loop that drives every application from raw lead to submitted package.

```
┌─────────┐    ┌───────┐    ┌─────────┐    ┌──────┐    ┌────────┐    ┌──────┐    ┌────────┐
│  Import  │───▶│ Score  │───▶│ Predict │───▶│ Pack │───▶│ Submit │───▶│ Retro │───▶│ Bump   │
│          │    │        │    │         │    │      │    │        │    │       │    │ Rubric │
└─────────┘    └───────┘    └─────────┘    └──────┘    └────────┘    └──────┘    └────────┘
     │                                                                            │
     └──────────────────────── feedback loop ────────────────────────────────────┘
```

---

## Stage 1: Import

**Goal:** Ingest a new job posting into the system.

- Paste the job URL or raw description.
- Extract structured fields: company, role title, location, compensation range, key requirements, nice-to-haves, application deadline.
- Assign a unique application ID.
- Store the raw posting alongside the extracted data for future reference.

**Output:** A new entry in the application tracker with status `new`.

---

## Stage 2: Score

**Goal:** Quantify alignment between the candidate and the role.

- Compare extracted requirements against the candidate profile (skills, experience, preferences).
- Produce a numeric fit score (0–100) across weighted dimensions: technical match, seniority fit, location/remote compatibility, culture signals, compensation alignment.
- Flag any hard blockers (visa, clearance, non-negotiable gaps).
- Log the rubric used and per-dimension breakdown for later calibration.

**Output:** Fit score + dimension breakdown attached to the application entry. Status moves to `scored`.

---

## Stage 3: Predict

**Goal:** Estimate the probability of progressing past each funnel stage.

- Use historical data (past applications, response rates, offer rates) to model P(screen), P(interview), P(offer).
- Factor in company size, hiring velocity, referral presence, and the fit score from Stage 2.
- Produce an expected value: `P(offer) * (offer_value - application_cost)`.
- Rank this application against the current pipeline to decide priority.

**Output:** Stage-by-stage probabilities and expected value. Status moves to `predicted`. If expected value falls below threshold, flag for skip.

---

## Stage 4: Pack

**Goal:** Generate the application materials.

- Tailor resume to the role: reorder sections, emphasize relevant experience, adjust keyword density for ATS.
- Draft cover letter (if required) using the posting highlights and candidate narrative.
- Prepare any supplementary materials: portfolio links, code samples, writing samples.
- Run each artifact through a checklist: no typos, correct company/role name, consistent tense, quantified achievements.

**Output:** A complete application package (resume PDF, cover letter, supporting docs) linked to the application entry. Status moves to `packed`.

---

## Stage 5: Submit

**Goal:** Deliver the application package.

- Submit through the required channel (ATS portal, email, referral intro).
- Record submission timestamp, method, and any contact information captured.
- Confirm receipt if possible (ATS confirmation number, email acknowledgment).
- Set follow-up reminders: thank-you note (24h), status check (7d), second touch (14d).

**Output:** Submission confirmation logged. Status moves to `submitted`.

---

## Stage 6: Retro

**Goal:** Learn from the outcome after the funnel resolves.

- Once a terminal state is reached (rejection, offer, ghosted after 30d), record the outcome.
- Compare predicted probabilities against actual results.
- Identify which rubric dimensions were most predictive and which were noise.
- Note any external factors: timing, referral quality, interviewer signals.

**Output:** Outcome record with actuals vs. predicted. Status moves to `closed`.

---

## Stage 7: Bump Rubric

**Goal:** Update the scoring model using retro data.

- Recalibrate dimension weights based on accumulated retro outcomes.
- Adjust probability models with new data points.
- Update threshold values for skip decisions and priority ranking.
- Archive the old rubric version for traceability.

**Output:** Updated scoring rubric and probability model. Changes apply to all future Stage 2 and Stage 3 runs.

---

## Principles

- **Every stage is observable.** Each stage writes structured output that the next stage consumes.
- **Feedback is mandatory.** The loop closes only when rubrics are updated from real outcomes.
- **Skip early, skip cheap.** Stage 3 exists to avoid wasting effort at Stage 4.
- **Artifacts are reusable.** Stage 4 outputs are templates; the next application starts from a library, not from scratch.
- **The rubric earns its keep.** If bump data shows a dimension has zero predictive power, remove it.
