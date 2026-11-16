"""Shared Redis cluster client for the API services."""
import os

from redis.cluster import RedisCluster

_client = RedisCluster.from_url(
    os.environ["REDIS_URL"],
    socket_timeout=0.05,
    socket_connect_timeout=0.2,
)

_INCR_TTL = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return n
"""


def client() -> RedisCluster:
    return _client


def incr_with_ttl(key: str, ttl_s: int) -> int:
    """Increment `key` and return the new value; the TTL (seconds) is set on first increment."""
    return int(_client.eval(_INCR_TTL, 1, key, ttl_s))


def load_script(source: str) -> str:
    """Register a Lua script on every primary and return its SHA."""
    return _client.script_load(source)


def run_script(sha: str, keys: list[str], args: list) -> list:
    """Run a registered script via EVALSHA."""
    return _client.evalsha(sha, len(keys), *keys, *args)
