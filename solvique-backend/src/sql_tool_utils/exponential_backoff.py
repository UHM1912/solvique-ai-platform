import re
import random

NON_RETRYABLE_ERROR_CODES = {400, 401, 403, 404, 422}
RETRYABLE_ERROR_CODES = {408, 429, 500, 502, 503, 504}
DEFAULT_RETRYABLE_ERROR_CODE = 503


class NonRetryableError(Exception):
    """Exception raised for errors returned by the LLM API that does not need a retry request"""

    def __init__(self, error_code, error_message):
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(error_message)

    def __str__(self):
        return f"NonRetryableError: API request status code: {self.error_code}. request status message: {super().__str__()}"


class RetryableError(Exception):
    """Exception raised for errors returned by the LLM API that does need a retry request after some period"""

    def __init__(self, error_code, error_message):
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(error_message)

    def __str__(self):
        return f"RetryableError: API request status code: {self.error_code}. request status message: {super().__str__()}"
        # return f'Rate limit error retry after few minutes.'


def backoff_with_jitter(
    attempt: int, base_delay: float = 1.0, max_delay: float = 60.0
) -> float:
    """
    Full jitter strategy: wait a random amount between 0 and the exponential cap.
    This spreads retries across the time window and prevents thundering herds.
    """
    exponential_cap = min(base_delay * (2**attempt), max_delay)
    return random.uniform(0, exponential_cap)


def extract_error_details(error):
    """Return a status code and message for API and transport-level errors."""
    error_text = str(error)
    response = getattr(error, "response", None)

    error_code = getattr(error, "status_code", None)
    if error_code is None and response is not None:
        error_code = getattr(response, "status_code", None)

    code_match = re.search(r"['\"]code['\"]\s*:\s*(\d{3})", error_text)
    if error_code is None and code_match:
        error_code = int(code_match.group(1))

    message = getattr(error, "message", None)
    message_match = re.search(
        r"['\"]message['\"]\s*:\s*['\"]([^'\"]+)['\"]", error_text
    )
    if message is None and message_match:
        message = message_match.group(1)

    if error_code is None:
        error_code = DEFAULT_RETRYABLE_ERROR_CODE
    if not message:
        message = error_text or error.__class__.__name__

    return int(error_code), message


def handle_error(error, attempt):
    """This function handles errors based on their nature"""
    error_code, error_message = extract_error_details(error)
    if error_code in NON_RETRYABLE_ERROR_CODES or (
        400 <= error_code < 500 and error_code not in RETRYABLE_ERROR_CODES
    ):
        raise NonRetryableError(error_code, error_message)

    if attempt > 2:
        raise RetryableError(error_code, error_message)

    wait = backoff_with_jitter(attempt)
    print(f"{wait =}")
    print(f"wait type = {type(wait)}")
    return wait
