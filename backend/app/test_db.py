import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("select 1;")
print("DB OK:", cur.fetchone())
cur.close()
conn.close()
