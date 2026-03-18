import os
import pandas as pd
import subprocess
import shutil

csv_path = "qlib_data/multi_coin_features.csv"
temp_dir = "qlib_data/temp_csvs"
bin_dir = "qlib_data/bin_multi_coin"

print("1. Reading unified CSV...")
df = pd.read_csv(csv_path)

print("2. Splitting by instrument...")
os.makedirs(temp_dir, exist_ok=True)
for symbol, group in df.groupby("instrument"):
    # Drop instrument column, it will use filename as default in dump_bin
    group = group.drop(columns=["instrument"])
    group.to_csv(f"{temp_dir}/{symbol.lower()}.csv", index=False)

print(f"3. Running dump_bin.py on {temp_dir}...")
# Note: we use exclude_fields because dump_bin assumes everything except date_field_name is a float feature
cmd = [
    "python3", "dump_bin.py", "dump_all",
    "--data_path", temp_dir,
    "--qlib_dir", bin_dir,
    "--date_field_name", "datetime",
    "--exclude_fields", "datetime" # symbol (instrument) is already dropped
]

subprocess.run(cmd, check=True)

print("4. Cleaning up temp files...")
shutil.rmtree(temp_dir)
print("✅ Conversion to Qlib format complete.")
