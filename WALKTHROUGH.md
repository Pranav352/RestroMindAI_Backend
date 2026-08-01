# RestroMind AI — Full Stack Walkthrough

A comprehensive walkthrough of everything implemented in the RestroMind AI platform — backend APIs, frontend pages, and all the features built today.

---

## 📂 Project Architecture

```
RestroMind AI/
├── Backend/
│   ├── core/               # Restaurant, Category (hierarchical), MenuItem, Table, Order, OrderItem
│   │   ├── models.py       # ORM models with self-referential Category, UUID tracking on Order
│   │   ├── serializers.py  # Public, owner, and admin serializers; nested sub-category support
│   │   ├── views.py        # All ViewSets + QR generator + stats + order management
│   │   ├── urls.py         # Router + manual URL patterns (public menu before detail routes)
│   │   └── permissions.py  # IsRestaurantOwner, IsSystemAdmin, HasTenantAccess
│   └── users/
│       ├── models.py       # Custom User (email auth) + Subscription model + auto-create signal
│       ├── serializers.py  # Register, User serializers
│       ├── views.py        # Register, Login, Logout, MeView, MockUpgradeView
│       └── permissions.py  # HasActiveSubscription
└── frontend/
    └── src/
        ├── api/            # Axios modules: api.js (interceptors), auth, menu, admin, orders, qr, restaurant
        ├── components/     # AdminRoute, ProtectedRoute, ConfirmDialog, ErrorBoundary, menu/ components
        ├── context/        # AuthContext: user state, JWT, activeTenantId (multi-tenant)
        ├── hooks/          # useRestaurant, useMenuData (data fetching + state)
        ├── layouts/        # AppLayout: sidebar, mobile nav, admin impersonation banner
        └── pages/          # All 11 route-level pages
```

---

## 🛠️ Backend — Implemented Features

### 1. Authentication System (`/api/auth/`)
- Custom `User` model (email-only, no username) with `role` field: `customer` / `owner` / `admin`.
- **Register** (`POST /api/auth/register/`): Creates user + auto-creates a `pending` Subscription for owner accounts (via Django signal).
- **Login** (`POST /api/auth/login/`): Returns `access` + `refresh` JWT tokens. Rate-limited to `AUTH_THROTTLE_RATE` (default: 5/minute).
- **Logout** (`POST /api/auth/logout/`): Blacklists the refresh token using simplejwt blacklist app.
- **Me** (`GET /api/auth/me/`): Returns user profile including nested `subscription` data.
- **Token Refresh** (`POST /api/auth/token/refresh/`): Returns new access token.

### 2. Subscription System
- `Subscription` model: `plan` (free_trial/premium), `status` (pending/active/expired/stopped), `start_date`, `end_date`.
- **Signal**: When an owner registers, a `Subscription` is created with `status='pending'` (in production) or `status='active'` (in test mode).
- **`HasActiveSubscription` permission**: Blocks all write operations (POST/PUT/PATCH/DELETE) if subscription is not active. GET requests always allowed.
- **Admin Approval**: Admin patches `subscription.status` to `active` → system auto-sets `start_date=now()` and `end_date=now()+30 days`.

### 3. Multi-Tenant Architecture
- `HasTenantAccess` permission reads the `X-Tenant-ID` request header.
- Validates the header value matches a restaurant the user owns (or is admin).
- Sets `request.tenant_id` for use in queryset scoping across all views.
- All category, menu item, table, and order queries filter by `request.tenant_id`.
- Admin users can set any `X-Tenant-ID` to impersonate and view any restaurant's data.

### 4. Restaurant Management (`/api/restaurants/`)
- Full CRUD ViewSet, scoped to `owner=request.user`.
- **Constraint**: Serializer rejects creating a second restaurant per owner.
- Supports: `name`, `phone`, `address`, `logo` (image, 5MB limit, JPEG/PNG/WEBP/GIF), `currency` (₹/$/ €/£).

### 5. Hierarchical Categories (`/api/categories/`)
- `Category` model with `parent` (self-referential FK, nullable) for two-level nesting.
- Top-level categories have `parent=null`; sub-categories reference a parent.
- `CategorySerializer` recursively serializes `subcategories` (nested children).
- `PublicCategorySerializer` used in the public menu endpoint returns `menu_items` (available only) + `subcategories` nested.
- The `PublicRestaurantSerializer` filters only `parent__isnull=True` top-level categories to avoid duplication.

### 6. Menu Items (`/api/menu/`)
- Full CRUD ViewSet with `MultiPartParser` for image uploads.
- Image validation: max 5MB, allowed types: JPEG, PNG, WEBP, GIF.
- Price validation: must be strictly > 0.
- `is_available` boolean toggle (owners update per item).

### 7. QR Code Generation (`/api/qr/generate/`)
- Accepts `restaurant_id` and `table_number`.
- Generates a PNG QR code linking to `{FRONTEND_BASE_URL}/menu/{restaurantId}?table={tableNumber}`.
- Saves PNG to `media/qrcodes/restaurant_{id}_table_{n}.png`.
- Creates or updates the `Table` record and returns its `qr_code_url` (absolute URL).

### 8. Public Digital Menu (`/api/menu/public/{restaurant_id}/`)
- `AllowAny` permission — no authentication required.
- Uses `prefetch_related('categories', 'categories__menu_items')` for a single-query load.
- Returns nested structure: restaurant → top-level categories → sub-categories → available items only.

### 9. Order System (`/api/orders/`)
- **Place Order** (public): Accepts `restaurant`, `table_number`, `customer_name`, `items` array. Auto-creates `Table` if not exists. Calculates `total_price` from item prices at order-time. Returns `tracking_token` (UUID).
- **Track Order** (public): `GET /api/orders/status/?token=<uuid>`.
- **Cancel Order** (public): `POST /api/orders/cancel/` — only works on `pending` status.
- **List Orders** (owner): Tenant-scoped list of all restaurant orders.
- **Update Status** (owner): PATCH to advance order through lifecycle.

### 10. Admin API
- **`AdminUserViewSet`**: Paginated (`AdminPagination`, configurable via `ADMIN_PAGINATION_PAGE_SIZE`), searchable by email, filterable by `subscription.status`. Supports PATCH (user + nested subscription) and DELETE (removes user + cascade).
- **`AdminRestaurantViewSet`**: Paginated, searchable by name/owner email. Supports DELETE.
- **`AdminDashboardStatsView`**: Platform totals, 7-day growth, subscription breakdown, recent 5 signups.
- **`OwnerDashboardStatsView`**: Tenant-scoped: category/item/table counts, today's orders, pending count, today's revenue (sum of `served`/`completed` orders), 5 most recent orders.

---

## 💻 Frontend — Implemented Features

### Authentication & Routing
- `AuthContext`: Manages `user`, `loading`, `isAuthenticated`, `activeTenantId` (localStorage-persisted), `login`, `logout`, `refreshUser`.
- Axios interceptor in `api.js`: Automatically attaches `Authorization: Bearer <token>` and `X-Tenant-ID: <activeTenantId>` to every request.
- `ProtectedRoute`: Redirects unauthenticated users to `/login`.
- `AdminRoute`: Redirects non-admin users.
- Routes: `/login`, `/signup`, `/menu/:restaurantId` (public), `/dashboard`, `/profile`, `/menu`, `/qr`, `/orders`, `/admin/users`, `/admin/restaurants`.

### AppLayout
- Dark sidebar navigation (`bg-[#161720]`) with amber gradient branding.
- Role-aware nav: owners see Dashboard/Orders/Profile/Menu/QR; admins see Dashboard/Manage Users/Manage Restaurants.
- Mobile hamburger menu with overlay drawer.
- **Impersonation Banner**: When `activeTenantId` is set for an admin, shows a persistent amber top bar with restaurant ID and "Exit Impersonation" button.

### Owner Dashboard (`DashboardPage.jsx`)
- Fetches `/api/owner/stats/` via `X-Tenant-ID`.
- Shows: subscription status badge, today's revenue, today's orders, pending orders alert (with link to orders page), recent orders table.
- Handles `has_restaurant: false` state gracefully.

### Menu Management (`MenuManagementPage.jsx`)
- Uses custom hooks `useRestaurant` and `useMenuData`.
- **Add Category form**: Creates top-level categories.
- **Add Sub-Category**: Via "Add Sub" button on top-level `CategorySection` cards; sends `parent` field to API.
- **`CategorySection` component**: 
  - Collapsible/expandable via chevron icon click (only for categories with sub-categories).
  - Displays item count badge and sub-folder count badge.
  - Context menu (⋮) for Rename and Delete actions.
  - Inline rename form with Save/Cancel.
  - "Add Sub" button visible only for top-level (`isTopLevel=true`) categories.
- **`MenuItemModal`**: Add/Edit modal with image upload preview, category selector, price, description, availability toggle.
- **`ConfirmDialog`**: Used for delete category and delete menu item confirmations.
- Subscription expiry warning banner for inactive owners.

### Admin Users Page (`AdminUsersPage.jsx`)
- Paginated table of all users.
- Search by email (debounced 400ms).
- Filter by subscription status (`pending`, `active`, `expired`, `stopped`) via URL param (`?status=`).
- Per-row actions dropdown:
  - **Approve Subscription** → PATCH `subscription.status: 'active'`
  - **Stop Subscription** → PATCH `subscription.status: 'stopped'`
  - **Activate Account** / **Deactivate Account** → PATCH `is_active`
  - **Delete User** → DELETE with `ConfirmDialog` confirmation
- `ConfirmDialog` imported from shared components.

### Admin Restaurants Page (`AdminRestaurantsPage.jsx`)
- Paginated restaurant list with search.
- Delete restaurant action with `ConfirmDialog`.

### Public Digital Menu (`PublicMenuPage.jsx`)
- Fetches `/api/menu/public/{restaurantId}/` (no auth).
- Renders restaurant name/logo/currency.
- Collapsible top-level categories; nested sub-categories shown as tabs or sections.
- Cart state management; order placement via `POST /api/orders/`.
- Displays `tracking_token` after successful order.

### QR Code Page (`QRCodePage.jsx`)
- Table number input → POST to `/api/qr/generate/`.
- Renders QR image from response `qr_code_url`.
- Download QR PNG button.

### Orders Page (`OrdersPage.jsx`)
- Fetches orders for active restaurant.
- Status update buttons per order (advancing through lifecycle).

### Reusable Components
- **`ConfirmDialog`**: Modal with title, message, confirm/cancel buttons. `isDanger` prop renders red confirm button.
- **`ErrorBoundary`**: Catches render errors, shows friendly fallback UI.
- **`MenuItemCard`**: Item card with image, name, price, availability toggle, edit/delete (3-dot menu).
- **`MenuItemModal`**: Full add/edit modal form.

---

## 🧪 Test Suite

- **19+ automated tests** in `core/tests.py` and `users/tests.py`.
- Tests use SQLite in-memory database (`USE_SQLITE=True`).
- Coverage: registration, role assignment, JWT flow, restaurant limit constraint, category ownership, price validation, QR generation, public menu availability filtering, subscription blocking.

```bash
USE_SQLITE=True python3 manage.py test
```

---

## 📋 Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `DB_NAME` | `restromind_ai_db` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | (required) | PostgreSQL password |
| `DB_HOST` | `localhost` | DB host |
| `DB_PORT` | `5432` | DB port |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | Used in QR code URL generation |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `AUTH_THROTTLE_RATE` | `5/minute` | Rate limit for auth endpoints |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `15` | Access token expiry |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` | Refresh token expiry |
| `ADMIN_PAGINATION_PAGE_SIZE` | `10` | Items per page in admin lists |
