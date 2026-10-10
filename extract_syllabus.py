import pandas as pd
import json
import os

excel_file = "Mamba_MVP_Official_Syllabus_Schedule (2).xlsx"
df_dict = pd.read_excel(excel_file, sheet_name=None)
result = {}

for sheet_name, df in df_dict.items():
    records = df.where(pd.notnull(df), None).to_dict(orient='records')
    result[sheet_name] = records

os.makedirs("src/data", exist_ok=True)
with open("src/data/syllabus.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, default=str)
print("Successfully extracted syllabus to src/data/syllabus.json")
