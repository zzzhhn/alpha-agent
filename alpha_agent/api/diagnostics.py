"""Keep operational failure details in the service log and expose a reference."""
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


def record_failure(code: str, exc: Exception) -> str:
    reference = uuid4().hex
    logger.error("%s reference=%s", code, reference, exc_info=exc)
    return reference
