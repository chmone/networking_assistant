import streamlit as st
import requests
import pandas as pd
from typing import List, Dict, Any, Optional
import logging

# Assuming the FastAPI backend runs on port 8000 by default
API_BASE_URL = "http://localhost:8000/api/v1"

logger = logging.getLogger(__name__) # Use Streamlit's logger or standard logging

def get_leads_from_api(status: Optional[str] = None, limit: int = 100,
                         name_contains: Optional[str] = None,
                         company_id: Optional[int] = None,
                         sort_by: Optional[str] = None,
                         sort_order: str = 'asc') -> List[Dict[str, Any]]:
    """Fetches leads from the backend API with filtering and sorting."""
    endpoint = f"{API_BASE_URL}/leads/"
    params = {"limit": limit, "sort_order": sort_order}
    if status:
        params['status'] = status
    if name_contains:
        params['name_contains'] = name_contains
    if company_id:
        params['company_id'] = company_id
    if sort_by:
        params['sort_by'] = sort_by
        
    try:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to API: {e}")
        return []
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        logger.exception("Error fetching leads from API")
        return []

def get_lead_details_from_api(lead_id: int) -> Optional[Dict[str, Any]]:
    """Fetches detailed information for a single lead."""
    endpoint = f"{API_BASE_URL}/leads/{lead_id}"
    try:
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching lead details for ID {lead_id}: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching lead details: {e}")
        logger.exception(f"Error fetching lead details for ID {lead_id}")
        return None

def update_lead_via_api(lead_id: int, update_data: Dict[str, Any]) -> bool:
    """Updates a lead via the backend API."""
    endpoint = f"{API_BASE_URL}/leads/{lead_id}"
    try:
        response = requests.put(endpoint, json=update_data, timeout=10)
        response.raise_for_status()
        st.success(f"Lead ID {lead_id} updated successfully!")
        return True
    except requests.exceptions.RequestException as e:
        err_detail = "Unknown error"
        if e.response is not None:
            try: err_detail = e.response.json().get("detail", str(e))
            except: err_detail = str(e.response.content)
        st.error(f"Error updating lead ID {lead_id}: {err_detail}")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred while updating lead: {e}")
        logger.exception(f"Error updating lead ID {lead_id}")
        return False

# --- Streamlit App Layout ---

st.set_page_config(page_title="Networking Leads", layout="wide")

st.title("Lead Management Dashboard")

# --- Sidebar Filters & Sorting (Task 13) ---
st.sidebar.header("Filters & Sorting")

# Status Filter
lead_status_options = ["All", "New", "Contacted", "Interested", "Not Interested", "Converted"]
selected_status = st.sidebar.selectbox("Filter by Status:", options=lead_status_options)
status_filter = selected_status if selected_status != "All" else None

# Name Filter
name_filter = st.sidebar.text_input("Filter by Name (contains):")

# Company Filter (Requires fetching companies first - basic implementation)
# TODO: Fetch company list from API for dropdown
company_filter_id = st.sidebar.number_input("Filter by Company ID:", min_value=1, step=1, value=None)

# Sorting Options
lead_sort_options = {
    "None": None, 
    "Name": "name", 
    "Status": "status", 
    "Created At": "created_at",
    "Updated At": "updated_at"
}
selected_sort_display = st.sidebar.selectbox("Sort By:", options=list(lead_sort_options.keys()))
sort_by_field = lead_sort_options[selected_sort_display]

sort_order_options = ["asc", "desc"]
selected_sort_order = st.sidebar.selectbox("Sort Order:", options=sort_order_options)

# --- Main Content Area ---
st.header("Leads")

# Fetch data based on filters and sorting
leads_data = get_leads_from_api(
    status=status_filter,
    name_contains=name_filter if name_filter else None,
    company_id=company_filter_id,
    sort_by=sort_by_field,
    sort_order=selected_sort_order
)

if not leads_data:
    st.warning(f"No leads found{f' with status \'{status_filter}\'' if status_filter else ''}. Try adding some via the API or check API connection.")
else:
    # Convert to DataFrame for better display
    try:
        df_leads = pd.DataFrame(leads_data)
        # Select and reorder columns for display
        display_columns = [
            'id', 'name', 'status', 'company_id', 
            'email', 'phone', 'source', 'notes', 
            'created_at', 'updated_at'
        ]
        # Filter out columns not present in the DataFrame to avoid errors
        display_columns = [col for col in display_columns if col in df_leads.columns]
        
        st.dataframe(df_leads[display_columns], use_container_width=True)
        st.info(f"Displaying {len(df_leads)} leads.")
        
        # Allow downloading data
        @st.cache_data # Cache the conversion
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode('utf-8')

        csv_data = convert_df_to_csv(df_leads[display_columns])
        st.download_button(
            label="Download data as CSV",
            data=csv_data,
            file_name='leads_data.csv',
            mime='text/csv',
        )
        
    except Exception as e:
        st.error("Error displaying leads data.")
        logger.exception("Error converting leads data to DataFrame or displaying it.")
        st.json(leads_data) # Display raw JSON as fallback

# --- Lead Detail View (Task 12) ---
st.divider()
st.header("Lead Details")

if not leads_data: # If no leads were fetched initially
    st.info("No leads available to select for details.")
elif 'df_leads' in locals() and not df_leads.empty:
    # Option 1: Select by ID from a list
    lead_id_options = [None] + df_leads['id'].tolist()
    selected_lead_id_for_detail = st.selectbox(
        "Select Lead ID to View Details:", 
        options=lead_id_options, 
        format_func=lambda x: "Select..." if x is None else x
    )

    # Option 2: Allow entering ID directly (could be combined or alternative)
    # entered_lead_id = st.number_input("Or Enter Lead ID:", min_value=1, step=1, value=None)
    # final_selected_id = entered_lead_id if entered_lead_id else selected_lead_id_for_detail
    final_selected_id = selected_lead_id_for_detail

    if final_selected_id:
        with st.spinner(f"Fetching details for Lead ID: {final_selected_id}..."):
            lead_details = get_lead_details_from_api(final_selected_id)
        
        if lead_details:
            st.subheader(f"Details for Lead: {lead_details.get('name', 'N/A')} (ID: {lead_details.get('id')})")
            # Display details - can be more formatted
            # st.json(lead_details) # Raw JSON
            
            # More structured display:
            # Use session state to manage edits without immediate re-runs affecting input
            if f"lead_detail_{final_selected_id}_status" not in st.session_state:
                st.session_state[f"lead_detail_{final_selected_id}_status"] = lead_details.get("status")
            if f"lead_detail_{final_selected_id}_notes" not in st.session_state:
                st.session_state[f"lead_detail_{final_selected_id}_notes"] = lead_details.get("notes", "")

            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Name:", value=lead_details.get("name", ""), disabled=True, key=f"detail_name_readonly_{final_selected_id}")
                st.text_input("Email:", value=lead_details.get("email", ""), disabled=True, key=f"detail_email_readonly_{final_selected_id}")
                st.text_input("Phone:", value=lead_details.get("phone", ""), disabled=True, key=f"detail_phone_readonly_{final_selected_id}")
                
                # Editable Status (Task 15)
                current_status = st.session_state[f"lead_detail_{final_selected_id}_status"]
                status_idx = lead_status_options.index(current_status) if current_status in lead_status_options else 0
                new_status = st.selectbox(
                    "Status:", 
                    options=lead_status_options, 
                    index=status_idx,
                    key=f"edit_status_{final_selected_id}" # Use a unique key for the editable widget
                )
                st.session_state[f"lead_detail_{final_selected_id}_status"] = new_status

            with col2:
                st.text_input("Source:", value=lead_details.get("source", ""), disabled=True, key=f"detail_source_readonly_{final_selected_id}")
                st.text_input("Company ID:", value=str(lead_details.get("company_id", "N/A")), disabled=True, key=f"detail_comp_id_readonly_{final_selected_id}")
                st.text_input("Created At:", value=str(lead_details.get("created_at", "")), disabled=True, key=f"detail_created_readonly_{final_selected_id}")
                st.text_input("Updated At:", value=str(lead_details.get("updated_at", "")), disabled=True, key=f"detail_updated_readonly_{final_selected_id}")
            
            # Editable Notes (Task 15)
            current_notes = st.session_state[f"lead_detail_{final_selected_id}_notes"]
            new_notes = st.text_area(
                "Notes:", 
                value=current_notes, 
                height=150, 
                key=f"edit_notes_{final_selected_id}"
            )
            st.session_state[f"lead_detail_{final_selected_id}_notes"] = new_notes

            if st.button("Save Lead Changes", key=f"save_button_{final_selected_id}"):
                update_payload = {}
                if new_status != lead_details.get("status"):
                    update_payload["status"] = new_status
                if new_notes != lead_details.get("notes", ""):
                    update_payload["notes"] = new_notes
                
                if update_payload:
                    if update_lead_via_api(final_selected_id, update_payload):
                        # Refresh data by clearing cache and re-fetching OR just re-run section
                        # For simplicity, we can just rely on user re-selecting or Streamlit's re-run on widget change for now.
                        # More robust: st.experimental_rerun() or clear specific cache.
                        st.success("Changes saved! Details will refresh on next interaction or selection.")
                        # To force a refresh of details immediately, we could re-fetch here:
                        # lead_details = get_lead_details_from_api(final_selected_id) 
                        # And then update session state and widgets if successful.
                else:
                    st.info("No changes detected to save.")
        elif final_selected_id: # If an ID was selected but details weren't found
            st.error(f"Could not load details for Lead ID: {final_selected_id}. It might have been deleted or an error occurred.")
    else:
        st.info("Select a Lead ID from the dropdown above to see more details.")
elif 'df_leads' in locals() and df_leads.empty:
    st.info("Lead list is empty. No details to show.")
else: # Should not happen if leads_data was populated but df_leads not created
    st.info("Leads data is available, but not yet processed for selection.")

# Placeholder for future enhancements (Task 12, 13, 15)
# - Clicking a lead to view details
# - Advanced filtering/sorting controls
# - Ability to update status/notes directly from the UI 