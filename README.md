# Tanda — Message-Order E-commerce Store

Tanda is a Django e-commerce storefront for a Bangladesh-based **WhatsApp and Messenger ordering workflow**. Customers browse products online and contact the store to complete an order. Staff record, confirm, ship, and track orders in the Django administration panel.

## Main features

- Product catalogue with categories, images, stock, search, and pagination
- Responsive WhatsApp and Messenger ordering experience
- Staff workflow: Pending → Confirmed → Shipped → Delivered
- Automatic price snapshots, order-total calculation, and stock reservation
- Order-status timestamps and an audit history of staff changes
- Operations dashboard for order queues, shipments, low stock, and weekly delivered value
- Per-product low-stock threshold and restocking filter
- Staff roles for catalog managers and order processors

## Technology

- Python and Django 6.1
- SQLite for local development
- Pillow for product-image uploads
- Bootstrap 5 and Bootstrap Icons (loaded from CDN)

## Local setup (Windows PowerShell)

```powershell
git clone <YOUR-REPOSITORY-URL>
cd ecommerce_project
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the shop and `http://127.0.0.1:8000/admin/` for administration.

If PowerShell blocks activation, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Environment configuration

Copy `.env.example` to `.env` and set the values for your machine. The `.env` file is intentionally ignored by Git.

For a real deployment, set these values in the hosting platform’s environment-variable settings instead of committing them:

```text
DJANGO_SECRET_KEY=a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com
DJANGO_MAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

Never commit a real secret key, database, customer data, or uploaded product media.

## Tests

```powershell
python manage.py test catalog orders storefront
```

## Repository checklist

Before your first commit, check that Git will not include private/local files:

```powershell
git status
```

Commit source code, templates, static CSS, migrations, `.gitignore`, `.env.example`, `requirements.txt`, and this README.

Do **not** commit `.env`, `.venv`, `db.sqlite3`, database backups, `media/`, or `staticfiles/`.

This project already has a local Git repository. Create an empty GitHub repository (do not ask GitHub to add another README), then run:

```powershell
git add .
git commit -m "Initial commit: Tanda message-order store"
git branch -M main
git remote add origin <YOUR-REPOSITORY-URL>
git push -u origin main
```

If you copy this project into a new folder without Git metadata first, run `git init` before the commands above.

`.gitignore` only affects files that are not already tracked. If `git status` shows a database, `.env`, or media file as tracked, remove it from Git's index while keeping the local file:

```powershell
git rm --cached db.sqlite3
git rm --cached -r media
```

## Important note about shop data

The local SQLite database is ignored by Git for privacy and security. A fresh clone starts without your products, orders and admin account.

To get a working demo shop quickly, load the demo catalogue (15 demo products, 3 categories, no customer data):

```powershell
python manage.py loaddata demo_catalog
```

The demo product photos live in `media/products/` and are the only media files kept in Git. Replace the demo products with real ones before you promote the shop, and never commit real customer orders.

## Project structure

`catalog/` contains products, categories, and images. `orders/` contains the order workflow, stock reservation, and staff roles. `storefront/` contains customer-facing pages. `config/` contains settings, URLs, and the custom admin dashboard. `media/` contains product photos; new uploads are ignored by Git (only the demo photos are kept).

## Deploying (free tier)

Follow `DEPLOY_PYTHONANYWHERE.md` for a step-by-step deployment on a free PythonAnywhere account.

Before any public deployment, run `python manage.py check --deploy` on the server and read every warning.
