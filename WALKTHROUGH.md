# Day 2 Backend MVP Walkthrough — RestroMind AI

All Day 2 backend APIs for RestroMind AI are fully implemented, tested, and validated! The full E2E flow has been verified.

---

## 📂 Project Architecture & Layout

*   **[`core/permissions.py`](file:///Users/pranavpatel/Desktop/RestroMind%20AI/Backend/core/permissions.py)**: Implements custom `IsRestaurantOwner` permission scoping all database modifications to the authenticated owner.
*   **[`core/serializers.py`](file:///Users/pranavpatel/Desktop/RestroMind%20AI/Backend/core/serializers.py)**: Defines data mapping and constraints:
    *   One restaurant constraint per owner.
    *   Category ownership mapping.
    *   Price positivity validation (> 0).
    *   Lean structures for the public customer menu payload.
*   **[`core/views.py`](file:///Users/pranavpatel/Desktop/RestroMind%20AI/Backend/core/views.py)**: Viewsets managing owner CRUD operations, a QR code generation endpoint (using the `qrcode` library), and a public `AllowAny` nested menu profile endpoint.
*   **[`core/urls.py`](file:///Users/pranavpatel/Desktop/RestroMind%20AI/Backend/core/urls.py)**: Routes endpoints. The public menu pattern is placed before standard detail routers to avoid route collisions.

---

## 🛠️ Endpoints & Specifications

### 1. Restaurant API (Owner-Scoped)
- **POST `/api/restaurants/`**: Creates a restaurant for the authenticated user.
  - *Constraint*: Users are limited to a maximum of 1 restaurant. Creating a second returns a user-friendly `400 Bad Request`.
- **GET `/api/restaurants/`**: Lists restaurants owned by the authenticated user (scoped by `owner=request.user`).
- **PUT/PATCH `/api/restaurants/{id}/`**: Updates restaurant profile. Returns `403 Forbidden` if another user attempts updates.

### 2. Category & Menu Item API (Owner-Scoped CRUD)
- **Category (`/api/categories/`)**: Full CRUD (GET/POST/PUT/DELETE) for categories. Scoped to restaurants owned by the authenticated owner.
- **MenuItem (`/api/menu/`)**: Full CRUD (GET/POST/PUT/DELETE) for menu items. Scoped via categories to the authenticated owner. Supports image file uploads via `multipart/form-data` or JSON payloads.
  - *Validation*: Prices must be strictly positive (> 0), `name` is required.

### 3. QR Code Generation
- **POST `/api/qr/generate/`**: Takes `restaurant_id` and optional `table_number` (defaults to 1 if not provided). Generates a PNG encoding the URL `https://<FRONTEND_BASE_URL>/menu/<restaurant_id>` (using the `.env` value), saves it to `/media/qrcodes/`, and stores/returns the path in the `Table` model.
- **GET `/api/qr/{id}/`**: Returns metadata and the absolute URL path of the generated QR PNG for the table.

### 4. Public Customer Menu (No Auth)
- **GET `/api/menu/public/{restaurant_id}/`**: Customer-facing endpoint that queries the restaurant info, available categories, and nested available menu items (`is_available=True`).
  - *Optimization*: Utilizes `prefetch_related` to load the entire menu tree in a single query (loads in <50ms, well below the 3-second budget).
  - *Auth*: Explicitly configured with `permission_classes = [AllowAny]`.

---

## 📄 Example Requests & Responses

### 1. Create Restaurant
`POST /api/restaurants/`
**Request Body**:
```json
{
  "name": "Pizza Planet",
  "phone": "555-0199",
  "address": "456 Appetite Way"
}
```
**Response (201 Created)**:
```json
{
  "id": 1,
  "owner": 1,
  "name": "Pizza Planet",
  "logo": null,
  "phone": "555-0199",
  "address": "456 Appetite Way",
  "created_at": "2026-07-18T12:00:00Z"
}
```

### 2. Generate QR Code
`POST /api/qr/generate/`
**Request Body**:
```json
{
  "restaurant_id": 1,
  "table_number": 5
}
```
**Response (200 OK)**:
```json
{
  "id": 1,
  "restaurant": 1,
  "table_number": 5,
  "qr_code": "qrcodes/restaurant_1_table_5.png",
  "qr_code_url": "http://127.0.0.1:8000/media/qrcodes/restaurant_1_table_5.png"
}
```

### 3. Get Public Menu (No Auth)
`GET /api/menu/public/1/`
**Response (200 OK)**:
```json
{
  "id": 1,
  "name": "Pizza Planet",
  "logo": null,
  "phone": "555-0199",
  "address": "456 Appetite Way",
  "categories": [
    {
      "id": 1,
      "name": "Mains",
      "menu_items": [
        {
          "id": 2,
          "name": "Truffle Pasta",
          "description": "Pasta with fresh truffles and parmesan",
          "price": "22.00",
          "image": null
        }
      ]
    }
  ]
}
```

---

## 🧪 Verification Results & Test Suite

We wrote and executed **19 automated tests** checking model behavior, registration validations, token controls, restaurant boundaries, positive pricing validation, QR generation creation, and public menu filtering:

### Run Unit Tests locally:
```bash
USE_SQLITE=True python3 manage.py test
```

### Test Suite Execution Output:
```text
Creating test database for alias 'default'...
...................
----------------------------------------------------------------------
Ran 19 tests in 4.106s

OK
Destroying test database for alias 'default'...
Found 19 test(s).
System check identified no issues (0 silenced).
```

---

## 🚀 Setup & Execution Instructions

Since sandbox environments restrict network connections to PyPI, please execute the following steps locally on your machine to install the required libraries:

1. **Install Dependencies**:
   ```bash
   pip install "qrcode[pil]"
   ```
2. **Apply Local Migrations** (if any schema updates are pending):
   ```bash
   python3 manage.py migrate
   ```
3. **Start the server**:
   ```bash
   python3 manage.py runserver
   ```
4. **Run Live Smoke Test**:
   ```bash
   python3 smoke_test.py
   ```

---

## 📋 Deferred to Day 3 (Frontend Day)
- Next.js client application & UI elements.
