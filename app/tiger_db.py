import os 
from pathlib import Path

from supabase import Client, create_client
from dotenv import load_dotenv

def get_database() -> Client:
  env_file: Path = Path(__file__).resolve().parent / ".env"
  # This is going to locate the .env inside the parent file /\
  load_dotenv(env_file)
  url: str = os.getenv("SUPABASE_URL","")
  key: str = os.getenv("SUPABASE_KEY","")
  # this line of code above will locate the supabase key and url and store its values inside the key and url
  if url == "" or key == "":
    raise ValueError(
      "Add SUPABASE_URL and SUPABASE_KEY to app/.env."
    )
   # If the url is empty or key is this will raise and Error message and report it to us
  database: Client = create_client(url, key)
  return database
   # This will creata a supabase client using our Url and key and than the client will request and save data then the return database will give the client back the code when the funcation is called.
