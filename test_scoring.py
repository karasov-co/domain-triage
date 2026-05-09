from scoring import calculate_score, get_priority_bucket, get_suggested_action

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