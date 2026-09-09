import streamlit as st
from datetime import date
import re

# Entity Schema provided by the user
entity_schema = {
  "domain": "Banking_Party_Master",
  "entity_name": "Party",
  "attributes": [
    {
      "name": "id_prim",
      "data_type": "VARCHAR(50)",
      "is_required": True,
      "is_primary_key": True,
      "description": "Primary Party Identifier"
    },
    {
      "name": "plss",
      "data_type": "VARCHAR(20)",
      "is_required": True,
      "is_primary_key": False,
      "description": "Prospect or Active Status"
    },
    {
      "name": "first_name",
      "data_type": "VARCHAR(100)",
      "is_required": True,
      "is_primary_key": False,
      "description": "First Name"
    },
    {
      "name": "last_name",
      "data_type": "VARCHAR(100)",
      "is_required": True,
      "is_primary_key": False,
      "description": "Last Name"
    },
    {
      "name": "tax_id_type",
      "data_type": "VARCHAR(20)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Tax Identification Type"
    },
    {
      "name": "tax_id",
      "data_type": "VARCHAR(50)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Tax Identification Number"
    },
    {
      "name": "dob",
      "data_type": "DATE",
      "is_required": False,
      "is_primary_key": False,
      "description": "Date of Birth"
    },
    {
      "name": "legal_addr",
      "data_type": "VARCHAR(255)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Legal Address"
    },
    {
      "name": "prim_addr",
      "data_type": "VARCHAR(255)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Primary Address"
    },
    {
      "name": "phone_number",
      "data_type": "VARCHAR(20)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Phone Number"
    },
    {
      "name": "email_id",
      "data_type": "VARCHAR(100)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Email Address"
    },
    {
      "name": "aadhaar_no",
      "data_type": "VARCHAR(12)",
      "is_required": True,
      "is_primary_key": False,
      "description": "Aadhaar Number"
    },
    {
      "name": "alternate_phone",
      "data_type": "VARCHAR(20)",
      "is_required": False,
      "is_primary_key": False,
      "description": "Alternate Phone Number"
    }
  ]
}

st.set_page_config(layout="centered")
st.title(f"{entity_schema['entity_name']} Information Form")
st.subheader(f"Domain: {entity_schema['domain']}")

# Initialize session state for form data and errors
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'form_errors' not in st.session_state:
    st.session_state.form_errors = {}

def get_varchar_length(data_type_str):
    """Extracts the length from a VARCHAR(X) string."""
    match = re.search(r'VARCHAR\((\d+)\)', data_type_str)
    return int(match.group(1)) if match else None

def validate_form(data):
    """Performs validation on the form data based on the schema."""
    errors = {}

    for attr in entity_schema['attributes']:
        name = attr['name']
        label = attr['description']
        is_required = attr['is_required']
        data_type = attr['data_type']
        value = data.get(name)

        # 1. Required field validation
        if is_required and (value is None or (isinstance(value, str) and not value.strip())):
            errors[name] = f"{label} is required."
            continue # Skip further validation for this field if it's empty and required

        # If not required and empty, no further validation needed for this field
        if not is_required and (value is None or (isinstance(value, str) and not value.strip())):
            continue

        # 2. Data type specific validation
        if 'VARCHAR' in data_type:
            max_len = get_varchar_length(data_type)
            if max_len and len(str(value)) > max_len:
                errors[name] = f"{label} must be at most {max_len} characters long."

            if name == 'plss':
                if value not in ["Prospect", "Active"]:
                    errors[name] = f"{label} must be 'Prospect' or 'Active'."
            elif name in ['phone_number', 'alternate_phone']:
                # Remove spaces and hyphens for validation, but keep original for display
                cleaned_value = str(value).replace(" ", "").replace("-", "")
                if not re.fullmatch(r'^\d{10,20}$', cleaned_value):
                    errors[name] = f"{label} must be a valid phone number (10-20 digits)."
            elif name == 'email_id':
                if not re.fullmatch(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
                    errors[name] = f"{label} must be a valid email address."
            elif name == 'aadhaar_no':
                if not re.fullmatch(r'^\d{12}$', value):
                    errors[name] = f"{label} must be a 12-digit number."

        elif data_type == 'DATE':
            # st.date_input returns a datetime.date object or None
            if value and not isinstance(value, date):
                errors[name] = f"{label} must be a valid date."
            elif value and value > date.today():
                errors[name] = f"{label} cannot be in the future."

    return errors

with st.form(key='party_form'):
    cols = st.columns(2) # Use columns for better layout

    form_values = {}

    for i, attr in enumerate(entity_schema['attributes']):
        name = attr['name']
        label = attr['description'] + (" *" if attr['is_required'] else "")
        data_type = attr['data_type']
        is_required = attr['is_required']
        max_len = get_varchar_length(data_type)

        with cols[i % 2]:
            # Display error message if exists, above the input field
            if st.session_state.form_errors.get(name):
                st.error(st.session_state.form_errors[name])

            if name == 'plss':
                options = ["Prospect", "Active"]
                default_index = 0
                current_value = st.session_state.form_data.get(name)

                if not is_required:
                    options.insert(0, "") # Add empty option if not required
                    if current_value == "":
                        default_index = 0
                    elif current_value in options:
                        default_index = options.index(current_value)
                    else:
                        default_index = 0 # Default to empty if not required
                else: # is_required
                    if current_value in options:
                        default_index = options.index(current_value)
                    else:
                        default_index = 0 # Default to first option if required

                form_values[name] = st.selectbox(
                    label=label,
                    options=options,
                    index=default_index,
                    key=f"input_{name}",
                    help=attr['description']
                )
            elif data_type == 'DATE':
                form_values[name] = st.date_input(
                    label=label,
                    value=st.session_state.form_data.get(name, None), # None is appropriate for date_input if no value
                    key=f"input_{name}",
                    help=attr['description'],
                    max_value=date.today() # Date of Birth cannot be in the future
                )
            elif 'VARCHAR' in data_type:
                current_value = st.session_state.form_data.get(name, "")
                if max_len and max_len > 100: # Use text_area for longer text fields like addresses
                    form_values[name] = st.text_area(
                        label=label,
                        value=current_value,
                        key=f"input_{name}",
                        help=attr['description'],
                        max_chars=max_len
                    )
                else: # Default to text_input for shorter VARCHARs
                    form_values[name] = st.text_input(
                        label=label,
                        value=current_value,
                        key=f"input_{name}",
                        help=attr['description'],
                        max_chars=max_len
                    )
            # Add other data types (e.g., INT, FLOAT, BOOLEAN) here if they were in the schema

    st.markdown("---")
    submitted = st.form_submit_button("Submit Party Data")

    if submitted:
        st.session_state.form_data = form_values # Store current form values
        st.session_state.form_errors = validate_form(st.session_state.form_data)

        if st.session_state.form_errors:
            st.error("Please correct the errors in the form.")
            # Rerun to display errors next to fields
            st.experimental_rerun()
        else:
            st.success("Form submitted successfully!")
            st.write("Submitted Data:")
            for key, value in st.session_state.form_data.items():
                st.write(f"- **{key.replace('_', ' ').title()}**: {value}")
            # Clear form data and errors after successful submission
            st.session_state.form_data = {}
            st.session_state.form_errors = {}
            # Rerun to clear the form
            st.experimental_rerun()
