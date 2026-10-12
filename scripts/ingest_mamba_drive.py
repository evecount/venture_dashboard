import os
import zipfile
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENTS_DIR = os.path.join(BASE_DIR, "clients", "MAMBA_partners")

zips = [
    r"D:\Downloads\MVP Program -20261012T180300Z-1-001.zip",
    r"D:\Downloads\Activated - Mamba Partners-20261012T180317Z-1-001.zip"
]

os.makedirs(CLIENTS_DIR, exist_ok=True)
print(f"Target Directory: {CLIENTS_DIR}")

for zip_path in zips:
    if os.path.exists(zip_path):
        print(f"Extracting {os.path.basename(zip_path)}...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            for member in z.infolist():
                # Clean parts: strip trailing spaces from folder names
                parts = member.filename.replace('\\', '/').split('/')
                clean_parts = [p.strip() for p in parts if p.strip()]
                if not clean_parts:
                    continue
                target_path = os.path.join(CLIENTS_DIR, *clean_parts)
                
                if member.is_dir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with z.open(member) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
        print(f"Extracted {os.path.basename(zip_path)} successfully!")

print("\nFiles in clients/MAMBA_partners:")
for root, dirs, files in os.walk(CLIENTS_DIR):
    rel_root = os.path.relpath(root, CLIENTS_DIR)
    if files:
        print(f"[{rel_root}] ({len(files)} files)")
