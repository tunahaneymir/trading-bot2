"""
PostgreSQL Connection Test
==========================
Bu dosya .env ayarlarının doğru okunup okunmadığını ve PostgreSQL bağlantısının çalıştığını test eder.
"""

import os
import psycopg2
from dotenv import load_dotenv

# .env dosyasını yükle
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


# ENV değişkenlerini oku
host = os.getenv("POSTGRES_HOST") or os.getenv("CONFIG_POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT") or os.getenv("CONFIG_POSTGRES_PORT")
db = os.getenv("POSTGRES_DB") or os.getenv("CONFIG_POSTGRES_DB")
user = os.getenv("POSTGRES_USER") or os.getenv("CONFIG_POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD") or os.getenv("CONFIG_POSTGRES_PASSWORD")

print("🔌 Trying to connect to PostgreSQL...")
print(f"   Host={host}, Port={port}, DB={db}, User={user}")

try:
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=password,
    )
    print("\n✅ Connection successful!")
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"   PostgreSQL version: {version[0]}")
    cur.close()
    conn.close()

except Exception as e:
    print("\n❌ Connection failed!")
    print(e)
