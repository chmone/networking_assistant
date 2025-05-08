import pytest

# Assuming exceptions are importable from src.core.exceptions
# Add path adjustment if necessary, similar to test_config_manager.py
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.exceptions import (
    PersonalResearchAgentError,
    ConfigError,
    DataAcquisitionError,
    ApiLimitError,
    ApiAuthError,
    DataProcessingError,
    OutputGenerationError
)

# --- Test Raising and Catching --- 

def test_raise_base_exception():
    """Test raising and catching the base exception."""
    with pytest.raises(PersonalResearchAgentError):
        raise PersonalResearchAgentError("Base error message")

def test_raise_config_error():
    """Test raising and catching ConfigError."""
    with pytest.raises(ConfigError):
        raise ConfigError("Config issue", config_path=".env")

def test_raise_data_acquisition_error():
    """Test raising and catching DataAcquisitionError."""
    with pytest.raises(DataAcquisitionError):
        raise DataAcquisitionError("Acquisition failed", source="API X")

def test_raise_api_limit_error():
    """Test raising and catching ApiLimitError."""
    with pytest.raises(ApiLimitError):
        raise ApiLimitError("Limit hit", source="API Y")

def test_raise_api_auth_error():
    """Test raising and catching ApiAuthError."""
    with pytest.raises(ApiAuthError):
        raise ApiAuthError("Auth failed", source="API Z")

def test_raise_data_processing_error():
    """Test raising and catching DataProcessingError."""
    with pytest.raises(DataProcessingError):
        raise DataProcessingError("Processing failed")

def test_raise_output_generation_error():
    """Test raising and catching OutputGenerationError."""
    with pytest.raises(OutputGenerationError):
        raise OutputGenerationError("Output failed", output_path="out.txt")

# --- Test Inheritance --- 

def test_inheritance_data_acquisition():
    """Test that specific data acquisition errors are caught by the base data acquisition error."""
    with pytest.raises(DataAcquisitionError):
        raise ApiLimitError()
    with pytest.raises(DataAcquisitionError):
        raise ApiAuthError()

def test_inheritance_base_error():
    """Test that all specific errors are caught by the base PersonalResearchAgentError."""
    exceptions_to_test = [
        ConfigError,
        DataAcquisitionError,
        ApiLimitError,
        ApiAuthError,
        DataProcessingError,
        OutputGenerationError
    ]
    for exc_type in exceptions_to_test:
        with pytest.raises(PersonalResearchAgentError):
            raise exc_type(f"Testing {exc_type.__name__}")

# --- Test Attributes --- 

def test_config_error_attributes():
    """Test attributes of ConfigError."""
    original_exc = ValueError("Original issue")
    exc = ConfigError("Config msg", config_path="path/conf", original_exception=original_exc)
    assert exc.message == "Config msg"
    assert exc.config_path == "path/conf"
    assert exc.original_exception is original_exc

def test_data_acquisition_error_attributes():
    """Test attributes of DataAcquisitionError."""
    original_exc = ConnectionError("Network down")
    exc = DataAcquisitionError("Data acq msg", source="TestSource", original_exception=original_exc)
    assert exc.message == "Data acq msg"
    assert exc.source == "TestSource"
    assert exc.original_exception is original_exc

def test_output_generation_error_attributes():
    """Test attributes of OutputGenerationError."""
    original_exc = IOError("Disk full")
    exc = OutputGenerationError("Output msg", output_path="file.out", original_exception=original_exc)
    assert exc.message == "Output msg"
    assert exc.output_path == "file.out"
    assert exc.original_exception is original_exc

# --- Test __str__ Formatting --- 

def test_str_base_exception():
    exc = PersonalResearchAgentError("Base message")
    assert str(exc) == "Base message"

    original_exc = TypeError("Bad type")
    exc_with_orig = PersonalResearchAgentError("Base wrapped", original_exception=original_exc)
    assert str(exc_with_orig) == "Base wrapped: TypeError - Bad type"

def test_str_config_error():
    exc = ConfigError("Config issue")
    assert str(exc) == "Config issue"

    exc_with_path = ConfigError("Config issue", config_path="file.cfg")
    assert str(exc_with_path) == "Config issue (Config Path: file.cfg)"

    original_exc = KeyError("missing key")
    exc_with_all = ConfigError("Config wrap", config_path="conf.ini", original_exception=original_exc)
    expected_str = "Config wrap: KeyError - 'missing key' (Config Path: conf.ini)"
    assert str(exc_with_all) == expected_str

def test_str_data_acquisition_error():
    exc = DataAcquisitionError("Data issue")
    assert str(exc) == "Data issue"

    exc_with_source = DataAcquisitionError("Data issue", source="SourceABC")
    assert str(exc_with_source) == "Data issue (Source: SourceABC)"

    original_exc = TimeoutError("timed out")
    exc_with_all = DataAcquisitionError("Data wrap", source="SourceXYZ", original_exception=original_exc)
    expected_str = "Data wrap: TimeoutError - timed out (Source: SourceXYZ)"
    assert str(exc_with_all) == expected_str

def test_str_output_generation_error():
    exc = OutputGenerationError("Output issue")
    assert str(exc) == "Output issue"

    exc_with_path = OutputGenerationError("Output issue", output_path="out.csv")
    assert str(exc_with_path) == "Output issue (Output Path: out.csv)"

    original_exc = PermissionError("no write")
    exc_with_all = OutputGenerationError("Output wrap", output_path="data.json", original_exception=original_exc)
    expected_str = "Output wrap: PermissionError - no write (Output Path: data.json)"
    assert str(exc_with_all) == expected_str 