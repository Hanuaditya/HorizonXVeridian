import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import Literal

# 1. Securely load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, NVIDIA_API_KEY]):
    raise ValueError("Missing required keys in .env file!")

# 2. Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize the Nvidia LLM
llm = ChatNVIDIA(model="meta/llama3-70b-instruct") 

# 3. Define the Strict Pydantic Schema (The Contract)
class EmployeeRecord(BaseModel):
    full_name: str = Field(description="The employee's first and last name, e.g., 'Arjun Rao'")
    department: str = Field(description="The department the employee belongs to")
    status: Literal['ACTIVE', 'ON_PATERNITY_LEAVE', 'ON_MATERNITY_LEAVE', 'TERMINATED', 'UNKNOWN'] = Field(
        description="The current employment status. Treat 'New Hire' as 'ACTIVE'."
    )
    job_title: str = Field(description="The employee's exact job title")

# 4. Bind the schema via Output Parser
parser = PydanticOutputParser(pydantic_object=EmployeeRecord)

# 5. Define a clean, simple prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an enterprise ETL processor. Extract the requested fields from the messy HR record.\n\n{format_instructions}"),
    ("human", "Messy HR Record:\n{raw_record}")
])

extraction_chain = prompt | llm | parser

def sync_hr_data():
    print("Fetching messy HR data from bamboohr_db.json...")
    
    with open('data/bamboohr_db.json', 'r') as file:
        raw_data = json.load(file)
    
    employees = raw_data.get("employees", [])
    clean_records = []

    print(f"Found {len(employees)} messy records. Extracting strictly via Pydantic + Nvidia...")
    for emp in employees:
        print(f"  -> Extracting: {emp.get('displayName')}...")
        
        try:
            # The LLM returns a fully validated Pydantic Python object via the parser
            clean_data_obj = extraction_chain.invoke({
                "raw_record": json.dumps(emp),
                "format_instructions": parser.get_format_instructions()
            })
            
            # Convert the Pydantic object back to a normal dictionary for Supabase
            clean_records.append(clean_data_obj.dict())
        except Exception as e:
            print(f"  [!] Validation Error for {emp.get('displayName')}: {e}")

    print(f"\nExtraction complete. Pushing {len(clean_records)} pristine records to Supabase...")
    
    # Clear old data if re-running
    supabase.table("hr_employees").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    
    # Insert clean records
    supabase.table("hr_employees").insert(clean_records).execute()
    
    print("✅ HR Sync Complete! Data is safely in Layer 2.")

if __name__ == "__main__":
    sync_hr_data()