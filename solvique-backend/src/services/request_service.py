import uuid

from src.logging_config import get_logger
from src.logging_config.logger import set_request_id

logger = get_logger(__name__)


def start_request(message: str) -> str:
    request_id = str(uuid.uuid4())[:8]
    set_request_id(request_id)
    logger.info(message)
    return request_id
