import requests

# 1. Login to get token
resp = requests.post(
    "http://localhost:8000/api/v1/auth/institution/login",
    data={"username": "nuuralislam@example.com", "password": "Inst@2025!"},
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)
print("Login status:", resp.status_code)
if resp.status_code == 200:
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Fetch students
    r = requests.get("http://localhost:8000/api/v1/students/", headers=headers)
    print("Students length:", len(r.text))
    print(r.text[:200])
    
    # 3. Fetch me
    r = requests.get("http://localhost:8000/api/v1/institutions/me", headers=headers)
    print("Institution me length:", len(r.text))
    print(r.text[:200])

