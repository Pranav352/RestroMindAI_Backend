# RestroMind AI - Backend

The backend service for RestroMind AI, providing the core API for restaurant management, digital menus, QR code generation, and user authentication with subscription handling.

## 🚀 Tech Stack

- **Framework**: Django 5.2 & Django REST Framework
- **Database**: PostgreSQL (via `psycopg2-binary`)
- **Authentication**: JWT (JSON Web Tokens) via `djangorestframework-simplejwt`
- **Other Key Libraries**: 
  - `Pillow` & `qrcode` for QR code generation
  - `django-cors-headers` for CORS management
  - `python-dotenv` for environment variable management

## 📋 Prerequisites

- Python 3.10+
- PostgreSQL
- pip (Python package installer)

## 🛠️ Local Setup & Installation

Follow these steps to set up the backend locally:

1. **Clone the repository and navigate to the backend directory**
   ```bash
   cd "RestroMind AI/Backend"
   ```

2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   - Copy the example environment file to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Open `.env` and configure your database credentials, secret key, and other settings.

5. **Set up the Database**
   Ensure your PostgreSQL server is running and the database specified in `.env` (e.g., `restromind_ai_db`) is created.

6. **Run Database Migrations**
   ```bash
   python manage.py migrate
   ```

7. **Start the Development Server**
   ```bash
   python manage.py runserver
   ```
   The server will run at `http://127.0.0.1:8000/`.

## 📡 Core API Endpoints

The API is structured around several key domains:

- **Authentication & Users** (`/api/users/`): JWT-based login, registration, and profile management. Includes trial and subscription tracking.
- **Restaurants** (`/api/restaurants/`): Owner-scoped creation and management of a restaurant profile (1 per owner).
- **Categories & Menu** (`/api/categories/`, `/api/menu/`): Full CRUD for menu items and categories, securely scoped to the authenticated owner.
- **QR Codes** (`/api/qr/generate/`): Generate QR codes for specific tables pointing to the public menu.
- **Public Menu** (`/api/menu/public/<restaurant_id>/`): Unauthenticated, optimized endpoint for customers to view the restaurant's menu.

## 🧪 Testing

To run the automated test suite (which uses a temporary SQLite database by default if configured with `USE_SQLITE=True`):

```bash
USE_SQLITE=True python manage.py test
```

Or run the live smoke test script to verify end-to-end functionality:
```bash
python smoke_test.py
```
