import os
from pypdf import PdfReader
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

# 2. Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
embedder = NVIDIAEmbeddings(model="nvidia/nv-embedqa-e5-v5")

def sync_security_data():
    file_path = "data/security_policy.pdf"
    print(f"Reading PDF: {file_path}...")
    
    reader = PdfReader(file_path)
    clean_records = []
    
    print(f"Found {len(reader.pages)} pages. Generating Nvidia embeddings for each page...")

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text.strip():
            continue
            
        page_num = i + 1
        print(f"Embedding Page {page_num}...")
        
        # Generate Vector
        vector = embedder.embed_query(text)
        
        record = {
            "document_name": "Veridian Global Information Security Policy v4.2",
            "chunk_text": text,
            "embedding": vector,
            "page_number": page_num
        }
        clean_records.append(record)

    print(f"Pushing {len(clean_records)} embedded pages to Supabase...")
    
    # Clear old data if re-running
    supabase.table("security_policies").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    supabase.table("security_policies").insert(clean_records).execute()
    
    print("✅ Security Sync Complete! PDF vectors are live in Layer 2.")

if __name__ == "__main__":
    sync_security_data()