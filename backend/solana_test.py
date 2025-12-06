import os
from dotenv import load_dotenv
from moralis import sol_api

load_dotenv(dotenv_path="../.env")

print("Inspecting sol_api.token:")
print(dir(sol_api.token))

print("\nInspecting sol_api.account:")
print(dir(sol_api.account))
