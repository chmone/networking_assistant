import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Common company suffixes to remove for normalization
COMPANY_SUFFIXES = [
    r',?\s+inc\.?,?$', 
    r',?\s+llc\.?,?$', 
    r',?\s+ltd\.?,?$', 
    r',?\s+corp\.?,?$', 
    r',?\s+corporation,?$', 
    r',?\s+limited,?$',
    r',?\s+incorporated,?$'
]
# Compile regex for efficiency
COMPANY_SUFFIX_REGEX = re.compile(r'(?i)(\b(?:{}))'.format('|'.join(suffix.replace(r',?\s+', '').replace(r'\.?,?$', '') for suffix in COMPANY_SUFFIXES)), re.IGNORECASE)
COMPANY_SUFFIX_REMOVE_REGEX = re.compile(r'|'.join(COMPANY_SUFFIXES), re.IGNORECASE)

def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    """Removes leading/trailing whitespace and collapses multiple spaces."""
    if text is None:
        return None
    return ' '.join(text.split()).strip()

def normalize_company_name(name: Optional[str]) -> Optional[str]:
    """Attempts to normalize a company name by removing common suffixes and cleaning whitespace."""
    if not name:
        return None
    
    # 1. Normalize whitespace first
    normalized = normalize_whitespace(name)
    if not normalized:
        return None # Return if whitespace normalization results in empty

    # 2. Remove common suffixes (ensure regex handles optional preceding space/comma)
    # Simpler regex: just target the words at the end, case-insensitive
    suffix_pattern = r'\b(?:Inc|LLC|Ltd|Corp|Corporation|Limited|Incorporated)\.?\,?\s*$'
    normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE).strip()

    # 3. Remove any remaining trailing punctuation (like , or .)
    # Handle cases where suffixes were part of the name, e.g. "Corp. of Engineers"
    if normalized and not normalized[-1].isalnum():
        normalized = normalized.rstrip('.,').strip()
    
    # Final whitespace cleanup (redundant if step 1 worked, but safe)
    normalized = normalize_whitespace(normalized)

    if not normalized:
        logger.warning(f"Normalization resulted in empty string for company name: '{name}'")
        return normalize_whitespace(name) # Return original name cleaned
        
    # logger.debug(f"Normalized '{name}' -> '{normalized}'")
    return normalized

def normalize_location(location: Optional[str]) -> Optional[str]:
    """
    Basic location normalization. Cleans whitespace.
    Future enhancements: Standardize state abbreviations, country names, 
    handle formats like "City, State", "City, Country".
    """
    if not location:
        return None
    
    normalized = normalize_whitespace(location)
    
    # Example future enhancement: Standardize US states
    # state_mapping = {"New York": "NY", "California": "CA", ...}
    # parts = normalized.split(',')
    # if len(parts) == 2:
    #     city = parts[0].strip()
    #     state_or_country = parts[1].strip()
    #     if state_or_country in state_mapping:
    #         normalized = f"{city}, {state_mapping[state_or_country]}"
    
    return normalized

def clean_lead_data(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cleans and normalizes fields within a lead data dictionary."""
    cleaned = lead_data.copy()
    
    cleaned['name'] = normalize_whitespace(cleaned.get('name'))
    cleaned['email'] = normalize_whitespace(cleaned.get('email', '').lower()) # Lowercase email
    cleaned['phone'] = normalize_whitespace(cleaned.get('phone'))
    cleaned['source'] = normalize_whitespace(cleaned.get('source'))
    cleaned['notes'] = normalize_whitespace(cleaned.get('notes'))
    # Potentially normalize status if it's free text before converting to enum
    
    # Assuming company info might be directly on the lead initially
    if 'company_name' in cleaned:
         cleaned['normalized_company_name'] = normalize_company_name(cleaned.get('company_name'))
    if 'location' in cleaned:
         cleaned['normalized_location'] = normalize_location(cleaned.get('location'))
         
    # Remove keys with None values? Optional based on downstream usage.
    # cleaned = {k: v for k, v in cleaned.items() if v is not None}
    
    return cleaned

def clean_company_data(company_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cleans and normalizes fields within a company data dictionary."""
    cleaned = company_data.copy()
    
    cleaned['name'] = normalize_company_name(cleaned.get('name'))
    cleaned['website'] = normalize_whitespace(cleaned.get('website'))
    cleaned['industry'] = normalize_whitespace(cleaned.get('industry'))
    cleaned['size'] = normalize_whitespace(cleaned.get('size'))
    cleaned['location'] = normalize_location(cleaned.get('location'))
    cleaned['description'] = normalize_whitespace(cleaned.get('description'))
    
    return cleaned

def clean_job_posting_data(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cleans and normalizes fields within a job posting data dictionary."""
    cleaned = job_data.copy()
    
    cleaned['job_title'] = normalize_whitespace(cleaned.get('job_title'))
    # company_name might come from the API client (e.g., board_token) or be parsed
    cleaned['company_name'] = normalize_company_name(cleaned.get('company_name'))
    cleaned['job_location'] = normalize_location(cleaned.get('job_location'))
    cleaned['job_url'] = normalize_whitespace(cleaned.get('job_url'))
    cleaned['job_description_snippet'] = normalize_whitespace(cleaned.get('job_description_snippet'))
    cleaned['source_api'] = normalize_whitespace(cleaned.get('source_api'))
    # Normalize commitment/job_type if needed
    cleaned['commitment'] = normalize_whitespace(cleaned.get('commitment')) 
    
    return cleaned

# Example Usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    print("--- Testing Company Name Normalization ---")
    names = ["Example Corp.", "Test, Inc.", "ACME LLC", "Global Limited", "  Whitespace Corp  ", "No Suffix Co", "Inc.", None]
    for name in names:
        print(f"'{name}' -> '{normalize_company_name(name)}'")

    print("\n--- Testing Location Normalization ---")
    locations = ["  New York, NY  ", "San Francisco, CA", " London, UK", None, "Paris"]
    for loc in locations:
        print(f"'{loc}' -> '{normalize_location(loc)}'")

    print("\n--- Testing Data Cleaning ---")
    lead = {'name': '  John Doe  ', 'email': ' JOHN.DOE@example.com  ', 'company_name': 'Example, Inc. ', 'location': ' new york city, ny'}
    job = {'job_title': ' Software Engineer  ', 'company_name': 'Test Corp.', 'job_location': None}
    
    cleaned_lead = clean_lead_data(lead)
    cleaned_job = clean_job_posting_data(job)
    
    print("Original Lead:", lead)
    print("Cleaned Lead:", cleaned_lead)
    print("Original Job:", job)
    print("Cleaned Job:", cleaned_job) 