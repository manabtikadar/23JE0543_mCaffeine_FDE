# Database and file storage

Create a private Storage bucket named `po-originals`. Set `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the server environment. Apply the [Django migrations](../orders/migrations/) with `python manage.py migrate`. The [storage client](../orders/storage.py) checks the bucket visibility before uploading originals.
