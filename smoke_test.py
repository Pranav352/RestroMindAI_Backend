import json
import urllib.request
import urllib.error
import sys
import uuid

BASE_URL = "http://127.0.0.1:8000"

def make_request(url, method="GET", data=None, token=None, content_type="application/json"):
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    if data is not None:
        if content_type == "application/json":
            req_data = json.dumps(data).encode("utf-8")
        else:
            req_data = data  # Raw bytes for multipart or forms
    else:
        req_data = None

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            resp_data = json.loads(body) if body else {}
            return response.status, resp_data
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            err_body = json.loads(body) if body else {}
        except Exception:
            err_body = {"detail": e.reason}
        return e.code, err_body
    except urllib.error.URLError as e:
        print(f"\n[ERROR] Could not connect to dev server at {BASE_URL}.")
        print("Please ensure the development server is running: python3 manage.py runserver\n")
        sys.exit(1)

def run_smoke_test():
    print("=" * 70)
    print("STARTING RESTROMIND AI END-TO-END SMOKE TESTS")
    print("=" * 70)

    # Generate a unique email prefix to run the tests cleanly multiple times
    uid = uuid.uuid4().hex[:6]
    email = f"owner_{uid}@restromind.com"
    password = "securepassword123"

    # 1. Register User
    print(f"\n1. Testing POST /api/auth/register/ for {email}...")
    register_payload = {
        "email": email,
        "password": password,
        "role": "owner"
    }
    status, response = make_request(f"{BASE_URL}/api/auth/register/", "POST", register_payload)
    if status == 201:
        print(f"   [SUCCESS] Registered owner: {email} (Status: {status})")
    else:
        print(f"   [FAILED] Registration failed: Status {status}, Response: {response}")
        sys.exit(1)

    # 2. Login User
    print("\n2. Testing POST /api/auth/login/...")
    login_payload = {
        "email": email,
        "password": password
    }
    status, response = make_request(f"{BASE_URL}/api/auth/login/", "POST", login_payload)
    if status == 200:
        print("   [SUCCESS] Logged in successfully!")
        access_token = response.get("access")
        refresh_token = response.get("refresh")
        if access_token and refresh_token:
            print("   [SUCCESS] Received access and refresh JWT tokens.")
        else:
            print("   [FAILED] Access or refresh token missing from login response.")
            sys.exit(1)
    else:
        print(f"   [FAILED] Login failed: Status {status}, Response: {response}")
        sys.exit(1)

    # 3. Create Restaurant
    print("\n3. Testing POST /api/restaurants/...")
    restaurant_payload = {
        "name": f"Gourmet Bistro {uid}",
        "phone": "555-0199",
        "address": "456 Appetite Way"
    }
    status, response = make_request(f"{BASE_URL}/api/restaurants/", "POST", restaurant_payload, token=access_token)
    if status == 201:
        restaurant_id = response.get("id")
        print(f"   [SUCCESS] Created restaurant '{response.get('name')}' with ID: {restaurant_id}")
    else:
        print(f"   [FAILED] Restaurant creation failed: Status {status}, Response: {response}")
        sys.exit(1)

    # 4. Enforce One Restaurant Limit
    print("\n4. Testing duplicate Restaurant check (expecting 400)...")
    status, response = make_request(f"{BASE_URL}/api/restaurants/", "POST", restaurant_payload, token=access_token)
    if status == 400:
        print(f"   [SUCCESS] Duplicate restaurant correctly blocked (Status: {status}, Response: {response})")
    else:
        print(f"   [FAILED] Allowed creating a duplicate restaurant! Status: {status}")
        sys.exit(1)

    # 5. Create 2 Categories
    print("\n5. Testing POST /api/categories/ for 2 categories...")
    categories = ["Starters", "Mains"]
    category_ids = []
    for cat_name in categories:
        cat_payload = {
            "restaurant": restaurant_id,
            "name": cat_name
        }
        status, response = make_request(f"{BASE_URL}/api/categories/", "POST", cat_payload, token=access_token)
        if status == 201:
            cat_id = response.get("id")
            category_ids.append(cat_id)
            print(f"   [SUCCESS] Created category '{cat_name}' with ID: {cat_id}")
        else:
            print(f"   [FAILED] Category creation failed for '{cat_name}': Status {status}, Response: {response}")
            sys.exit(1)

    # 6. Create 3 Menu Items
    print("\n6. Testing POST /api/menu/ for 3 items...")
    menu_items = [
        {"category": category_ids[0], "name": "Bruschetta", "price": 8.50, "is_available": True},
        {"category": category_ids[1], "name": "Truffle Pasta", "price": 22.00, "is_available": True},
        {"category": category_ids[1], "name": "Filet Mignon (Sold Out)", "price": 38.00, "is_available": False}
    ]
    
    for item in menu_items:
        status, response = make_request(f"{BASE_URL}/api/menu/", "POST", item, token=access_token)
        if status == 201:
            print(f"   [SUCCESS] Created item '{item['name']}' at price {item['price']} (Available: {item['is_available']})")
        else:
            print(f"   [FAILED] Item creation failed for '{item['name']}': Status {status}, Response: {response}")
            sys.exit(1)

    # 7. Generate QR Code
    print("\n7. Testing POST /api/qr/generate/...")
    qr_payload = {
        "restaurant_id": restaurant_id,
        "table_number": 5
    }
    status, response = make_request(f"{BASE_URL}/api/qr/generate/", "POST", qr_payload, token=access_token)
    if status == 200:
        print(f"   [SUCCESS] Generated QR code for Restaurant {restaurant_id}, Table {response.get('table_number')}")
        print(f"             Database QR path: {response.get('qr_code')}")
        print(f"             QR absolute URL: {response.get('qr_code_url')}")
    else:
        print(f"   [FAILED] QR Code generation failed: Status {status}, Response: {response}")
        sys.exit(1)

    # 8. Access Public Menu WITHOUT token (No Auth)
    print("\n8. Testing GET /api/menu/public/{restaurant_id}/ (unauthenticated)...")
    status, response = make_request(f"{BASE_URL}/api/menu/public/{restaurant_id}/", "GET")
    if status == 200:
        print(f"   [SUCCESS] Successfully retrieved public menu for '{response.get('name')}'")
        cats = response.get("categories", [])
        print(f"             Returned {len(cats)} categories.")
        
        # Verify Truffle Pasta is available, and Filet Mignon is filtered out
        for c in cats:
            items = c.get("menu_items", [])
            print(f"             Category '{c.get('name')}': {len(items)} items returned.")
            for it in items:
                print(f"               - {it.get('name')} (${it.get('price')})")
                if "Sold Out" in it.get("name"):
                    print("   [FAILED] Returned an unavailable menu item in the public endpoint!")
                    sys.exit(1)
    else:
        print(f"   [FAILED] Public menu request failed: Status {status}, Response: {response}")
        sys.exit(1)

    # 9. Logout
    print("\n9. Testing POST /api/auth/logout/ (token blacklisting)...")
    logout_payload = {"refresh": refresh_token}
    status, response = make_request(f"{BASE_URL}/api/auth/logout/", "POST", logout_payload, token=access_token)
    if status == 205:
        print(f"   [SUCCESS] Refresh token blacklisted and logged out.")
    else:
        print(f"   [FAILED] Logout failed: Status {status}, Response: {response}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("ALL DAY 2 END-TO-END SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_smoke_test()

