from dotenv import load_dotenv
from google import genai
import os
import time

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("ERROR: API key not found!")
    exit()

print("SUCCESS: Gemini API key loaded!")
print("Testing Gemini API...")

client = genai.Client(api_key=API_KEY)

models_to_test = [
    "gemini-3.8-flash"
]

for model in models_to_test:
    print(f"\nTesting model: {model}")

    try:
        start = time.time()

        response = client.models.generate_content(
            model=model,
            contents="Reply only: Gemini API is working!"
        )

        print("\nSUCCESS!")
        print("Response:", response.text)
        print("Time:", round(time.time() - start, 2), "seconds")
        break

    except Exception as e:
        print("\nFAILED:", str(e))