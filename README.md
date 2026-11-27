# 23JE0543_mCaffeine_FDE

## Deployment milestone

A single Django web service runs on Render and connects to Supabase PostgreSQL. The public landing page links to `/health`. Each health request executes `SELECT 1` and returns either HTTP 200 with `{"status":"ok"}` or HTTP 503 with `{"status":"unavailable"}`. The service logs database failures with a timestamp and error class. This milestone needs no tables or migrations.

### Deploy from the dashboards

1. In Supabase, choose **New project**, select a Free organization, enter a project name, generate a database password and save it in your password manager. Select **Singapore** to match the web service region, create the project, and wait for it to finish provisioning.
2. In the project's top bar choose **Connect**, select **URI** and **Session pooler**, and copy the PostgreSQL URI for port **5432**. Replace the password placeholder privately with the database password. Percent-encode any URI-reserved characters in the password. The app requests TLS automatically. [Supabase connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
3. Once `render.yaml` is on GitHub's `main` branch, open the Render Dashboard and choose **New → Blueprint**. Connect GitHub and grant access to **manabtikadar/23JE0543_mCaffeine_FDE**. Choose **Connect** beside the repository. Enter a Blueprint name, select **main**, and keep **render.yaml** as the Blueprint path.
4. Enter the completed URI in Render's **DATABASE_URL** secret field. The Blueprint generates **DJANGO_SECRET_KEY** and defines one Free Python web service in Singapore, its build and start commands, and its health check. Review the plan and click **Deploy Blueprint**. Keep the database password and complete URI in private fields. [Render Blueprint guide](https://render.com/docs/infrastructure-as-code)
5. Open the service from the Blueprint. Under **Events**, wait for **Live**. Open the assigned **onrender.com** URL and follow **Check database connection**. To inspect the HTTP status on Windows, run `curl.exe -i https://YOUR-SERVICE.onrender.com/health`, substituting the public hostname from Render. A 200 and `{"status":"ok"}` verify the hosted path end to end. If deployment stays unhealthy, check **Logs** for the error class and **Environment** for the session-pooler configuration.

### Run locally on Windows

From the repository root, use Python 3.12 and PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

On first setup, use a local editor to give each name in the ignored `.env` file a value using `NAME=value` syntax. Set `DJANGO_SECRET_KEY` to a long random secret from your password manager and `DATABASE_URL` to your PostgreSQL URI. For a loopback-only development database without TLS, append `?sslmode=disable`. Render requires TLS. The process environment takes precedence over the local file.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test config
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/`. To verify outage handling locally, stop your disposable local database while Django is running and request `/health`. Expect 503. Restart that database and request the same endpoint again to get 200.
