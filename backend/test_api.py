import requests
import json
import sys
# Set standard output to UTF-8 to prevent Windows UnicodeEncodeError on emojis
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
BASE_URL = "http://localhost:8000/api"
def safe_print(title, content):
    # Safe printing of content that might contain emojis on Windows command line
    try:
        print(f"{title}\n{content}")
    except UnicodeEncodeError:
        ascii_content = str(content).encode('ascii', 'ignore').decode('ascii')
        print(f"{title}\n{ascii_content} (stripped emojis)")
def test_backend():
    print("--- 1. Testing HCP search ---")
    try:
      r = requests.get(f"{BASE_URL}/hcps")
      if r.status_code == 200:
          hcps = r.json()
          print(f"HCPs in database ({len(hcps)}):")
          for h in hcps:
              print(f"  - ID {h['id']}: {h['name']} ({h['specialty']})")
      else:
          print("Failed to get HCPs:", r.text)
    except Exception as e:
      print("Error connecting to backend:", e)
      return
    print("\n--- 2. Testing search HCP endpoint ---")
    r = requests.get(f"{BASE_URL}/hcps/search", params={"query": "Sarah"})
    print("Search results for 'Sarah':", r.json())
    print("\n--- 3. Testing compliance check ---")
    r = requests.post(f"{BASE_URL}/compliance", json={
        "topics_discussed": "Discussed off-label use of Prodo-X and promised cancer cure",
        "materials_shared": ["Internal-Draft presentation"]
    })
    safe_print("Compliance report for off-label discussion:", json.dumps(r.json(), indent=2))
    print("\n--- 4. Testing AI Assistant Chat (LangGraph agent) ---")
    print("Sending natural language interaction log...")
    payload = {
        "message": "Log a call with Dr. Sarah Jenkins today, discussed Prodo-X efficacy, sentiment was positive, and I shared a brochure",
        "history": [],
        "current_form": {}
    }
    r = requests.post(f"{BASE_URL}/chat", json=payload)
    if r.status_code == 200:
        data = r.json()
        safe_print("Assistant Reply:", data["reply"])
        safe_print("\nUpdated Form State:", json.dumps(data["updated_form"], indent=2))
        safe_print("\nTools Executed:", data["tools_executed"])
        safe_print("\nCompliance Report:", json.dumps(data["compliance_report"], indent=2))
    else:
        print("FastAPI chat endpoint error:", r.text)
    print("\n--- 5. Testing history query ---")
    r = requests.get(f"{BASE_URL}/interactions")
    print(f"Total interactions in database: {len(r.json())}")
if __name__ == "__main__":
    test_backend()