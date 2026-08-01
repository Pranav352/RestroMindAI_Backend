# RestroMind AI - Backend

The backend service for RestroMind AI — a full-featured REST API for restaurant management, hierarchical digital menus, QR code generation, order lifecycle management, subscription enforcement, and multi-tenant admin tooling.

## 🚀 Tech Stack

| Library | Version / Role |
|---------|---------------|
| **Django** | 5.2 — Web framework |
| **Django REST Framework** | DRF — REST API layer |
| **PostgreSQL** | Primary database (`psycopg2-binary`) |
| **djangorestframework-simplejwt** | JWT Authentication + Token Blacklisting |
| **Pillow** | Image processing (logo & menu item uploads) |
| **qrcode[pil]** | QR code PNG generation for table-specific URLs |
| **django-cors-headers** | CORS management (configurable via `.env`) |
| **python-dotenv** | Environment variable loading |

---

## 📋 Prerequisites

- Python 3.10+
- PostgreSQL 14+
- pip

---

## 🛠️ Local Setup

1. **Navigate to the backend directory**
   ```bash
   cd "RestroMind AI/Backend"
   ```

2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install "qrcode[pil]" psycopg2-binary
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your PostgreSQL credentials, `SECRET_KEY`, and `FRONTEND_BASE_URL`.

5. **Run database migrations**
   ```bash
   python3 manage.py migrate
   ```

6. **Create a superuser (admin account)**
   ```bash
   python3 manage.py createsuperuser
   ```

7. **Start the development server**
   ```bash
   python3 manage.py runserver
   ```
   The API will be available at **`http://127.0.0.1:8000/`**.

---

## 📡 API Endpoints

### Authentication (`/api/auth/`)
- `POST /api/auth/register/` — Register a user (owner/customer). Owners get a `pending` subscription auto-created.
- `POST /api/auth/login/` — JWT login (rate-limited: 5/min default).
- `POST /api/auth/token/refresh/` — Refresh access token.
- `POST /api/auth/logout/` — Blacklist refresh token.
- `GET /api/auth/me/` — Current user profile + subscription info.

### Restaurant Management (`/api/restaurants/`)
- Owner-scoped CRUD. Constraint: **1 restaurant per owner**.
- Supports logo image upload, currency selection (₹/$/€/£).

### Menu Management (requires `X-Tenant-ID` header)
- `GET/POST /api/categories/` — Manage categories. Pass `parent` field for sub-categories.
- `GET/POST /api/menu/` — Manage menu items with image uploads and availability toggle.
- Requires active subscription for write operations (`HasActiveSubscription`).

### QR Code (`/api/qr/`)
- `POST /api/qr/generate/` — Generate a table-specific QR code PNG.
- `GET /api/qr/{id}/` — Retrieve table + QR code URL.

### Orders (`/api/orders/`)
- `POST /api/orders/` — Public: place an order (returns `tracking_token`).
- `GET /api/orders/` — Owner: list all orders (tenant-scoped).
- `GET /api/orders/status/?token=<uuid>` — Public: track order by token.
- `POST /api/orders/cancel/` — Public: cancel a `pending` order by token.
- `PATCH /api/orders/{id}/` — Owner: update order status.

### Public Menu (`/api/menu/public/`)
- `GET /api/menu/public/{restaurant_id}/` — No auth. Returns full nested menu tree (top categories → subcategories → available items). Optimized with `prefetch_related`.

### Admin Endpoints
- `GET /api/admin/stats/` — Platform stats (users, restaurants, pending approvals, recent signups).
- `GET/PATCH/DELETE /api/admin/users/` — User management with pagination, search, status filter. PATCH supports nested subscription approval.
- `GET/DELETE /api/admin/restaurants/` — Restaurant management with search and pagination.
- `GET /api/owner/stats/` — Owner dashboard stats (today's orders/revenue, recent orders).

---

## 🔐 Permission Architecture

| Class | File | Purpose |
|-------|------|---------|
| `IsRestaurantOwner` | `core/permissions.py` | Object-level: only the owner can modify their resources |
| `IsSystemAdmin` | `core/permissions.py` | View-level: admin/superuser only |
| `HasTenantAccess` | `core/permissions.py` | Validates `X-Tenant-ID` header; sets `request.tenant_id` |
| `HasActiveSubscription` | `users/permissions.py` | Blocks writes for inactive subscriptions; reads always allowed |

---

## 🗄️ Data Models

| Model | App | Description |
|-------|-----|-------------|
| `User` | `users` | Email-auth, roles: `customer` / `owner` / `admin` |
| `Subscription` | `users` | Free-trial tracking per owner (pending → active → expired) |
| `Restaurant` | `core` | Owner's restaurant (name, logo, phone, address, currency) |
| `Category` | `core` | Hierarchical (self-referential `parent` FK for sub-categories) |
| `MenuItem` | `core` | Dish/drink (price, image, is_available) |
| `Table` | `core` | Physical table + generated QR code path |
| `Order` | `core` | Customer order with status lifecycle + UUID tracking token |
| `OrderItem` | `core` | Line item in an order (price snapshot at order-time) |

---

## 🧪 Testing

### Unit Tests (SQLite in-memory)
```bash
USE_SQLITE=True python3 manage.py test
```

### Live Smoke Test (requires running server)
```bash
python3 smoke_test.py
```

Test suite covers: user registration, role validation, JWT auth, restaurant constraint (1 per owner), category/item CRUD, pricing validation, QR generation, public menu filtering, and subscription enforcement.
