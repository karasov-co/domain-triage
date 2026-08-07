import pytest

import cache


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DB_PATH", str(tmp_path / "test_cache.db"))
    cache.init_db()


def test_cache_miss_new_domain_is_pending():
    cache.add_domains(["example.com"])
    assert cache.get_pending() == ["example.com"]

def test_cache_hit_done_domain_is_not_reprocessed():
    cache.add_domains(["example.com"])
    cache.save_result("example.com", {"score": 90})
    assert cache.get_pending() == []

    # re-adding the same domain (e.g. re-running with the same seeds.csv)
    # must not reset it back to pending: INSERT OR IGNORE is the cache hit.
    cache.add_domains(["example.com"])
    assert cache.get_pending() == []
    assert cache.stats() == {"done": 1}

def test_cache_hit_preserves_existing_result():
    cache.add_domains(["example.com"])
    cache.save_result("example.com", {"score": 90, "bucket": "high"})
    cache.add_domains(["example.com"])

    [result] = cache.get_all_results()
    assert result["status"] == "done"
    assert result["score"] == 90
    assert result["bucket"] == "high"

def test_rerun_failed_moves_failed_back_to_pending():
    cache.add_domains(["broken.com", "ok.com"])
    cache.save_failure("broken.com", "connection_error")
    cache.save_result("ok.com", {"score": 80})

    assert cache.get_pending() == []
    assert cache.stats() == {"done": 1, "failed": 1}

    cache.reset_failed()

    assert cache.get_pending() == ["broken.com"]
    assert cache.stats() == {"done": 1, "pending": 1}

def test_rerun_failed_does_not_touch_done_domains():
    cache.add_domains(["ok.com"])
    cache.save_result("ok.com", {"score": 80})

    cache.reset_failed()

    assert cache.get_pending() == []
    assert cache.stats() == {"done": 1}

def test_rerun_failed_clears_error_field():
    cache.add_domains(["broken.com"])
    cache.save_failure("broken.com", "timeout")
    cache.reset_failed()

    [result] = cache.get_all_results()
    assert result["status"] == "pending"
    assert result["error"] is None
