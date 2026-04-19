"""
Test Groq API Connection
"""
import requests
import json

GROQ_API_KEY = "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"
GROQ_MODEL = "llama-3.1-8b-instant"

def test_groq_connection():
    print("🔍 Testing Groq API connection...")
    print(f"📡 API Key: {GROQ_API_KEY[:20]}...")
    print(f"🤖 Model: {GROQ_MODEL}")
    print("-" * 50)
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "user", "content": "Say 'API connection successful!' in one sentence."}
                ],
                "temperature": 0.3,
                "max_tokens": 50
            },
            timeout=30
        )
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            message = data["choices"][0]["message"]["content"]
            print(f"✅ SUCCESS: API is working!")
            print(f"💬 Response: {message}")
            return True
        else:
            print(f"❌ ERROR: API returned status {response.status_code}")
            print(f"📄 Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot reach Groq API. Check your internet connection.")
        return False
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out. Try again.")
        return False
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = test_groq_connection()
    print("-" * 50)
    if success:
        print("🎉 Your app will work! Run: python app.py")
    else:
        print("⚠️  Fix the API issue before running the app")
