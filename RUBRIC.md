# Job Scoring Rubric v0

## Final Score Formula

```
final_score = 0.30*fit + 0.25*evidence + 0.20*opportunity + 0.15*strategic - 0.10*friction - 0.20*risk
```

All dimensions are scored 0-10 unless otherwise noted.

## Hard Gates (Auto-Reject)

If any of the following conditions are true, the job is automatically rejected with a final score of 0 regardless of other dimensions:

- **Availability conflict** -- the role requires start dates, shift schedules, or on-site presence that conflict with current commitments
- **Missing critical skills** -- the job requires a skill listed as "required" (not "nice-to-have") that cannot be acquired within the ramp-up period
- **Unrelated field** -- the role is in a domain with no meaningful overlap to target career trajectory (e.g. sales role for an engineering candidate)
- **Live platform requiring login** -- the application portal requires account creation or login to a platform not already possessed, and no alternative submission path exists

## Dimensions

### Fit (weight: 0.30)

How well the role aligns with skills, experience level, and career direction.

| Score | Meaning |
|-------|---------|
| 9-10  | Near-perfect match: required skills, experience band, and domain all align |
| 7-8   | Strong match: most required skills present, minor gaps in nice-to-haves |
| 5-6   | Moderate match: core skills transferable, meaningful ramp-up needed |
| 3-4   | Weak match: significant skill gaps or seniority mismatch |
| 1-2   | Poor match: role is a stretch in multiple dimensions |

### Evidence (weight: 0.25)

How much concrete evidence (portfolio, past work, metrics) can be cited to support the application.

| Score | Meaning |
|-------|---------|
| 9-10  | Multiple direct examples with measurable outcomes ready to cite |
| 7-8   | Strong examples exist, may need minor tailoring |
| 5-6   | Some relevant examples, requires reframing or inference |
| 3-4   | Few direct examples; application would rely heavily on potential |
| 1-2   | No meaningful evidence to point to |

### Opportunity (weight: 0.20)

Value of the role as a career stepping stone: growth, network, compensation, learning.

| Score | Meaning |
|-------|---------|
| 9-10  | Exceptional growth potential, brand-name signal, or comp jump |
| 7-8   | Clear advancement path, strong company/team signal |
| 5-6   | Lateral move with some upside |
| 3-4   | Limited growth, stagnant team, or below-market comp |
| 1-2   | Career regression or dead-end |

### Strategic (weight: 0.15)

Long-term positioning value: does this role open doors, build a narrative, or fill a gap in the career story.

| Score | Meaning |
|-------|---------|
| 9-10  | Unlocks a target niche, completes a narrative arc, or adds a missing credential |
| 7-8   | Strengthens positioning in a target direction |
| 5-6   | Neutral: neither helps nor hurts long-term story |
| 3-4   | Slightly off-target; could confuse the career narrative |
| 1-2   | Actively misaligns with stated goals |

### Friction (weight: -0.10, subtracted)

Practical obstacles: lengthy applications, relocation, take-home assignments, poor UX.

| Score | Meaning |
|-------|---------|
| 1-2   | One-click apply, no hoops |
| 3-4   | Standard application: resume + cover letter |
| 5-6   | Moderate friction: custom questions, portfolio assembly |
| 7-8   | High friction: multi-stage process, take-home, timed assessment |
| 9-10  | Extreme friction: case study, presentation, or weeks-long process |

### Risk (weight: -0.20, subtracted)

Downside probability: offer rescission, layoff likelihood, toxic culture signals, visa/contract issues.

| Score | Meaning |
|-------|---------|
| 1-2   | Stable company, clean Glassdoor, known team |
| 3-4   | Minor concerns: recent layoffs in other departments, mixed reviews |
| 5-6   | Moderate risk: startup without runway clarity, contract-to-hire |
| 7-8   | High risk: high turnover signals, unclear funding, bad interview experience |
| 9-10  | Critical risk: company in distress, contract ambiguity, known toxic culture |
