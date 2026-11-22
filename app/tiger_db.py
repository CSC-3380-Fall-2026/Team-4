import os
from pathlib import Path

from supabase import Client, create_client
from dotenv import load_dotenv


def get_database() -> Client:
    """Create a Supabase client from the app's environment settings.

    Returns:
        A client configured with SUPABASE_URL and SUPABASE_KEY.

    Raises:
        ValueError: If either setting is missing.
    """
    env_file: Path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_file)
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_KEY", "")
    if url == "" or key == "":
        raise ValueError("Add SUPABASE_URL and SUPABASE_KEY to app/.env.")
    database: Client = create_client(url, key)
    return database
