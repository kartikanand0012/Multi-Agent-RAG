"""Quick smoke test — verifies Azure OpenAI connection for both chat and embeddings."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm.client import llm_client, count_tokens
from app.core.config import settings


async def main():
    print(f"Using Azure: {settings.use_azure}")
    print(f"Strong model : {llm_client.strong_model}")
    print(f"Fast model   : {llm_client.fast_model}")
    print()

    # Test 1: chat completion
    print("Test 1: Chat completion...")
    messages = [{"role": "user", "content": "Reply with exactly three words: system is working"}]
    response = await llm_client.complete(messages, model=llm_client.fast_model)
    print(f"  Response: {response.strip()}")

    # Test 2: embeddings
    print("Test 2: Embeddings...")
    vectors = await llm_client.embed(["Hello world"])
    print(f"  Embedding dimensions: {len(vectors[0])}")

    # Test 3: token counter
    print("Test 3: Token counter...")
    text = "The quick brown fox jumps over the lazy dog"
    print(f"  '{text}' = {count_tokens(text)} tokens")

    print("\nAll tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
