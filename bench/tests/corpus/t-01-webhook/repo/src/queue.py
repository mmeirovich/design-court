"""Tiny job queue wrapper used across the service."""


def publish(topic: str, payload: dict, delay_s: int = 0) -> None:
    """Publish a job to a topic; consumers are registered with @subscribe(topic)."""
    ...
