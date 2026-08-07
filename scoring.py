def _clip (value, min_value=0, max_value=100):   
    return max(min_value, min(max_value, value))

def calculate_score(facts):
    score = 50
    reasons = ["+50 base"]

    error = facts.get("error")
    if error:
        if "connection" in error.lower():
            score -= 30
            reasons.append("-30 connection error")
        elif "timeout" in error.lower():
            score -= 20
            reasons.append("-20 timeout error")
        else:
            score -= 15
            reasons.append("-15 other error")

    http_status = facts.get("http_status")
    if http_status == 200:
        score += 20
        reasons.append("+20 HTTP 200 OK")
    elif http_status and 300 <= http_status < 400:
        score += 5
        reasons.append("+5 HTTP 3xx")
    elif http_status and 400 <= http_status < 500:
        score -= 10
        reasons.append("-10 HTTP 4xx")
    elif http_status and http_status >= 500:
        score -= 15
        reasons.append("-15 HTTP 5xx")

    response_time = facts.get("response_time_ms")
    if response_time is not None:
        if response_time < 1000:
            score += 5
            reasons.append("+5 fast response")
        elif response_time > 5000:
            score -= 5
            reasons.append("-5 slow response")

    if facts.get("title"):
        score += 10
        reasons.append("+10 title present")
    
    html_size = facts.get("html_size")
    if html_size is not None:
        if html_size > 5000:
            score +=5
            reasons.append("+5 normal HTML size")
        elif 0 < html_size < 1000:
            score -= 10
            reasons.append("-10 tiny HTML")

    if facts.get("is_parked"):
            score -= 25
            reasons.append("-25 parked domain")

    if facts.get("spammy_tld"):
        score -= 15
        reasons.append(f"-15 spammy TLD (.{facts.get('tld', '')})")

    score = _clip(score)
    reason = ", ".join(reasons)
    return score, reason

def to_score_1_10(score):
    """Map the 0-100 score onto the 1-10 display scale.

    round(score / 10) alone returns 0 for anything under 5, which is off the
    scale the README documents and the reports print. The floor keeps the two
    consistent -- a domain that scored at all is at least a 1.
    """
    return _clip(round(score / 10), 1, 10)


def get_priority_bucket(score):
    if score >= 75:
        return "high"
    elif score >= 50:
        return "medium"
    elif score >= 25:
        return "low"
    else:
        return "skip"
    
def get_suggested_action(score, facts):
    if facts.get("error"):
        return "investigate" if score >= 25 else "skip"
    if facts.get("is_parked"):
        return "skip"
    if score >= 75:
        return "review_for_outreach"
    elif score >= 50:
        return "manual_review"
    elif score >= 25:
        return "deprioritize"
    else:
        return "skip"