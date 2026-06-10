# v0 Rubric: Student Internship Scoring

## Overview

This rubric scores internship postings across 6 dimensions on a 0-10 scale. Each dimension has a weight reflecting its importance to the applicant's priorities. Hard gates disqualify postings that fail non-negotiable criteria regardless of weighted score.

---

## Dimensions

### 1. Skill Match (weight: 30%)

How well the posting's required/preferred skills align with the applicant's skill set (Python, JavaScript, React, data analysis, ML basics, SQL).

| Score | Criteria |
|-------|----------|
| 0-1   | No overlap with applicant skills |
| 2-3   | 1-2 minor skills match (e.g., generic "programming") |
| 4-5   | 2-3 core skills match (e.g., Python + one framework) |
| 6-7   | Most required skills match; preferred skills partially match |
| 8-9   | All required skills match; most preferred skills match |
| 10    | Perfect overlap -- every listed skill is in applicant's toolkit |

### 2. Role Fit (weight: 20%)

How well the role description matches the applicant's interests (backend, data, ML, full-stack) and career trajectory.

| Score | Criteria |
|-------|----------|
| 0-1   | Completely misaligned role (e.g., hardware, marketing) |
| 2-3   | Tangentially related (e.g., QA-only, IT support) |
| 4-5   | General SWE role with some relevant work |
| 6-7   | Primarily in a target domain (backend, data, ML, or full-stack) |
| 8-9   | Directly in a preferred domain with growth potential |
| 10    | Dream role -- exact domain, interesting problems, mentorship mentioned |

### 3. Compensation (weight: 15%)

Hourly rate or stipend. Assumed unpaid if not stated.

| Score | Criteria |
|-------|----------|
| 0-1   | Unpaid or below $15/hr |
| 2-3   | $15-$20/hr |
| 4-5   | $20-$30/hr |
| 6-7   | $30-$40/hr |
| 8-9   | $40-$55/hr |
| 10    | $55+/hr or includes housing/relocation stipend |

### 4. Company Signal (weight: 15%)

Brand recognition, engineering culture indicators, team size, and growth trajectory.

| Score | Criteria |
|-------|----------|
| 0-1   | No online presence; unknown; red flags (e.g., MLM, staffing agency) |
| 2-3   | Small unknown company with minimal signal |
| 4-5   | Established company; no specific engineering culture signals |
| 6-7   | Known company or strong signals (open source, tech blog, good Glassdoor) |
| 8-9   | Strong brand; known for engineering excellence; good intern programs |
| 10    | Top-tier brand with structured intern program and return offer pipeline |

### 5. Location / Remote (weight: 10%)

Alignment with target locations or remote/hybrid flexibility.

| Score | Criteria |
|-------|----------|
| 0-1   | Requires relocation to non-target area; no remote option |
| 2-3   | In a non-target city; hybrid with infrequent remote |
| 4-5   | Hybrid in a target city |
| 6-7   | Fully remote or in a preferred target city (SF, Seattle, NYC, Austin) |
| 8-9   | Fully remote with optional in-person in a target city |
| 10    | Fully remote, async-friendly, no location restrictions |

### 6. Timing / Duration (weight: 10%)

Alignment with the applicant's availability window (Jun 1 - Aug 15, 2026) and commitment level.

| Score | Criteria |
|-------|----------|
| 0-1   | Dates conflict entirely; requires unavailable period |
| 2-3   | Partial overlap; demands >40 hrs/week during school |
| 4-5   | Acceptable dates but shorter than ideal (<8 weeks) |
| 6-7   | Fits availability; 8-10 weeks; full-time |
| 8-9   | Perfect fit within availability; 10-12 weeks; full-time |
| 10    | Flexible start/end within window; 12+ weeks possible |

---

## Hard Gate Rules

**Any single failure below disqualifies the posting from consideration, regardless of weighted score.**

| Gate | Rule | Rationale |
|------|------|-----------|
| G1 | `graduation_date >= 2026-06-01` | Must still be enrolled or graduating after internship start |
| G2 | `compensation >= $0` | Must not require the intern to pay (no "pay-to-play" programs) |
| G3 | `availability_overlap >= 6 weeks` | Posting dates must overlap at least 6 weeks with Jun 1 - Aug 15 window |
| G4 | `location_reachable == true` | Must be in a reachable location (target city, remote, or relocation covered) |
| G5 | `not_staffing_agency` | Posting must be from the actual employer, not a staffing/body shop |
| G6 | `skill_match >= 2` | Must match at least 2 of the applicant's core skills |

---

## Scoring Formula

```
weighted_score = (
    skill_match      * 0.30 +
    role_fit         * 0.20 +
    compensation     * 0.15 +
    company_signal   * 0.15 +
    location_remote  * 0.10 +
    timing_duration  * 0.10
)

final_score = weighted_score IF all hard gates pass, ELSE disqualified
```

### Score Tiers

| Tier | Weighted Score | Action |
|------|---------------|--------|
| S    | 8.5 - 10.0    | Apply immediately; prioritize |
| A    | 7.0 - 8.4     | Apply; strong candidate |
| B    | 5.5 - 6.9     | Apply if capacity allows |
| C    | 4.0 - 5.4     | Low priority; apply only if nothing else |
| D    | 0.0 - 3.9     | Skip |

---

## Usage

Each posting is evaluated against this rubric. The evaluator assigns a 0-10 integer score for each dimension, checks all hard gates, computes the weighted score, and assigns a tier. Disqualified postings (failed gate) are excluded from tier ranking.

This is v0. Weights and thresholds will be recalibrated after reviewing the first batch of scored postings.
