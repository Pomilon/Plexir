from typing import List, Dict, Any

MAX_DISTILLED_HISTORY_LENGTH = 1000 # Max characters for the distilled context
MAX_MESSAGE_LENGTH = 200 # Max characters for an individual message in distilled context
RECENT_MESSAGES_COUNT = 5 # Number of recent messages to prioritize

def distill(history: List[Dict[str, Any]]) -> str:
    """
    Distills the conversation history into a concise context summary,
    prioritizing recent and important messages. This is used during failover
    to provide the backup model with essential context.
    """
    distilled_parts = []
    current_length = 0

    # Iterate through history in reverse to prioritize recent messages
    for msg in reversed(history):
        # Extract role and content
        role = msg.get("role", "unknown")
        content = ""

        # Handle different message types (text, function_call, function_response)
        if "content" in msg:
            content = msg["content"]
        elif "parts" in msg:
            # Reconstruct content from parts, prioritizing function calls/responses
            part_texts = []
            for part in msg["parts"]:
                if isinstance(part, dict):
                    if "function_call" in part:
                        fc = part["function_call"]
                        part_texts.append(f"Function Call: {fc['name']}({fc['args']})")
                    elif "function_response" in part:
                        fr = part["function_response"]
                        part_texts.append(f"Function Response: {fr['name']} -> {fr['response']}")
                    else: # Generic part dict
                        part_texts.append(str(part))
                else: # Assume string part
                    part_texts.append(str(part))
            content = "\n".join(part_texts)

        # Truncate long messages
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH] + "... (truncated)"
        
        # Format the message for distillation
        formatted_message = f"{role.upper()}: {content}\n"
        
        # Check if adding this message exceeds the total length
        if current_length + len(formatted_message) > MAX_DISTILLED_HISTORY_LENGTH:
            break # Stop adding messages
        
        distilled_parts.insert(0, formatted_message) # Add to the beginning to maintain original order
        current_length += len(formatted_message)

        # Stop if we have enough recent messages and hit length limit
        if len(distilled_parts) >= RECENT_MESSAGES_COUNT and current_length > MAX_DISTILLED_HISTORY_LENGTH / 2:
            break
            
    if not distilled_parts:
        return "No relevant recent context available."

    return "--- Distilled Previous Context (from failover) ---\n" + "".join(distilled_parts) + "----------------------------------------------------"

def get_messages_to_summarize(history: List[Dict[str, Any]], count: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Splits history into 'to be summarized' and 'to keep' (pinned or recent).
    """
    to_summarize = []
    to_keep = []
    
    # We never summarize the last 10 messages to keep immediate flow
    keep_recent = history[-10:] if len(history) > 10 else history
    history_old = history[:-10] if len(history) > 10 else []

    for msg in history_old:
        if msg.get("pinned"):
            to_keep.append(msg)
        else:
            to_summarize.append(msg)
            
    # If we have too many to summarize, only take 'count' oldest
    if len(to_summarize) > count:
        remaining = to_summarize[count:]
        to_summarize = to_summarize[:count]
        to_keep = to_keep + remaining

    return to_summarize, to_keep + keep_recent
