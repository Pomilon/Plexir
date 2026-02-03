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
    assert estimate_token_count("1234") == 1
    assert estimate_token_count("12345678") == 2
    assert estimate_token_count({"content": "1234"}) == 1
    assert estimate_token_count([{"content": "1234"}, {"content": "5678"}]) == 2

def test_pruning_limit():
    # 1. Create a history that definitely exceeds a small limit
    # Each message is roughly 100 chars + overhead -> ~25-30 tokens
    # 20 messages -> ~500-600 tokens
    history = create_long_history(20, 100)
    
    limit = 200
    pruned_history = enforce_context_limit(history, limit)
    final_tokens = estimate_token_count(pruned_history)
    
    # Assert final tokens are within limit
    assert final_tokens <= limit, f"Final tokens {final_tokens} exceeded limit {limit}"
    
    # Assert pruning actually happened
    assert len(pruned_history) < len(history)
    
    # Assert recent messages are preserved (default KEEP_LAST_MESSAGES=4)
    assert pruned_history[-1] == history[-1]
    assert pruned_history[-2] == history[-2]
    
    # Assert summary message exists
    assert "summarized" in pruned_history[0]["content"]

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
