from supabase import Client
from tiger_db import get_database

def main() -> None:
  database: Client = get_database()

  print(
    database.table("connection_test")
    .select("message")
    .execute()
    .data
  )
if __name__ == "__main__":
  main()
# this will check to see if the Project can read the stored messeges in Supabase
