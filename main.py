import os
import json
import time # Import the time library for retry logic
from datetime import datetime
from dotenv import load_dotenv
from pyairtable import Api
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# --- 1. SETUP ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, GOOGLE_API_KEY]):
    raise ValueError("Airtable keys and Google API Key must be set in the .env file.")

# Configure the Gemini client
genai.configure(api_key=GOOGLE_API_KEY)

# Configure the Airtable client
api = Api(AIRTABLE_API_KEY)

# Define all table connections
APPLICANTS_TABLE = api.table(AIRTABLE_BASE_ID, "Applicants")
PERSONAL_TABLE = api.table(AIRTABLE_BASE_ID, "Personal Details")
EXPERIENCE_TABLE = api.table(AIRTABLE_BASE_ID, "Work Experience")
SALARY_TABLE = api.table(AIRTABLE_BASE_ID, "Salary Preferences")
SHORTLISTED_LEADS_TABLE = api.table(AIRTABLE_BASE_ID, "Shortlisted Leads")

# --- Constants for Shortlisting ---
TIER_1_COMPANIES = {"google", "meta", "openai", "apple", "amazon", "netflix", "microsoft"}
APPROVED_LOCATIONS = {"us", "united states", "canada", "uk", "united kingdom", "germany", "india"}

# --- HELPER & AUTOMATION FUNCTIONS ---

def calculate_total_experience(experience_list):
    """Calculates total years of experience from a list of jobs."""
    total_months = 0
    for job in experience_list:
        try:
            start_date = datetime.strptime(job.get("Start"), "%Y-%m-%d")
            end_date_str = job.get("End")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else datetime.now()
            total_months += (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        except (ValueError, TypeError):
            continue
    return total_months / 12

def evaluate_shortlisting(applicant_record, applicant_json):
    """Evaluates an applicant's JSON against shortlisting rules."""
    print("  > Evaluating for shortlist...")
    
    # Rule 1: Experience
    experience_list = applicant_json.get("experience", [])
    total_exp_years = calculate_total_experience(experience_list)
    worked_at_tier_1 = any(job.get("Company", "").lower() in TIER_1_COMPANIES for job in experience_list)
    experience_ok = (total_exp_years >= 4) or worked_at_tier_1
    
    # Rule 2: Compensation
    salary = applicant_json.get("salary", {})
    rate = salary.get("Preferred Rate", float('inf'))
    availability = salary.get("Availability (hrs/wk)", 0)
    compensation_ok = (rate is not None and rate <= 100) and (availability is not None and availability >= 20)

    # Rule 3: Location
    personal = applicant_json.get("personal", {})
    location = personal.get("Location", "").lower()
    location_ok = any(loc in location for loc in APPROVED_LOCATIONS)
    
    # Final Decision
    if experience_ok and compensation_ok and location_ok:
        print("  > Applicant meets all criteria. Shortlisting...")
        reason = f"Exp: {total_exp_years:.1f} yrs (Tier-1: {worked_at_tier_1}), Comp: ${rate}/hr @ {availability} hrs/wk, Loc: {personal.get('Location')}"
        
        SHORTLISTED_LEADS_TABLE.create({
            "Applicant": [applicant_record['id']],
            "Compressed JSON": json.dumps(applicant_json, indent=2),
            "Score Reason": reason
        })
        print("  > Successfully created Shortlisted Lead record.")
    else:
        print("  > Applicant does not meet shortlist criteria.")

def parse_llm_response(response_text):
    """Parses the raw text response from the LLM into a dictionary."""
    parsed_data = {}
    lines = response_text.strip().split('\n')
    current_section = None

    for line in lines:
        if line.startswith("Summary:"):
            parsed_data["LLM Summary"] = line.replace("Summary:", "").strip()
            current_section = "summary"
        elif line.startswith("Score:"):
            try:
                parsed_data["LLM Score"] = int(line.replace("Score:", "").strip())
            except ValueError:
                continue
            current_section = "score"
        elif line.startswith("Issues:") or line.startswith("Follow-Ups:"):
            if "LLM Follow-Ups" not in parsed_data:
                parsed_data["LLM Follow-Ups"] = ""
            parsed_data["LLM Follow-Ups"] += line + "\n"
            current_section = "follow_ups"
        elif current_section == "follow_ups" and line.strip():
            parsed_data["LLM Follow-Ups"] += line + "\n"
            
    if "LLM Follow-Ups" in parsed_data:
        parsed_data["LLM Follow-Ups"] = parsed_data["LLM Follow-Ups"].strip()

    return parsed_data

def evaluate_with_llm(applicant_record, applicant_json):
    """Sends applicant JSON to Gemini for evaluation, with retries and token caps."""
    print("  > Sending data to Gemini for evaluation...")
    
    if applicant_record.get('fields', {}).get('LLM Score'):
        print("  > Applicant already has an LLM score. Skipping.")
        return

    # Model name and setup
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a recruiting analyst. Given this JSON applicant profile, do four things:
    1. Provide a concise 75-word summary.
    2. Rate overall candidate quality from 1-10 (higher is better).
    3. List any data gaps or inconsistencies you notice.
    4. Suggest up to three follow-up questions to clarify gaps.

    Return your response in exactly this format:
    Summary: <text>
    Score: <integer>
    Issues: <comma-separated list or 'None'>
    Follow-Ups: <bullet list>

    Applicant JSON:
    {json.dumps(applicant_json, indent=2)}
    """
    
    # --- Retry and Backoff Logic ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # --- Generation Config for Token Cap ---
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=0.5
            )
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            response_text = response.text
            print("  > Gemini response received.")
            
            update_data = parse_llm_response(response_text)
            
            if update_data:
                APPLICANTS_TABLE.update(applicant_record['id'], update_data)
                print("  > Successfully updated applicant record with Gemini evaluation.")
            
            return # Exit the function on success

        except Exception as e:
            print(f"  > An error occurred during Gemini evaluation (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt # Exponential backoff: 1, 2, 4 seconds
                print(f"  > Retrying in {wait_time} second(s)...")
                time.sleep(wait_time)
            else:
                print("  > Max retries reached. LLM evaluation failed.")

# --- MAIN ORCHESTRATION FUNCTION ---

def compress_evaluate_enrich(applicant_id_to_process: str):
    """Main function to compress data, then evaluate it for shortlisting and LLM enrichment."""
    print(f"Processing Applicant ID: {applicant_id_to_process}...")
    try:
        # 1. Fetch main applicant record
        formula = f"{{Applicant ID}} = '{applicant_id_to_process}'"
        applicant_record = APPLICANTS_TABLE.first(formula=formula)
        if not applicant_record:
            print(f"Error: Applicant with ID '{applicant_id_to_process}' not found.")
            return

        record_id = applicant_record['id']
        
        # 2. Fetch all child records
        personal_details = PERSONAL_TABLE.first(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        work_experiences = EXPERIENCE_TABLE.all(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        salary_prefs = SALARY_TABLE.first(formula=f"{{Applicant}} = '{applicant_id_to_process}'")
        
        # 3. Build the complete JSON object
        personal_data = personal_details.get('fields', {}) if personal_details else {}
        personal_data.pop('Applicant', None)
        
        experience_data = []
        if work_experiences:
            for exp in work_experiences:
                fields = exp.get('fields', {})
                fields.pop('Applicant', None)
                experience_data.append(fields)

        salary_data = salary_prefs.get('fields', {}) if salary_prefs else {}
        salary_data.pop('Applicant', None)

        final_json = {
            "personal": personal_data,
            "experience": experience_data,
            "salary": salary_data
        }
        
        # 4. Write the compressed JSON back to Airtable
        APPLICANTS_TABLE.update(record_id, {"Compressed JSON": json.dumps(final_json, indent=2)})
        print(f"  > Successfully compressed data for Applicant ID: {applicant_id_to_process}")

        # 5. Run the shortlisting evaluation
        evaluate_shortlisting(applicant_record, final_json)
        
        # 6. Run the LLM enrichment
        evaluate_with_llm(applicant_record, final_json)

    except Exception as e:
        print(f"An error occurred: {e}")

# --- SCRIPT EXECUTION ---
if __name__ == "__main__":
    target_applicant_id = "4" 
    compress_evaluate_enrich(target_applicant_id)