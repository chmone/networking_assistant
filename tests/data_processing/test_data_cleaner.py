# Initial test file for data_cleaner.py

import pytest
from src.data_processing.data_cleaner import (
    normalize_whitespace,
    normalize_company_name,
    normalize_location,
    clean_lead_data,
    clean_company_data,
    clean_job_posting_data
)

# Tests for normalize_whitespace
@pytest.mark.parametrize("input_text, expected_output", [
    ("  hello world  ", "hello world"),
    ("hello   world", "hello world"),
    ("helloworld", "helloworld"),
    ("  ", ""),
    ("", ""),
    (None, None),
    (" leading", "leading"),
    ("trailing ", "trailing"),
    ("many    spaces    between", "many spaces between"),
])
def test_normalize_whitespace(input_text, expected_output):
    assert normalize_whitespace(input_text) == expected_output

# Tests for normalize_company_name
@pytest.mark.parametrize("input_name, expected_output", [
    ("Example Corp.", "Example"),
    ("Example Corp", "Example"),
    ("Test, Inc.", "Test"),
    ("Test, Inc", "Test"),
    ("ACME LLC", "ACME"),
    ("ACME llc", "ACME"), # Case-insensitivity for suffix
    ("Global Limited", "Global"),
    ("  Whitespace Corp  ", "Whitespace"),
    ("No Suffix Co", "No Suffix Co"),
    ("My Company Inc", "My Company"),
    ("My Company, Inc.", "My Company"),
    ("My Company, Incorporated", "My Company"),
    ("A.B.C. Corp", "A.B.C"),
    ("The Best Company Ltd.", "The Best Company"),
    ("  Multi  Space   LLC  ", "Multi Space"),
    ("Company with trailing comma,", "Company with trailing comma"),
    ("Company with trailing period.", "Company with trailing period"),
    ("International Corp", "International"),
    ("Future Ltd", "Future"),
    ("Innovate Inc.", "Innovate"),
    ("Solutions LLC.", "Solutions"),
    ("Global Services Limited", "Global Services"),
    ("  Alpha Beta Corp.  ", "Alpha Beta"),
    (None, None),
    ("", None), # Empty string input
    ("  ", None), # Whitespace only input should be None after strip
    # Cases where removing suffix results in empty string, should return original cleaned name
    ("Inc.", "Inc."), 
    ("  LLC  ", "LLC"),
    ("Corp.", "Corp."),
    ("LLC", "LLC"), 
    ("Corp", "Corp"),
    ("Example LTD", "Example"),
    ("Example, LTD", "Example"),
])
def test_normalize_company_name(input_name, expected_output):
    assert normalize_company_name(input_name) == expected_output

# Test case where removing suffix results in empty string, should return original cleaned name
# @pytest.mark.parametrize("input_name, expected_output", [
#     ("Inc.", "Inc."), # Should return original cleaned if suffix only makes it empty
#     ("  LLC  ", "LLC"),
#     ("Corp.", "Corp."),
# ])
# def test_normalize_company_name_suffix_only_returns_cleaned_original(input_name, expected_output):
#     # This behavior is a bit nuanced: if ONLY a suffix (after initial strip) is provided,
#     # and removing it makes the string empty, the current code returns the *original, whitespace-normalized* string.
#     # The main parametrize test has `("Inc.", "")` which is what one might expect if it truly removes.
#     # Let's adjust the main test for "Inc." etc. to reflect this specific logic.
#     # The function logic: `if not normalized: return normalize_whitespace(name)`
#     assert normalize_company_name(input_name) == expected_output

# TODO: Add test cases for other functions

# Tests for normalize_location
@pytest.mark.parametrize("input_location, expected_output", [
    ("  New York, NY  ", "New York, NY"),
    ("San Francisco, CA", "San Francisco, CA"),
    (" London, UK", "London, UK"),
    (None, None),
    ("", None), # Empty string input handled by normalize_whitespace inside, but func has `if not location: return None`
    ("  ", ""),   # Whitespace only input
    ("Paris", "Paris"),
    ("Berlin   Germany", "Berlin Germany"),
])
def test_normalize_location(input_location, expected_output):
    assert normalize_location(input_location) == expected_output

# Tests for clean_lead_data
@pytest.mark.parametrize("input_data, expected_output", [
    (
        {"name": "  John Doe  ", "email": " JOHN.DOE@example.com  ", "phone": "123-456-7890  ", "source": "  Web  ", "notes": "  Important lead.  ", "company_name": "Example, Inc. ", "location": " new york city, ny"},
        {"name": "John Doe", "email": "john.doe@example.com", "phone": "123-456-7890", "source": "Web", "notes": "Important lead.", "company_name": "Example, Inc. ", "normalized_company_name": "Example", "location": " new york city, ny", "normalized_location": "new york city, ny"}
    ),
    (
        {"name": "Jane Smith", "email": " JANE@EXAMPLE.COM "},
        {"name": "Jane Smith", "email": "jane@example.com", "phone": None, "source": None, "notes": None} # Assuming missing keys are fine, get defaults to None or ''
    ),
    (
        {"name": None, "email": "", "company_name": "  LLC  "},
        {"name": None, "email": "", "phone": None, "source": None, "notes": None, "company_name": "  LLC  ", "normalized_company_name": "LLC"}
    ),
    (
        {},
        {"name": None, "email": "", "phone": None, "source": None, "notes": None} # Empty input
    ),
    (
        {"name": "Test", "email": "test@test.com", "company_name": "Test Corp", "location": "Test Loc"},
        {"name": "Test", "email": "test@test.com", "phone": None, "source": None, "notes": None, "company_name": "Test Corp", "normalized_company_name": "Test", "location": "Test Loc", "normalized_location": "Test Loc"}
    ),
])
def test_clean_lead_data(input_data, expected_output):
    cleaned = clean_lead_data(input_data)
    # Ensure all expected keys are present, even if None
    for key in expected_output:
        assert key in cleaned
        assert cleaned[key] == expected_output[key]
    # Ensure no unexpected keys were added if not in expected_output
    for key in cleaned:
        assert key in expected_output

# Tests for clean_company_data
@pytest.mark.parametrize("input_data, expected_output", [
    (
        {"name": "  Mega Corp Ltd.  ", "website": "  http://megacorp.com ", "industry": " Tech  ", "size": " 1000+ ", "location": "  SF, CA ", "description": "   A big company.   "},
        {"name": "Mega Corp", "website": "http://megacorp.com", "industry": "Tech", "size": "1000+", "location": "SF, CA", "description": "A big company."}
    ),
    (
        {"name": "Small Biz LLC", "website": None, "description": "A small business."},
        {"name": "Small Biz", "website": None, "industry": None, "size": None, "location": None, "description": "A small business."}
    ),
    (
        {},
        {"name": None, "website": None, "industry": None, "size": None, "location": None, "description": None} # Empty input
    ),
    (
        {"name": "  Solo Inc.  ", "location": " remote  "},
        {"name": "Solo", "website": None, "industry": None, "size": None, "location": "remote", "description": None}
    ),
])
def test_clean_company_data(input_data, expected_output):
    cleaned = clean_company_data(input_data)
    for key in expected_output:
        assert key in cleaned
        assert cleaned[key] == expected_output[key]
    for key in cleaned:
        assert key in expected_output

# Tests for clean_job_posting_data
@pytest.mark.parametrize("input_data, expected_output", [
    (
        {"job_title": "  Software Engineer  ", "company_name": "  Tech Solutions Inc.  ", "job_location": "  Remote  ", "job_url": " http://apply.com/123 ", "job_description_snippet": "  Develop cool stuff.  ", "source_api": "  LinkedIn  ", "commitment": " Full-time  "},
        {"job_title": "Software Engineer", "company_name": "Tech Solutions", "job_location": "Remote", "job_url": "http://apply.com/123", "job_description_snippet": "Develop cool stuff.", "source_api": "LinkedIn", "commitment": "Full-time"}
    ),
    (
        {"job_title": "Analyst", "company_name": "Data Corp"},
        {"job_title": "Analyst", "company_name": "Data", "job_location": None, "job_url": None, "job_description_snippet": None, "source_api": None, "commitment": None}
    ),
    (
        {},
        {"job_title": None, "company_name": None, "job_location": None, "job_url": None, "job_description_snippet": None, "source_api": None, "commitment": None} # Empty input
    ),
    (
        {"job_title": "  Intern  ", "company_name": "Just LLC", "job_location": None, "commitment": " Part-time"},
        {"job_title": "Intern", "company_name": "Just", "job_location": None, "job_url": None, "job_description_snippet": None, "source_api": None, "commitment": "Part-time"}
    ),
])
def test_clean_job_posting_data(input_data, expected_output):
    cleaned = clean_job_posting_data(input_data)
    for key in expected_output:
        assert key in cleaned
        assert cleaned[key] == expected_output[key]
    for key in cleaned:
        assert key in expected_output 