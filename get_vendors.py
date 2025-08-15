import requests

# === CONFIG ===
API_URL = "https://api.payday.is/accounting/creditors?balance=false"
API_TOKEN ="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb21wYW55SWQiOiI1MjE0NmEwZi05ZDc5LTQ2MzctYmEzYS00OGEzMGJjNWY3NmIiLCJ1c2VySWQiOiJhZmUwMTQ3My1lNmUwLTQ5YjEtODY1Mi00OTJlMmEzMTg0ZjMiLCJjdWx0dXJlIjoiaXMiLCJzY29wZSI6InJlYWRfY29tcGFueSByZWFkX3VzZXJzIHJlYWRfY3VzdG9tZXJzIHdyaXRlX2N1c3RvbWVycyByZWFkX2ludm9pY2VzIHdyaXRlX2ludm9pY2VzIHJlYWRfcmVjdXJyaW5nX2ludm9pY2VzIHdyaXRlX3JlY3VycmluZ19pbnZvaWNlcyByZWFkX3Byb2R1Y3RzIHdyaXRlX3Byb2R1Y3RzIHJlYWRfc2FsZXNfb3JkZXJzIHdyaXRlX3NhbGVzX29yZGVycyByZWFkX2FjY291bnRpbmcgd3JpdGVfYWNjb3VudGluZyByZWFkX2V4cGVuc2VzIHdyaXRlX2V4cGVuc2VzIHJlYWRfcGF5cm9sbCB3cml0ZV9wYXlyb2xsIHJlYWRfZXN0aW1hdGVzIHdyaXRlX2VzdGltYXRlcyIsIm5iZiI6MTc1NDY4ODg2MSwiZXhwIjoxNzU0Nzc1MjYxLCJpYXQiOjE3NTQ2ODg4NjF9.45thTxWL3v01YBjgYAqPmhA0Rrv9KiGggGHdKYyfEeE"  # Replace with real token

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Api-Version": "alpha"
}

def get_vendors():
    response = requests.get(API_URL, headers=HEADERS)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    vendors = get_vendors()
    for v in vendors:
        print(f"{v['id']} | {v['ssn']} | {v['name']}")
