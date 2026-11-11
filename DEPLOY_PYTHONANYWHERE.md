# Deploying Tanda on PythonAnywhere (free tier)

This guide takes the project from your computer to a public address like
`https://yourusername.pythonanywhere.com`. It is written for a first deployment.
Replace `yourusername` with your PythonAnywhere username (in lowercase in the web
address). Use the exact username shown in the **Files** tab when typing folder paths.

## Why PythonAnywhere free tier fits this project

- Product photos and the SQLite database are stored on a **persistent disk**, so uploads
  and orders are not lost when you reload (most other free hosts wipe their disk).
- Static files and photos are served by PythonAnywhere itself, so no extra packages
  (WhiteNoise, Gunicorn) are needed. `requirements.txt` stays the same.
- HTTPS is included.

Limits you must know about (free account):

- One web app, at `yourusername.pythonanywhere.com`. No custom domain.
- 512 MB disk and 100 CPU-seconds per day. This is enough for a small demo shop.
- The free web app expires after 1 month. Each month, open the **Web** tab and click
  **Run until 1 month from today**. PythonAnywhere emails you a reminder. Put it in your
  calendar.
- No Jupyter notebooks, and outgoing internet from the server is limited. The shop does
  not need outgoing internet. Bootstrap loads in the visitor's browser, not on the server.

---

## Part A. On your computer

### A1. Copy the fixed files into your project folder
Copy the files from `tanda_deploy_fixes.zip` over the same paths in your project, then run
the tests:

```powershell
python manage.py test
```

Expected: `OK (skipped=3)`.

### A2. Update your local `.env`
Your local `.env` must now say that you are developing locally (debug is off by default):

```text
DJANGO_SECRET_KEY=any-long-random-text
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,unreeling-catalyst-path.ngrok-free.dev
DJANGO_CSRF_TRUSTED_ORIGINS=https://unreeling-catalyst-path.ngrok-free.dev
```

The ngrok lines are only for your own ngrok testing. They no longer live in `settings.py`.

### A3. Give GitHub a clean history
Your old Git history contains an old database file with a customer's name, phone and
address, and an admin password hash. Deleting a file in a new commit does not remove it
from history. The simplest safe way is a new repository with a fresh history.

1. On GitHub, create a **new empty repository** (no README). Example: `tanda-shop`.
2. In your project folder (PowerShell):

```powershell
Remove-Item -Recurse -Force .git
git init -b main
git add .
git status
```

3. Check that none of these appear in the list: `db.sqlite3`, `.env`, `__pycache__`,
   `test-results.txt`. You should see the demo photos in `media/products/` and
   `catalog/fixtures/demo_catalog.json`.
4. Commit and push:

```powershell
git commit -m "Initial commit: Tanda store"
git remote add origin https://github.com/YOUR-NAME/tanda-shop.git
git push -u origin main
```

5. After the new repository works, **delete the old repository** on GitHub
   (Settings, then the Danger Zone at the bottom). Until then, make it Private.

The new repository can stay public. It contains no secrets and no customer data. A public
repository is the easiest way for PythonAnywhere to download it.

---

## Part B. On PythonAnywhere

### B1. Download the code
Dashboard, then **Consoles**, then **$ Bash**:

```bash
git clone https://github.com/YOUR-NAME/tanda-shop.git
cd tanda-shop
```

### B2. Create the virtual environment and install packages
Django 6.1 needs Python 3.12 or newer. Use the newest version PythonAnywhere offers:

```bash
mkvirtualenv tanda-venv --python=python3.13
pip install -r requirements.txt
```

If `python3.13` is not found, use `python3.12`. Use the same Python version in the Web tab.

### B3. Create the server `.env` file
First create a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(60))"
```

Copy the output. Then:

```bash
nano .env
```

Paste this, using your key and your real username (save with Ctrl+O, Enter, Ctrl+X):

```text
DJANGO_SECRET_KEY=PASTE-THE-LONG-KEY-HERE
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourusername.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com
DJANGO_MAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

The mail line only keeps Django's deployment check quiet. The shop sends no email.
Never put this file on GitHub. `.gitignore` already blocks it.

### B4. Create the database, admin user, demo products and static files

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata demo_catalog
python manage.py collectstatic --noinput
python manage.py check --deploy
```

- `loaddata demo_catalog` adds 15 demo products so the shop is not empty. Skip it if you
  want to add products yourself.
- `check --deploy` should show **no errors**. Two optional HSTS warnings are normal.

### B5. Create the web app
Open the **Web** tab, then **Add a new web app**:

1. Click Next. Choose **Manual configuration** (not "Django"), then your Python version
   (same as in B2), then Next.
2. **Virtualenv** section: enter `/home/yourusername/.virtualenvs/tanda-venv`
3. **Code** section: set **Source code** and **Working directory** to
   `/home/yourusername/tanda-shop`
4. Click the **WSGI configuration file** link. Delete everything in it and paste:

```python
import os
import sys

path = '/home/yourusername/tanda-shop'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

   Save the file.
5. **Static files** section, add two rows:

| URL | Directory |
|---|---|
| `/static/` | `/home/yourusername/tanda-shop/staticfiles` |
| `/media/` | `/home/yourusername/tanda-shop/media` |

6. Turn on **Force HTTPS** (optional; the project also redirects to HTTPS).
7. Click the green **Reload** button at the top.

### B6. Check the site
Open `https://yourusername.pythonanywhere.com` and check:

- The home page has styling and 12 product cards with photos.
- `/admin/` opens and you can log in with the superuser from B4.
- The WhatsApp and Messenger buttons open.

---

## Updating the site later

On your computer: change code, run `python manage.py test`, then `git add .`, `git commit`
and `git push`. On PythonAnywhere (Bash console):

```bash
cd ~/tanda-shop
git pull
workon tanda-venv
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** in the Web tab.

## Replacing the demo products with real ones
In `/admin/`, delete the demo products and add real ones with real photos, prices and
stock. Leave **rating** and **review count** empty unless you have real reviews. When
done, delete the demo photos from `media/products/` and change `.gitignore` to ignore all
of `media/`. Photos you upload in the admin are saved on the server.

## Backups (free tier has none)
Every few weeks, open the **Files** tab and download `tanda-shop/db.sqlite3` and the
`tanda-shop/media/` photos. Keep them private. Never commit them to Git.

## Troubleshooting
Always read the **Error log** link in the Web tab first.

| Problem | Likely cause and fix |
|---|---|
| `Bad Request (400)` | The address is missing from `DJANGO_ALLOWED_HOSTS` in the server `.env`. |
| `403 CSRF verification failed` on login | `DJANGO_CSRF_TRUSTED_ORIGINS` must start with `https://`. |
| Page has no styling | The `/static/` row in the Web tab is wrong, or `collectstatic` was not run. |
| Photos missing | The `/media/` row is wrong, or the photos are not in the `media` folder. |
| `ImproperlyConfigured: DJANGO_SECRET_KEY` | The `.env` file is missing or is not in `~/tanda-shop`. |
| Changes do not show | Click **Reload** in the Web tab. |
| Site disabled | Click **Run until 1 month from today** in the Web tab. |