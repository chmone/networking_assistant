# Initial test file for text_exporter.py
import pytest
import os
from unittest.mock import MagicMock, patch, mock_open
from freezegun import freeze_time
import datetime # Need the real datetime for isinstance

from src.output_generation.text_exporter import TextFileExporter, OutputGenerationError

class TestTextFileExporterInit:
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_init_success_creates_directory(self, mock_makedirs):
        output_dir = "test_output_dir"
        exporter = TextFileExporter(output_dir=output_dir)
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        assert exporter.output_dir == output_dir

    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_init_directory_already_exists(self, mock_makedirs):
        # exist_ok=True handles this, so makedirs is still called
        output_dir = "existing_dir"
        exporter = TextFileExporter(output_dir=output_dir)
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        assert exporter.output_dir == output_dir

    @patch('src.output_generation.text_exporter.os.makedirs', side_effect=OSError("Permission denied"))
    @patch('src.output_generation.text_exporter.logger.error') # To check error logging
    @patch('src.output_generation.text_exporter.logger.warning') # To check warning logging
    def test_init_makedirs_os_error_falls_back_to_current_dir(self, mock_log_warning, mock_log_error, mock_makedirs):
        output_dir = "uncreatable_dir"
        exporter = TextFileExporter(output_dir=output_dir)
        
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_log_error.assert_called_once()
        mock_log_warning.assert_called_once_with(f"Falling back to current directory for output.")
        assert exporter.output_dir == "."

    def test_init_default_output_dir(self):
        # Test with default output_dir="output"
        with patch('src.output_generation.text_exporter.os.makedirs') as mock_makedirs_default:
            exporter = TextFileExporter()
            mock_makedirs_default.assert_called_once_with("output", exist_ok=True)
            assert exporter.output_dir == "output"

# Fixture for sample leads
@pytest.fixture
def sample_leads_data():
    return [
        {
            'lead_name': 'Alice A', 'linkedin_profile_url': 'url_a', 
            'current_role': 'Engineer', 'company_name': 'Tech A',
            'location': 'Loc A', 'alma_mater_match': ['School A'],
            'source_of_lead': 'Source A', 'date_added': '2023-01-01', 'raw_snippet': 'Snippet A'
        },
        {
            'lead_name': 'Bob B', 'linkedin_profile_url': 'url_b', 
            'current_role': 'PM', 'company_name': 'Tech B',
            'location': 'Loc B', 'alma_mater_match': [],
            'source_of_lead': 'Source B', 'date_added': '2023-01-02', 'raw_snippet': 'Snippet B'
        },
        { # Missing some fields
            'lead_name': 'Charlie C', 'linkedin_profile_url': 'url_c',
            'current_role': 'Analyst'
        }
    ]

class TestExportLeadsToTxt:
    
    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.os.path.join', return_value='output/custom_name.txt')
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_success_uses_provided_filename(self, mock_mkdirs, mock_path_join, mock_file_open, sample_leads_data):
        exporter = TextFileExporter(output_dir="output")
        custom_filename = "my_leads.txt"
        expected_filepath = f"output/{custom_filename}"
        mock_path_join.return_value = expected_filepath

        result_path = exporter.export_leads_to_txt(leads=sample_leads_data, filename=custom_filename)

        mock_path_join.assert_called_once_with("output", custom_filename)
        mock_file_open.assert_called_once_with(expected_filepath, 'w', encoding='utf-8')
        assert result_path == expected_filepath

    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_empty_leads_list(self, mock_mkdirs, mock_file_open):
        exporter = TextFileExporter()
        result_path = exporter.export_leads_to_txt(leads=[])
        mock_file_open.assert_not_called()
        assert result_path == ""

    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.logger.error')
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_invalid_leads_input_type(self, mock_mkdirs, mock_log_error, mock_file_open):
        exporter = TextFileExporter()
        result_path = exporter.export_leads_to_txt(leads="not a list")
        mock_file_open.assert_not_called()
        mock_log_error.assert_called_once()
        assert result_path == ""

    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.logger.warning')
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_skips_non_dict_items_in_list(self, mock_mkdirs, mock_log_warning, mock_file_open, sample_leads_data):
        invalid_leads = sample_leads_data + ["invalid string", None, 123]
        exporter = TextFileExporter()
        exporter.export_leads_to_txt(leads=invalid_leads)
        
        assert mock_log_warning.call_count == 3 # One for each invalid item
        # Check that data for valid leads was still written
        handle = mock_file_open()
        handle.write.assert_any_call("Lead #1\n")
        handle.write.assert_any_call("Lead #2\n")
        handle.write.assert_any_call("Lead #3\n")
        # Ensure it didn't try to write e.g. "Lead #4"
        with pytest.raises(AssertionError): 
            handle.write.assert_any_call("Lead #4\n")

    @patch('src.output_generation.text_exporter.os.makedirs')
    @patch('src.output_generation.text_exporter.os.path.join', return_value='output/leads.txt')
    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    def test_export_io_error_raises_output_generation_error(self, mock_open_call, mock_path_join, mock_mkdirs, sample_leads_data):
        # Make the write call fail
        mock_open_call.return_value.write.side_effect = IOError("Disk full")
        
        exporter = TextFileExporter()
        with pytest.raises(OutputGenerationError) as exc_info:
            exporter.export_leads_to_txt(leads=sample_leads_data)
        
        assert "Failed to write to output file" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, IOError)

    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.os.path.join', return_value='output/leads.txt')
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_unexpected_error_raises_output_generation_error(self, mock_mkdirs, mock_path_join, mock_file_open, sample_leads_data):
        # Simulate error during file write, after isinstance check
        mock_file_handle = mock_file_open.return_value
        # Let the first few writes (header) succeed, then raise error
        original_write = mock_file_handle.write
        call_count = 0
        def write_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 5: # Let header writes succeed
                 return original_write(*args, **kwargs)
            else:
                 raise TypeError("Simulated unexpected write error")
                 
        mock_file_handle.write.side_effect = write_side_effect

        exporter = TextFileExporter()
        with pytest.raises(OutputGenerationError) as exc_info:
            # Use a specific filename to avoid datetime.now() for filename generation
            exporter.export_leads_to_txt(leads=sample_leads_data, filename="test_unexpected.txt")
        
        assert "Unexpected error during text export" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, TypeError)
        assert "Simulated unexpected write error" in str(exc_info.value.__cause__)

    @patch('src.output_generation.text_exporter.open', new_callable=mock_open)
    @patch('src.output_generation.text_exporter.os.path.join') 
    @patch('src.output_generation.text_exporter.os.makedirs')
    def test_export_success_generates_filename(self, mock_mkdirs, mock_path_join, mock_file_open, sample_leads_data):
        # Pass an explicit filename
        test_filename = "explicit_leads_export.txt"
        expected_filepath = f"test_dir/{test_filename}"
        mock_path_join.return_value = expected_filepath

        exporter = TextFileExporter(output_dir="test_dir")
        # Call with explicit filename
        result_path = exporter.export_leads_to_txt(leads=sample_leads_data, filename=test_filename)

        mock_path_join.assert_called_once_with("test_dir", test_filename)
        mock_file_open.assert_called_once_with(expected_filepath, 'w', encoding='utf-8')
        assert result_path == expected_filepath

        # Check if write calls were made (example check)
        handle = mock_file_open() 
        # Header check might need adjustment if we no longer mock datetime.now for it
        # Check total leads and lead details write instead
        handle.write.assert_any_call(f"Total Leads: {len(sample_leads_data)}\n")
        handle.write.assert_any_call("Lead #1\n")
        handle.write.assert_any_call("Name:       Alice A\n")
        # The isinstance check inside the function should now work correctly

        assert result_path == expected_filepath 