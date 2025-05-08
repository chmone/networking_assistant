import pytest
import time
import random
import requests # For exceptions
from unittest.mock import MagicMock, call

# Assuming retry_utils is importable from src.core.retry_utils
# Add path adjustment if necessary
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.retry_utils import retry_with_backoff
from src.core.exceptions import ApiLimitError # Example custom exception

# --- Mock Response Class (similar to example) --- 
class MockResponse:
    def __init__(self, status_code, content=""):
        self.status_code = status_code
        self.content = content
        self.text = str(content)
    def json(self):
        import json
        return json.loads(self.content) if self.content else {}

# --- Test Cases --- 

def test_retry_success_on_first_try(mocker):
    """Test that the function returns immediately if it succeeds on the first try."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock(return_value="Success")
    
    @retry_with_backoff(retries=3, initial_delay=0.1)
    def decorated_func():
        return mock_func()
        
    result = decorated_func()
    
    assert result == "Success"
    mock_func.assert_called_once()
    mock_sleep.assert_not_called() # No retry means no sleep

def test_retry_on_exception_success(mocker):
    """Test retry succeeds after initial failures raising specified exceptions."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    mock_func.side_effect = [
        ValueError("Temporary Error 1"), 
        TypeError("Temporary Error 2"), 
        "Success"
    ]
    
    @retry_with_backoff(retries=3, initial_delay=0.1, retry_on_exceptions=(ValueError, TypeError))
    def decorated_func():
        return mock_func()
        
    result = decorated_func()
    
    assert result == "Success"
    assert mock_func.call_count == 3
    # Check that sleep was called twice (after first and second failures)
    assert mock_sleep.call_count == 2
    # Check backoff (optional, requires checking sleep arguments)
    # print(mock_sleep.call_args_list)

def test_retry_on_status_code_success(mocker):
    """Test retry succeeds after initial failures returning specified status codes."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    mock_func.side_effect = [
        MockResponse(503, "Server Busy"),
        MockResponse(429, "Rate Limited"),
        MockResponse(200, '{"data": "Success"}')
    ]
    
    @retry_with_backoff(retries=3, initial_delay=0.1, retry_on_status_codes=(503, 429))
    def decorated_func():
        return mock_func()
        
    result = decorated_func()
    
    assert result.status_code == 200
    assert result.json() == {"data": "Success"}
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2

def test_retry_max_retries_exception(mocker):
    """Test that the last exception is raised after max retries are exhausted."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    # Exception expected from the *last* call before max retries were exceeded
    expected_exception_from_last_call = ValueError("Attempt 2") 
    mock_func.side_effect = [
        ValueError("Attempt 1"), 
        expected_exception_from_last_call, 
        ValueError("Persistent Error") # This won't be reached
    ]
    
    # retries=1 means 1 initial call + 1 retry = 2 total calls
    @retry_with_backoff(retries=1, initial_delay=0.1, retry_on_exceptions=(ValueError,))
    def decorated_func():
        return mock_func()
        
    with pytest.raises(ValueError) as excinfo:
        decorated_func()
        
    # Check the type and message of the caught exception
    assert isinstance(excinfo.value, ValueError)
    assert str(excinfo.value) == "Attempt 2" 
    assert mock_func.call_count == 2 # Initial call + 1 retry
    assert mock_sleep.call_count == 1 # Sleep called after first failure

def test_retry_max_retries_status_code(mocker):
    """Test that an HTTPError is raised after max retries if status code always triggers retry."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    # Function always returns a status code that triggers retry
    mock_func.side_effect = [
        MockResponse(503, "Busy 1"),
        MockResponse(503, "Busy 2"),
        MockResponse(503, "Busy 3") 
    ]
    
    # retries=2 means 1 initial call + 2 retries = 3 total calls
    @retry_with_backoff(retries=2, initial_delay=0.1, retry_on_status_codes=(503,))
    def decorated_func():
        return mock_func()
        
    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        decorated_func()
        
    # Check that the exception has the last response attached (optional but good)
    assert excinfo.value.response is not None
    assert excinfo.value.response.status_code == 503
    assert excinfo.value.response.text == "Busy 3"
    
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2 

def test_no_retry_on_unexpected_exception(mocker):
    """Test that an exception NOT in retry_on_exceptions is raised immediately."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    unexpected_exception = TypeError("Unexpected type error")
    mock_func.side_effect = unexpected_exception
    
    @retry_with_backoff(retries=3, initial_delay=0.1, retry_on_exceptions=(ValueError,)) # Only retry on ValueError
    def decorated_func():
        return mock_func()
        
    with pytest.raises(TypeError) as excinfo:
        decorated_func()
        
    assert excinfo.value is unexpected_exception
    mock_func.assert_called_once() # Called only once
    mock_sleep.assert_not_called() # No retry, no sleep

def test_no_retry_on_success_status_code(mocker):
    """Test that a status code NOT in retry_on_status_codes returns immediately."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    success_response = MockResponse(201, "Created") # 201 is not in retry list
    mock_func.return_value = success_response
    
    @retry_with_backoff(retries=3, initial_delay=0.1, retry_on_status_codes=(500, 503))
    def decorated_func():
        return mock_func()
        
    result = decorated_func()
        
    assert result is success_response
    mock_func.assert_called_once()
    mock_sleep.assert_not_called()

def test_jitter_applied(mocker):
    """Test that jitter adds a small random amount to the delay."""
    mock_time_sleep = mocker.patch('time.sleep')
    mock_random_uniform = mocker.patch('random.uniform', return_value=0.05) # Mock jitter to be fixed 0.05
    mock_func = MagicMock()
    mock_func.side_effect = [ValueError("Fail once"), "Success"]
    
    initial_delay = 0.1
    @retry_with_backoff(retries=1, initial_delay=initial_delay, jitter=True, retry_on_exceptions=(ValueError,))
    def decorated_func():
        return mock_func()
        
    decorated_func()
    
    mock_func.call_count == 2
    mock_time_sleep.assert_called_once() # Called once after the first failure
    # Check that the sleep duration includes the jitter
    expected_delay = initial_delay + 0.05 # delay + mocked jitter
    # pytest approx allows for floating point comparisons
    assert mock_time_sleep.call_args[0][0] == pytest.approx(expected_delay) 
    # Check that random.uniform was called with expected range (0 to delay*0.1)
    mock_random_uniform.assert_called_once_with(0, initial_delay * 0.1)

def test_backoff_factor(mocker):
    """Test that the delay increases by the backoff_factor."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    mock_func.side_effect = [ValueError("Fail 1"), ValueError("Fail 2"), "Success"]
    
    initial_delay = 0.1
    backoff_factor = 3
    @retry_with_backoff(retries=2, initial_delay=initial_delay, backoff_factor=backoff_factor, jitter=False, retry_on_exceptions=(ValueError,))
    def decorated_func():
        return mock_func()
        
    decorated_func()
    
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2
    # Check sleep durations
    assert mock_sleep.call_args_list == [
        call(pytest.approx(initial_delay)),                      # First delay
        call(pytest.approx(initial_delay * backoff_factor))     # Second delay
    ]

def test_retry_with_custom_exception(mocker):
    """Test retry works with custom exceptions listed in retry_on_exceptions."""
    mock_sleep = mocker.patch('time.sleep')
    mock_func = MagicMock()
    mock_func.side_effect = [ApiLimitError("Custom limit error"), "Success"]

    @retry_with_backoff(retries=1, initial_delay=0.1, retry_on_exceptions=(ApiLimitError,))
    def decorated_func():
        return mock_func()

    result = decorated_func()
    assert result == "Success"
    assert mock_func.call_count == 2
    assert mock_sleep.call_count == 1 