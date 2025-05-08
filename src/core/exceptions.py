"""
Custom exception classes for the Personal Research Agent application.
"""

class PersonalResearchAgentError(Exception):
    """Base class for exceptions in this application."""
    def __init__(self, message="An application error occurred", original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception
        self.message = message

    def __str__(self):
        if self.original_exception:
            return f"{self.message}: {type(self.original_exception).__name__} - {str(self.original_exception)}"
        return self.message

# --- Configuration Errors ---
class ConfigError(PersonalResearchAgentError):
    """Exception raised for errors in configuration.
    
    Attributes:
        config_path -- path to the configuration file that caused the error
        message -- explanation of the error
    """
    def __init__(self, message="Configuration error", config_path=None, original_exception=None):
        super().__init__(message, original_exception)
        self.config_path = config_path

    def __str__(self):
        base_str = super().__str__()
        if self.config_path:
            return f"{base_str} (Config Path: {self.config_path})"
        return base_str

# --- Data Acquisition Errors ---
class DataAcquisitionError(PersonalResearchAgentError):
    """Exception raised for errors during data acquisition (e.g., API calls, scraping)."""
    def __init__(self, message="Data acquisition failed", source=None, original_exception=None):
        super().__init__(message, original_exception)
        self.source = source # e.g., API name, website URL

    def __str__(self):
        base_str = super().__str__()
        if self.source:
            return f"{base_str} (Source: {self.source})"
        return base_str

class ApiLimitError(DataAcquisitionError):
    """Raised when an API rate limit is hit."""
    def __init__(self, message="API rate limit exceeded", source=None, original_exception=None):
        super().__init__(message, source, original_exception)

class ApiAuthError(DataAcquisitionError):
    """Raised for API authentication failures."""
    def __init__(self, message="API authentication failed", source=None, original_exception=None):
        super().__init__(message, source, original_exception)

# --- Data Processing Errors ---
class DataProcessingError(PersonalResearchAgentError):
    """Exception raised for errors during data processing or filtering."""
    pass # Can be specialized further if needed

# --- Output Generation Errors ---
class OutputGenerationError(PersonalResearchAgentError):
    """Exception raised for errors during data export or output generation."""
    def __init__(self, message="Output generation failed", output_path=None, original_exception=None):
        super().__init__(message, original_exception)
        self.output_path = output_path

    def __str__(self):
        base_str = super().__str__()
        if self.output_path:
            return f"{base_str} (Output Path: {self.output_path})"
        return base_str

# Example Usage (not to be run directly here, but for illustration)
# if __name__ == '__main__':
#     try:
#         # Simulate an error
#         # raise ConfigError("Missing API key in .env", config_path=".env")
#         # raise DataAcquisitionError("Failed to fetch data from LinkedIn", source="LinkedIn API")
#         # raise ApiLimitError(source="SerpApi")
#         pass
#     except PersonalResearchAgentError as e:
#         print(f"Caught application-specific error: {e}")
#     except Exception as e:
#         print(f"Caught a general error: {e}") 