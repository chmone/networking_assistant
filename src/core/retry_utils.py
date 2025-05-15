import time
import random
import logging
import requests # For specific exceptions
import functools # Add this import

# It's good practice for utils to have their own logger or use a common one
logger = logging.getLogger(__name__)

# Import custom exceptions if they are to be specifically caught and handled by retry
from .exceptions import ApiLimitError, DataAcquisitionError, ApiAuthError # Keep ApiAuthError import for the check

def retry_with_backoff(retries=3, initial_delay=1, backoff_factor=2, jitter=True, 
                       retry_on_exceptions=(requests.exceptions.ConnectionError, 
                                            requests.exceptions.Timeout,
                                            ApiLimitError, # Only retry on these specific exceptions by default
                                            DataAcquisitionError # REMOVED ApiAuthError from this default tuple
                                            ),
                       retry_on_status_codes=(429, 500, 502, 503, 504)):
    """
    A decorator to retry a function with exponential backoff and jitter.

    :param retries: Maximum number of retries.
    :param initial_delay: Initial delay in seconds.
    :param backoff_factor: Multiplier for the delay in each retry (e.g., 2 for doubling).
    :param jitter: If True, add a random small amount to the delay to prevent thundering herd.
    :param retry_on_exceptions: A tuple of exception types that should trigger a retry.
    :param retry_on_status_codes: A tuple of HTTP status codes that should trigger a retry 
                                   (if the decorated function returns a response object with a status_code).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_retries = 0
            delay = initial_delay
            last_exception = None
            
            while current_retries <= retries:
                try:
                    result = func(*args, **kwargs)
                    
                    # If result has a status_code, check it against retry_on_status_codes
                    if hasattr(result, 'status_code') and result.status_code in retry_on_status_codes:
                        logger.warning(
                            f"Retry {current_retries + 1}/{retries}: Function {func.__name__} returned status {result.status_code}. Retrying..."
                        )
                        # Store this as the "exception" that caused the retry for logging purposes if all retries fail
                        last_exception = requests.exceptions.HTTPError(f"Function returned status code {result.status_code}", response=result)
                        # Fall through to retry logic
                    else:
                        return result # Success
                        
                except retry_on_exceptions as e:
                    # ADDED CHECK: Immediately raise ApiAuthError if caught, don't retry it.
                    # This handles cases where ApiAuthError inherits from a listed exception (DataAcquisitionError)
                    if type(e) is ApiAuthError:
                        logger.warning(f"Function {func.__name__} raised ApiAuthError. Not retrying authentication errors.")
                        raise e
                    
                    # Original retry logic for other exceptions in the tuple
                    logger.warning(
                        f"Retry {current_retries + 1}/{retries}: Function {func.__name__} raised {type(e).__name__}: {e}. Retrying..."
                    )
                    last_exception = e
                    # Fall through to retry logic
                except Exception as e:
                    # If an unexpected exception occurs that is not in retry_on_exceptions,
                    # re-raise it immediately without retrying.
                    logger.error(f"Function {func.__name__} raised an unexpected error: {e}")
                    raise

                # If we are here, it means a retry is needed (either due to status code or caught exception)
                if current_retries < retries:
                    current_retries += 1
                    
                    actual_delay = delay
                    if jitter:
                        actual_delay += random.uniform(0, delay * 0.1) # Add up to 10% jitter
                    
                    logger.info(f"Waiting {actual_delay:.2f} seconds before next retry for {func.__name__}.")
                    time.sleep(actual_delay)
                    delay *= backoff_factor
                else:
                    # Max retries reached
                    logger.error(f"Max retries ({retries}) reached for function {func.__name__}.")
                    if last_exception:
                        # Re-raise the last exception that caused a retry attempt
                        raise last_exception 
                    else:
                        # Should not happen if a retry was triggered, but as a fallback
                        raise RuntimeError(f"Max retries reached for {func.__name__} without a specific exception to re-raise.")
            
            # This part should ideally not be reached if logic is correct
            # (either success, or an exception is raised after max retries)
            return None 

        return wrapper
    return decorator

# --- Example Usage (for testing the decorator itself) ---
# This would typically be in a test file or a different module.
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # --- Test with exception --- 
    RETRY_ATTEMPTS_EXCEPTION = 0
    @retry_with_backoff(retries=3, initial_delay=0.1, retry_on_exceptions=(ValueError,))
    def might_fail_with_exception():
        global RETRY_ATTEMPTS_EXCEPTION
        RETRY_ATTEMPTS_EXCEPTION += 1
        print(f"Attempting might_fail_with_exception (attempt #{RETRY_ATTEMPTS_EXCEPTION})...")
        if RETRY_ATTEMPTS_EXCEPTION < 3:
            raise ValueError("Simulated transient error")
        print("might_fail_with_exception succeeded!")
        return "Success after exceptions!"

    print("\n--- Testing retry on exception ---")
    try:
        result = might_fail_with_exception()
        print(f"Result: {result}")
    except ValueError as e:
        print(f"Caught expected ValueError after retries: {e}")
    except Exception as e:
        print(f"Caught unexpected error: {e}")
    print(f"Total attempts made for might_fail_with_exception: {RETRY_ATTEMPTS_EXCEPTION}")
    assert RETRY_ATTEMPTS_EXCEPTION == 3

    # --- Test with status code --- 
    RETRY_ATTEMPTS_STATUS = 0
    class MockResponse:
        def __init__(self, status_code, content=""):
            self.status_code = status_code
            self.content = content
            self.text = str(content)
        def json(self):
            import json
            return json.loads(self.content) if self.content else {}

    @retry_with_backoff(retries=2, initial_delay=0.1, retry_on_status_codes=(503, 429))
    def might_return_bad_status():
        global RETRY_ATTEMPTS_STATUS
        RETRY_ATTEMPTS_STATUS += 1
        print(f"Attempting might_return_bad_status (attempt #{RETRY_ATTEMPTS_STATUS})...")
        if RETRY_ATTEMPTS_STATUS == 1:
            return MockResponse(503, "Service Unavailable")
        elif RETRY_ATTEMPTS_STATUS == 2:
            return MockResponse(429, "Rate Limited")
        print("might_return_bad_status succeeded with 200!")
        return MockResponse(200, '{"data": "success"}')

    print("\n--- Testing retry on status code ---")
    try:
        response = might_return_bad_status()
        print(f"Response status: {response.status_code}, content: {response.json()}")
        assert response.status_code == 200
    except requests.exceptions.HTTPError as e:
        print(f"Caught expected HTTPError after retries: {e} (response status: {e.response.status_code if e.response else 'N/A'})")
    except Exception as e:
        print(f"Caught unexpected error: {e}")
    print(f"Total attempts made for might_return_bad_status: {RETRY_ATTEMPTS_STATUS}")
    assert RETRY_ATTEMPTS_STATUS == 3 # 1 initial + 2 retries

    # --- Test max retries failure ---
    RETRY_ATTEMPTS_FAILURE = 0
    @retry_with_backoff(retries=1, initial_delay=0.1, retry_on_exceptions=(IOError,))
    def will_always_fail():
        global RETRY_ATTEMPTS_FAILURE
        RETRY_ATTEMPTS_FAILURE += 1
        print(f"Attempting will_always_fail (attempt #{RETRY_ATTEMPTS_FAILURE})...")
        raise IOError("Persistent I/O Failure")

    print("\n--- Testing max retries failure ---")
    try:
        will_always_fail()
    except IOError as e:
        print(f"Caught expected IOError after max retries: {e}")
    except Exception as e:
        print(f"Caught unexpected error: {e}")
    print(f"Total attempts made for will_always_fail: {RETRY_ATTEMPTS_FAILURE}")
    assert RETRY_ATTEMPTS_FAILURE == 2 # 1 initial + 1 retry
    print("\nRetry decorator tests completed.") 