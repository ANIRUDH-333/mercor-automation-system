import os
import json
from dotenv import load_dotenv
from pyairtable import Api

# Load environment variables from .env file
load_dotenv()

# --- 1. SETUP ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID]):
    raise ValueError("API Key and Base ID must be set in the .env file.")

api = Api(AIRTABLE_API_KEY)

APPLICANTS_TABLE = api.table(AIRTABLE_BASE_ID, "Applicants")
PERSONAL_TABLE = api.table(AIRTABLE_BASE_ID, "Personal Details")
EXPERIENCE_TABLE = api.table(AIRTABLE_BASE_ID, "Work Experience")
SALARY_TABLE = api.table(AIRTABLE_BASE_ID, "Salary Preferences")

def decompress_applicant_data(applicant_id_to_process: str):
    """Reads compressed JSON and upserts data into child tables."""
    print(f"Decompressing data for Applicant ID: {applicant_id_to_process}...")

    # --- 2. FETCH AND PARSE JSON ---
    formula = f"{{Applicant ID}} = '{applicant_id_to_process}'"
    applicant_record = APPLICANTS_TABLE.first(formula=formula)
    if not applicant_record:
        print(f"Error: Applicant with ID '{applicant_id_to_process}' not found.")
        return

    record_id = applicant_record['id']
    try:
        compressed_json_str = applicant_record['fields']['Compressed JSON']
        applicant_data = json.loads(compressed_json_str)
    except (KeyError, json.JSONDecodeError):
        print(f"Error: Could not read or parse JSON for Applicant ID {applicant_id_to_process}.")
        return

    # --- 3. UPSERT PERSONAL DETAILS (One-to-One) ---
    personal_data = applicant_data.get("personal", {})
    if personal_data:
        personal_record = PERSONAL_TABLE.first(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        personal_data["Applicant"] = [record_id] 
        personal_data.pop('Id', None)
        if personal_record:
            print("  > Updating Personal Details...")
            PERSONAL_TABLE.update(personal_record['id'], personal_data)
        else:
            print("  > Creating Personal Details...")
            PERSONAL_TABLE.create(personal_data)

    # --- 4. SYNC WORK EXPERIENCE (One-to-Many) ---
    experience_data = applicant_data.get("experience", [])
    if experience_data:
        existing_exp_records = EXPERIENCE_TABLE.all(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        if existing_exp_records:
            record_ids_to_delete = [rec['id'] for rec in existing_exp_records]
            print(f"  > Deleting {len(record_ids_to_delete)} old Work Experience records...")
            EXPERIENCE_TABLE.batch_delete(record_ids_to_delete)
        
        print(f"  > Creating {len(experience_data)} new Work Experience records...")
        records_to_create = []
        for exp in experience_data:
            exp["Applicant"] = [record_id]
            exp.pop('Id', None)
            records_to_create.append(exp)
        EXPERIENCE_TABLE.batch_create(records_to_create)

    # --- 5. UPSERT SALARY PREFERENCES (One-to-One) ---
    salary_data = applicant_data.get("salary", {})
    if salary_data:
        salary_record = SALARY_TABLE.first(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        salary_data["Applicant"] = [record_id]
        salary_data.pop('Id', None)
        if salary_record:
            print("  > Updating Salary Preferences...")
            SALARY_TABLE.update(salary_record['id'], salary_data)
        else:
            print("  > Creating Salary Preferences...")
            SALARY_TABLE.create(salary_data)

    print(f"\nSuccessfully decompressed data for Applicant ID: {applicant_id_to_process}")


# --- Example Usage ---
if __name__ == "__main__":
    target_applicant_id = "1"
    decompress_applicant_data(target_applicant_id)