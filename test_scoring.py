import pytest

from scoring import (
    _clip,
    calculate_score,
    get_priority_bucket,
    get_suggested_action,
    to_score_1_10,
)


def test_perfect_site():
    score, _ = calculate_score({"http_status":200,"response_time_ms":300,"title":"X","html_size":250000,"is_parked":False,"spammy_tld":False,"tld":"com","error":None})
    assert score == 90
    assert get_priority_bucket(score) == "high"

def test_parked_skip():
    facts = {"http_status":200,"response_time_ms":500,"title":"For sale","html_size":3000,"is_parked":True,"spammy_tld":True,"tld":"xyz","error":None}
    score, _ = calculate_score(facts)
    assert get_suggested_action(score, facts) == "skip"

def test_dead_domain():
    score, _ = calculate_score({"http_status":None,"error":"connection_error","is_parked":False,"spammy_tld":False})
    assert score < 25
    assert get_priority_bucket(score) == "skip"

def test_empty_facts():
    score, _ = calculate_score({})
    assert score == 50


# --- bucket boundaries -------------------------------------------------

@pytest.mark.parametrize("score,expected_bucket", [
    (75, "high"),
    (74, "medium"),
    (50, "medium"),
    (49, "low"),
    (25, "low"),
    (24, "skip"),
    (0, "skip"),
    (100, "high"),
])
def test_bucket_boundaries(score, expected_bucket):
    assert get_priority_bucket(score) == expected_bucket


# --- recommendation (action) thresholds --------------------------------

@pytest.mark.parametrize("score,expected_action", [
    (75, "review_for_outreach"),
    (74, "manual_review"),
    (50, "manual_review"),
    (49, "deprioritize"),
    (25, "deprioritize"),
    (24, "skip"),
])
def test_action_thresholds_no_error_not_parked(score, expected_action):
    facts = {"error": None, "is_parked": False}
    assert get_suggested_action(score, facts) == expected_action

def test_action_parked_overrides_high_score():
    facts = {"error": None, "is_parked": True}
    assert get_suggested_action(100, facts) == "skip"

@pytest.mark.parametrize("score,expected_action", [
    (25, "investigate"),
    (24, "skip"),
])
def test_action_error_thresholds(score, expected_action):
    facts = {"error": "timeout", "is_parked": False}
    assert get_suggested_action(score, facts) == expected_action


# --- 1-10 display scale -------------------------------------------------

@pytest.mark.parametrize("score,expected_score_1_10", [
    (10, 1),
    (50, 5),
    (95, 10),
    (100, 10),
])
def test_score_1_10_scale_boundaries(score, expected_score_1_10):
    assert to_score_1_10(score) == expected_score_1_10


# Regression: round(score / 10) returned 0 below a score of 5, which is off the
# 1-10 scale the README documents and the summary report prints.
@pytest.mark.parametrize("score", [0, 1, 4, 5, 9])
def test_score_1_10_never_falls_off_the_bottom_of_the_scale(score):
    assert to_score_1_10(score) >= 1


@pytest.mark.parametrize("score", range(101))
def test_score_1_10_always_lands_in_the_documented_range(score):
    assert 1 <= to_score_1_10(score) <= 10


def test_pipeline_uses_the_shared_scale_helper():
    """The formula was inline in main.py, so no test ever exercised it."""
    import main

    assert main.to_score_1_10 is to_score_1_10


# --- individual scoring deltas (the table in README.md) -----------------

@pytest.mark.parametrize("error,expected_delta", [
    ("connection_error", -30),
    ("timeout", -20),
    ("request_error:SomethingElse", -15),
])
def test_error_deltas(error, expected_delta):
    score, _ = calculate_score({"error": error})
    assert score == 50 + expected_delta

@pytest.mark.parametrize("http_status,expected_delta", [
    (200, 20),
    (301, 5),
    (404, -10),
    (500, -15),
])
def test_http_status_deltas(http_status, expected_delta):
    score, _ = calculate_score({"http_status": http_status})
    assert score == 50 + expected_delta

@pytest.mark.parametrize("response_time_ms,expected_delta", [
    (999, 5),
    (5001, -5),
    (2500, 0),
])
def test_response_time_deltas(response_time_ms, expected_delta):
    score, _ = calculate_score({"response_time_ms": response_time_ms})
    assert score == 50 + expected_delta

@pytest.mark.parametrize("html_size,expected_delta", [
    (5001, 5),
    (999, -10),
    (2500, 0),
])
def test_html_size_deltas(html_size, expected_delta):
    score, _ = calculate_score({"html_size": html_size})
    assert score == 50 + expected_delta


# --- clip bounds ---------------------------------------------------------

def test_clip_caps_at_max():
    assert _clip(150) == 100

def test_clip_floors_at_min():
    assert _clip(-50) == 0

def test_clip_passes_through_in_range():
    assert _clip(42) == 42
