from app.llm.cache import DiskCache


def test_cache_miss_returns_none(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    assert cache.get("system", "user", "model") is None


def test_cache_set_then_get_returns_value(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    cache.set("system", "user", "model", "SELECT * WHERE {}")
    result = cache.get("system", "user", "model")
    assert result == "SELECT * WHERE {}"


def test_cache_different_key_returns_none(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    cache.set("system", "user", "model-a", "value-a")
    assert cache.get("system", "user", "model-b") is None


def test_cache_disabled_never_stores(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"), disabled=True)
    cache.set("s", "u", "m", "value")
    assert cache.get("s", "u", "m") is None


def test_cache_creates_directory_automatically(tmp_path):
    cache_dir = tmp_path / "deep" / "nested" / "cache"
    cache = DiskCache(str(cache_dir))
    cache.set("s", "u", "m", "value")
    assert cache_dir.exists()
