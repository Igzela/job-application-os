"""Tests for profile source consistency."""

from __future__ import annotations

from jobos.profile_loader import validate_profile_consistency


def test_profile_consistency_detects_school_and_major_conflicts() -> None:
    profile = {
        "school": "长春理工大学",
        "major": "过程装备与控制工程",
        "education": [
            {
                "institution": "University of California, Berkeley",
                "major": "Computer Science",
            }
        ],
    }

    errors = validate_profile_consistency(profile)

    assert any("school" in error for error in errors)
    assert any("major" in error for error in errors)


def test_profile_consistency_accepts_matching_year_formats() -> None:
    profile = {
        "school": "长春理工大学",
        "major": "过程装备与控制工程",
        "graduation_date": "2027",
        "education": [
            {
                "institution": "长春理工大学",
                "major": "过程装备与控制工程",
                "graduation_date": "2027-06-30",
            }
        ],
    }

    assert validate_profile_consistency(profile) == []
