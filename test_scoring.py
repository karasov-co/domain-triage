from scoring import calculate_score, get_priority_bucket, get_suggested_action


def test_case(name, facts):
    score, reason = calculate_score(facts)
    print(f"\n=== {name} ===")
    print(f"Score: {score}")
    print(f"Reason: {reason}")
    print(f"Bucket: {get_priority_bucket(score)}")
    print(f"Action: {get_suggested_action(score, facts)}")


test_case("Perfect site", {
    "http_status": 200,
    "response_time_ms": 300,
    "html_size": 50000,
    "title": "Acme Corp",
    "is_parked": False,
    "spammy_tld": False,
    "tld": "com",
    "error": None,
})

test_case("Parked .xyz", {
    "http_status": 200,
    "response_time_ms": 200,
    "html_size": 2000,
    "title": "Domain for sale",
    "is_parked": True,
    "spammy_tld": True,
    "tld": "xyz",
    "error": None,
})

test_case("Dead domain", {
    "http_status": None,
    "response_time_ms": None,
    "html_size": None,
    "title": None,
    "is_parked": False,
    "spammy_tld": True,
    "tld": "xyz",
    "error": "connection_error",
})

test_case("Empty facts", {})