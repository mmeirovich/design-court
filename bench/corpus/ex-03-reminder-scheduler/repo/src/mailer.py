"""Outbound email for the application."""
import logging

from .providers import ProviderError, client

log = logging.getLogger(__name__)


def send_template(user_id: int, template: str, context: dict) -> bool:
    """Render `template` for the user and hand it to the provider.

    Returns True if the provider accepted the message.
    """
    try:
        client.send(
            to=_address_for(user_id),
            template=template,
            context=context,
            timeout=2.0,
        )
    except ProviderError as exc:
        log.warning("send failed user=%s template=%s: %s", user_id, template, exc)
        return False
    return True


def _address_for(user_id: int) -> str:
    ...
