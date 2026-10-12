import os
import glob
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials missing!")
    exit(1)

client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "clients", "MAMBA_partners"))

print(f"Scanning client directory: {ROOT_DIR}")

# Find all .txt files (transcripts)
txt_files = []
for r, d, fs in os.walk(ROOT_DIR):
    for f in fs:
        if f.endswith(".txt"):
            txt_files.append(os.path.join(r, f))

print(f"Found {len(txt_files)} transcript files.")

indexed_count = 0
for file_path in txt_files:
    filename = os.path.basename(file_path)
    rel_path = os.path.relpath(file_path, ROOT_DIR)
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
            
        if not content:
            continue
            
        # Title formatting
        title = f"Mamba MVP Transcript: {filename.replace('.txt', '')}"
        
        # Upsert: delete if exists with same title
        client.table("knowledge_documents").delete().eq("title", title).execute()
        
        # Insert chunk or full content (truncate if extremely large)
        doc = {
            "title": title,
            "category": "transcript",
            "source": f"clients/MAMBA_partners/{rel_path}",
            "content": content[:25000],  # first 25k chars
            "metadata": {
                "client": "MAMBA Partners",
                "rel_path": rel_path,
                "char_length": len(content)
            }
        }
        res = client.table("knowledge_documents").insert(doc).execute()
        print(f"Indexed: {title} ({len(content)} chars)")
        indexed_count += 1
    except Exception as e:
        print(f"Error indexing {filename}: {e}")

print(f"\nSuccessfully indexed {indexed_count} client transcripts into Supabase knowledge_documents!")
