import asyncio
import logging
from plexir.core.router import GeminiProvider, OpenAICompatibleProvider, Router
from plexir.core.config_manager import ProviderConfig
from plexir.tools.base import ToolRegistry

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

async def test_gemini_provider():
    print("--- Testing GeminiProvider ---")
    config = ProviderConfig(
        name="Gemini Test",
        type="gemini",
        model_name="gemini-1.5-flash",
        api_key="mock_key"
    )
    registry = ToolRegistry()
    provider = GeminiProvider(config, registry)
    
    # Test 1: Normal message
    print("Test 1: Normal 'Hello'")
    try:
        # Note: This will likely fail without a real API key if not mocked, 
        # but we are testing structure/imports here.
        async for chunk in provider.generate([{"role": "user", "content": "Hello"}], "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Expected/Actual Failure]: {e}")

async def test_groq_provider():
    print("\n--- Testing GroqProvider (via OpenAICompatibleProvider) ---")
    config = ProviderConfig(
        name="Groq Test",
        type="groq",
        model_name="llama3-70b-8192",
        api_key="mock_key"
    )
    registry = ToolRegistry()
    provider = OpenAICompatibleProvider(config, registry)
    
    # Test 1: Normal message
    print("Test 1: Normal 'Hello'")
    try:
        async for chunk in provider.generate([{"role": "user", "content": "Hello"}], "You are a helpful assistant."):
            print(chunk, end="", flush=True)
        print("\n[Success]")
    except Exception as e:
        print(f"\n[Expected/Actual Failure]: {e}")

async def main():
    await test_gemini_provider()
    await test_groq_provider()

if __name__ == "__main__":
    asyncio.run(main())
