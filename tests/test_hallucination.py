"""Tests that the evidence validator catches unsupported resume claims.

validate_pack() in pack_generator.py checks that factual claims in generated
packs (resume, cover letter, greeting) are traceable to the evidence bank.
This test module verifies it flags fabricated content.
"""

import pytest

from jobos.models import ApplicationPack
from jobos.pack_generator import validate_pack, _evidence_supports_claim, _build_evidence_corpus


# -- Fixtures -----------------------------------------------------------------

def _make_evidence(skills=None, titles=None, content="", fields=None):
    """Build a single evidence bank entry."""
    return {
        "title": titles or "Project Alpha",
        "content": content or "Built a REST API with Flask and PostgreSQL.",
        "fields": fields or {"Tech": "Python, Flask, PostgreSQL"},
        "skills": skills or ["Python", "Flask", "SQL"],
    }


def _make_pack(resume_text: str, cover_letter: str = "", greeting: str = "") -> ApplicationPack:
    """Build a minimal ApplicationPack with the given resume content."""
    return ApplicationPack(
        job_id="test-job-001",
        files={
            "resume_targeted.md": resume_text,
            "cover_letter.md": cover_letter,
            "greeting.md": greeting,
        },
    )


# -- Claim-level tests --------------------------------------------------------


class TestEvidenceSupportsClaim:
    """_evidence_supports_claim should accept or reject individual claims."""

    def test_supported_claim_passes(self):
        corpus = _build_evidence_corpus([_make_evidence()])
        assert _evidence_supports_claim("Built a REST API with Flask", corpus) is True

    def test_fabricated_claim_fails(self):
        corpus = _build_evidence_corpus([_make_evidence()])
        claim = "Led a team of 15 engineers at Google to launch Kubernetes"
        assert _evidence_supports_claim(claim, corpus) is False

    def test_empty_claim_passes(self):
        """A claim with no extractable keywords should not false-positive."""
        corpus = _build_evidence_corpus([_make_evidence()])
        assert _evidence_supports_claim("---", corpus) is True


# -- Pack-level tests ---------------------------------------------------------


class TestValidatePackCatchesFabrication:
    """validate_pack must flag resumes that contain unsupported claims."""

    def test_clean_resume_no_warnings(self):
        """A resume that only uses evidence-backed content should pass."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Python, Flask, PostgreSQL

- Built a REST API with Flask and PostgreSQL
"""
        pack = _make_pack(resume)
        warnings = validate_pack(pack, [_make_evidence()])
        # No fabricated claims -> no warnings
        assert warnings == []

    def test_fabricated_bullet_flagged(self):
        """A bullet point with no evidence backing must produce a warning."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Python, Flask, PostgreSQL

- Built a REST API with Flask and PostgreSQL
- Reduced infrastructure costs by 40% at Goldman Sachs using Kafka
"""
        pack = _make_pack(resume)
        warnings = validate_pack(pack, [_make_evidence()])

        assert len(warnings) >= 1
        assert any("Goldman Sachs" in w or "Kafka" in w for w in warnings)

    def test_fabricated_field_value_flagged(self):
        """A field value that introduces unsupported technologies must be flagged."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Solidity, WebAssembly, Elixir

- Built a REST API with Flask and PostgreSQL
"""
        pack = _make_pack(resume)
        warnings = validate_pack(pack, [_make_evidence()])

        assert len(warnings) >= 1
        assert any("Unsupported claim in field" in w for w in warnings)

    def test_fabricated_cover_letter_bullet_flagged(self):
        """Cover letter bullets not backed by evidence must be flagged."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Python, Flask, PostgreSQL

- Built a REST API with Flask and PostgreSQL
"""
        cover_letter = """\
Dear Hiring Team,

- **Quantum Computing Lab** (Qiskit): Developed a quantum error correction simulator
"""
        pack = _make_pack(resume, cover_letter=cover_letter)
        warnings = validate_pack(pack, [_make_evidence()])

        assert any("cover_letter.md" in w for w in warnings)

    def test_multiple_fabrications_all_flagged(self):
        """Several fabricated claims should each produce their own warning."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Python, Flask, PostgreSQL

- Built a REST API with Flask and PostgreSQL
- Deployed machine learning models to production at Netflix
- Managed a team of 10 engineers building React Native apps

## Skills

**Languages:** Python, Rust, Haskell, Erlang
"""
        pack = _make_pack(resume)
        warnings = validate_pack(pack, [_make_evidence()])

        # At least the two fabricated bullets + the unsupported field values
        assert len(warnings) >= 3

    def test_fabricated_greeting_claim_flagged(self):
        """Greeting text with unsupported hands-on claims must be flagged."""
        resume = """\
# Jane Doe

## Projects

### Project Alpha

**Tech:** Python, Flask, PostgreSQL

- Built a REST API with Flask and PostgreSQL
"""
        greeting = """\
Hello! I have hands-on experience with blockchain development and smart contracts.
"""
        pack = _make_pack(resume, greeting=greeting)
        warnings = validate_pack(pack, [_make_evidence()])

        assert any("greeting.md" in w for w in warnings)


class TestEmptyPack:
    """Edge cases for empty or minimal packs."""

    def test_empty_resume_produces_warning(self):
        pack = _make_pack("")
        warnings = validate_pack(pack, [_make_evidence()])
        assert any("empty or missing" in w for w in warnings)

    def test_no_evidence_bank_still_runs(self):
        """Validator should not crash when evidence list is empty."""
        resume = """\
# Jane Doe

## Projects

### Some Project

- Did something interesting
"""
        pack = _make_pack(resume)
        warnings = validate_pack(pack, [])
        # With no evidence, everything is unsupported
        assert len(warnings) >= 1
