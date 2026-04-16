import pytest
from plexir.core.context import enforce_context_limit, estimate_token_count

def create_long_history(num_messages=20, msg_len=100):
    history = []
    for i in range(num_messages):
        role = "user" if i % 2 == 0 else "model"
        content = f"Message {i}: " + "x" * msg_len
        history.append({"role": role, "content": content})
    return history

def test_estimate_token_count():
    # "1234" is 1 word. int(1 * 1.3) + 2 = 3
    assert estimate_token_count("1234") == 3
    # "1234 5678" is 2 words. int(2 * 1.3) + 2 = 4
    assert estimate_token_count("1234 5678") == 4
    # Dict overhead is +4. int(1*1.3)+2 + 4 = 7
    assert estimate_token_count({"content": "1234"}) == 7

def test_pruning_limit():
    # 1. Create a history that definitely exceeds a small limit
    # With new heuristic: "Message i: x...x" is approx 2 words.
    # Each message: (int(2 * 1.3) + 2) + 4 (overhead) = 8 tokens
    # 50 messages -> 400 tokens
    history = create_long_history(50, 100)
    
    limit = 100
    pruned_history = enforce_context_limit(history, limit)
    final_tokens = estimate_token_count(pruned_history)
    
    # Assert final tokens are within limit
    assert final_tokens <= limit, f"Final tokens {final_tokens} exceeded limit {limit}"
    
    # Assert pruning actually happened
    assert len(pruned_history) < len(history)
    
    # Assert recent messages are preserved (default KEEP_LAST_MESSAGES=4)
    assert pruned_history[-1] == history[-1]
    
    # Assert summary message exists
    assert any("summarized" in msg.get("content", "") for msg in pruned_history)

def test_no_pruning_needed():
    history = create_long_history(2, 20) # Very short
    limit = 1000
    pruned_history = enforce_context_limit(history, limit)
    
    assert len(pruned_history) == len(history)
    assert pruned_history == history

def test_no_limit_param():
    history = create_long_history(5, 50)
    assert enforce_context_limit(history, None) == history
    assert enforce_context_limit(history, 0) == history
