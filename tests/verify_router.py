import asyncio
import logging
from plexir.core.router import GeminiProvider, GroqProvider, Router

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

async def test_gemini_provider():
    print("--- Testing GeminiProvider ---")
    provider = GeminiProvider()
    
    # Test 1: Normal message
    print("Test 1: Normal 'Hello'")
    try:
        async for chunk in provider.generate([{"role": "user", "content": "Hello"}], "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Failed]: {e}")

    # Test 2: Empty User Content in History (Should be skipped or handled)
    print("\nTest 2: History with empty content")
    history = [
        {"role": "user", "content": "   "}, # Whitespace should be ignored/skipped
        {"role": "user", "content": "Hi again"}
    ]
    try:
        async for chunk in provider.generate(history, "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Failed]: {e}")

    # Test 3: Empty Last Message (Immediate trigger for 'content must not be empty')
    print("\nTest 3: Empty Last Message")
    history = [{"role": "user", "content": ""}]
    try:
        async for chunk in provider.generate(history, "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Failed]: {e}")

async def test_groq_provider():
    print("\n--- Testing GroqProvider ---")
    provider = GroqProvider()
    
    # Test 1: Normal message
    print("Test 1: Normal 'Hello'")
    try:
        async for chunk in provider.generate([{"role": "user", "content": "Hello"}], "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Failed]: {e}")

async def main():
    await test_gemini_provider()
    # await test_groq_provider() # Uncomment to test Groq

if __name__ == "__main__":
    asyncio.run(main())
