import os
import gspread
from google.oauth2.service_account import Credentials
from supabase import create_client, Client
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

# 1. Securely load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, NVIDIA_API_KEY]):
    raise ValueError("Missing required keys in .env file!")

# --- CONFIGURATION ---
# Paste the ID from your Google Sheet URL here:
SPREADSHEET_ID = "10jz-23jHhMSXWDPqTvIUbUIahZvIv9BXTvTVMjzxkfw"
WORKSHEET_NAME = "sheet1" # Double check the tab at the bottom of your screen!

# 2. Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
embedder = NVIDIAEmbeddings(model="nvidia/nv-embedqa-e5-v5")

# 3. Authenticate with Google Sheets
scopes = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]
creds = Credentials.from_service_account_file("service-account.json", scopes=scopes)
client = gspread.authorize(creds)

def sync_finance_data():
    print(f"Connecting to Google Sheet: {SPREADSHEET_ID}...")
    
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    records = sheet.get_all_records() 
    
    clean_records = []
    print(f"Found {len(records)} budget lines. Generating Nvidia embeddings...")

    for row in records:
        raw_category = str(row.get("Category", ""))
        if not raw_category:
            continue
            
        clean_category_key = raw_category.lower().replace(" ", "_")
        raw_budget = str(row.get("Budget Remaining", "0"))
        clean_budget = float(raw_budget.replace("$", "").replace(",", ""))
        
        # Embed the human-readable text
        vector = embedder.embed_query(raw_category)
        
        record = {
            "category": clean_category_key,
            "budget_remaining": clean_budget,
            "currency": row.get("Currency", "USD"),
            "owner": row.get("Owner", "Unknown"),
            "embedding": vector,
            "last_synced_from": "Google Sheets"
        }
        clean_records.append(record)

    print(f"Pushing {len(clean_records)} embedded records to Supabase...")
    supabase.table("finance_budgets").upsert(clean_records, on_conflict="category").execute()
    
    print("✅ Finance Sync Complete! Semantic vectors are live in Layer 2.")

if __name__ == "__main__":
    sync_finance_data()