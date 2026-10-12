import os
import pg8000.native
from dotenv import load_dotenv

load_dotenv()

password = "iDf8E7f%Hz9ef7#wefwfw"
host = "db.amhqbzochrobnufyplgb.supabase.co"
user = "postgres"
database = "postgres"
port = 5432

print(f"Connecting to Supabase Postgres at {host}...")
try:
    con = pg8000.native.Connection(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
        ssl_context=True
    )
    print("Connected successfully!")
    
    # Enable pgvector extension
    try:
        con.run("CREATE EXTENSION IF NOT EXISTS vector;")
        print("Vector extension enabled!")
    except Exception as e:
        print(f"Vector extension note: {e}")

    # Create knowledge_documents table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS public.knowledge_documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'document',
        source TEXT NOT NULL DEFAULT 'manual',
        content TEXT NOT NULL,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    """
    con.run(create_table_sql)
    print("Table public.knowledge_documents is ready!")

    # Enable RLS
    rls_sql = """
    ALTER TABLE public.knowledge_documents ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS "Allow all access to knowledge_documents" ON public.knowledge_documents;
    CREATE POLICY "Allow all access to knowledge_documents" ON public.knowledge_documents
        FOR ALL USING (true) WITH CHECK (true);
    """
    con.run(rls_sql)
    print("RLS policy configured!")

    # Check founder_checkins table and add full-text / metadata if needed
    con.close()
    print("Supabase Knowledge Base initialization complete!")
except Exception as e:
    print(f"Error during Supabase setup: {e}")
