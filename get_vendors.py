import requests

# === CONFIG ===
API_URL = "https://api.payday.is/accounting/creditors?balance=false"
API_TOKEN = "your_token_here"  # Replace with real token

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
