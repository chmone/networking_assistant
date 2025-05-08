import os
import sys
import datetime
import logging

# Adjust path to import custom exceptions relative to src
current_dir = os.path.dirname(os.path.abspath(__file__))
core_path = os.path.abspath(os.path.join(current_dir, '..', 'core'))
if core_path not in sys.path:
    if __package__:
        from ..core.exceptions import OutputGenerationError
    else:
        try:
            from core.exceptions import OutputGenerationError
        except ImportError:
            project_root_path = os.path.abspath(os.path.join(current_dir, '..', '..'))
            if project_root_path not in sys.path:
                sys.path.insert(0, project_root_path)
            try:
                from src.core.exceptions import OutputGenerationError
            except ImportError as e:
                logging.error(f"Failed to import OutputGenerationError: {e}")
                OutputGenerationError = Exception # Fallback
else:
    from core.exceptions import OutputGenerationError

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class TextFileExporter:
    def __init__(self, output_dir="output"):
        """
        Initializes the TextFileExporter, ensuring the output directory exists.
        """
        self.output_dir = output_dir
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Ensured output directory exists: {self.output_dir}")
        except OSError as e:
            logger.error(f"Could not create output directory {self.output_dir}: {e}")
            # Raise a specific error if directory creation fails critically
            # raise OutputGenerationError(f"Failed to create output directory {self.output_dir}", output_path=output_dir, original_exception=e)
            self.output_dir = "." 
            logger.warning(f"Falling back to current directory for output.")

    def export_leads_to_txt(self, leads: list, filename: str = None) -> str:
        """
        Export leads to a human-readable text file.
        Returns the path to the created file.
        Raises OutputGenerationError on failure.
        """
        if not isinstance(leads, list):
            msg = f"Invalid input to export_leads_to_txt: expected a list, got {type(leads)}"
            logger.error(msg)
            # raise OutputGenerationError(msg) # Or raise specific error type
            return ""
            
        if not leads:
            logger.info("No leads provided to export. Skipping file creation.")
            return ""
            
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"leads_{timestamp}.txt"
            
        file_path = os.path.join(self.output_dir, filename)
        
        logger.info(f"Exporting {len(leads)} leads to text file: {file_path}")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Lead Export - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"Total Leads: {len(leads)}\n")
                f.write("="*40 + "\n\n")
                for i, lead in enumerate(leads):
                    if not isinstance(lead, dict):
                        logger.warning(f"Skipping invalid item at index {i} in leads list (not a dict): {lead}")
                        continue
                    f.write(f"Lead #{i+1}\n")
                    f.write("-"*20 + "\n")
                    f.write(f"Name:       {lead.get('lead_name', 'N/A')}\n")
                    f.write(f"Profile:    {lead.get('linkedin_profile_url', 'N/A')}\n")
                    f.write(f"Role:       {lead.get('current_role', 'N/A')}\n")
                    f.write(f"Company:    {lead.get('company_name', 'N/A')}\n")
                    f.write(f"Location:   {lead.get('location', 'N/A')}\n")
                    
                    schools = lead.get('alma_mater_match', [])
                    if isinstance(schools, list):
                        f.write(f"Schools:    {', '.join(schools) if schools else 'N/A'}\n")
                    else: # Handle unexpected type
                        f.write(f"Schools:    {str(schools)}\n") 
                        
                    f.write(f"Source:     {lead.get('source_of_lead', 'N/A')}\n")
                    # Format datetime object to string if it exists
                    date_added = lead.get('date_added')
                    date_str = date_added.strftime("%Y-%m-%d %H:%M:%S") if isinstance(date_added, datetime.datetime) else str(date_added or 'N/A')
                    f.write(f"Added:      {date_str}\n")
                    f.write(f"Snippet:    {lead.get('raw_snippet', 'N/A')}\n") # Optional: Include raw snippet
                    f.write("\n" + "="*40 + "\n\n")
                    
            logger.info(f"Successfully exported leads to {file_path}")
            return file_path
            
        except IOError as e:
            logger.error(f"Could not write to file {file_path}: {e}")
            # Raise specific error for file I/O issues
            raise OutputGenerationError(f"Failed to write to output file", output_path=file_path, original_exception=e) from e
        except Exception as e:
            logger.exception(f"An unexpected error occurred during text export to {file_path}: {e}")
            # Wrap other unexpected errors
            raise OutputGenerationError(f"Unexpected error during text export", output_path=file_path, original_exception=e) from e

# Example usage
if __name__ == '__main__':
    print("Testing TextFileExporter...")
    exporter = TextFileExporter()
    
    # Sample leads (similar to LeadProcessor test)
    sample_leads_for_export = [
         {
            'lead_name': 'Alice Alumni', 'linkedin_profile_url': 'http://linkedin/in/alice', 
            'current_role': 'Software Engineer', 'company_name': 'Big Tech',
            'location': 'San Francisco, CA', 'alma_mater_match': ['Questrom'],
            'source_of_lead': 'Alumni Search: Questrom', 'date_added': datetime.datetime.now().isoformat(), 'raw_snippet': 'Alice snippet...'
        },
        {
            'lead_name': 'Bob PM', 'linkedin_profile_url': 'http://linkedin/in/bob', 
            'current_role': 'Senior Product Manager', 'company_name': 'Startup Co',
            'location': 'New York City Area', 'alma_mater_match': [],
            'source_of_lead': 'PM Search: New York City', 'date_added': datetime.datetime.now().isoformat(), 'raw_snippet': 'Bob snippet...'
        },
        {
            'lead_name': 'Charlie NoData' # Missing most fields
        },
        "Invalid entry"
    ]

    print(f"\nExporting {len(sample_leads_for_export)} sample leads...")
    output_path = exporter.export_leads_to_txt(sample_leads_for_export)
    
    if output_path:
        print(f"Export successful. Check the file: {output_path}")
        # Optional: Read the file back to verify content
        try:
            with open(output_path, 'r', encoding='utf-8') as f_verify:
                print("\n--- File Content Snippet ---")
                print(f_verify.read(500)) # Print first 500 chars
                print("...")
        except Exception as e:
             print(f"Error reading back file for verification: {e}")
    else:
        print("Export failed.") 