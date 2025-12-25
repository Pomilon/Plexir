import google.generativeai as genai
import os
from plexir.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

print("Available Models:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")
