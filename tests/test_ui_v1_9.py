import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from textual.widgets import TextArea, Collapsible
from textual.containers import VerticalScroll
from plexir.ui.app import PlexirApp
from plexir.ui.widgets import MessageBubble, MessageContent

@pytest.mark.asyncio
async def test_ui_message_queuing():
    """Test that submitting messages while busy adds them to the queue visually."""
    app = PlexirApp()
    async with app.run_test() as pilot:
        # Mock handle_user_message to be slow
        async def slow_handle(msg):
            await asyncio.sleep(0.5)
        app.handle_user_message = slow_handle
        
        text_area = app.query_one("#user-input", TextArea)
        
        # 1. Submit first message
        text_area.text = "Message 1"
        await pilot.press("ctrl+enter")
        await pilot.pause()
        
        # 2. Submit second message immediately
        text_area.text = "Message 2"
        await pilot.press("ctrl+enter")
        await pilot.pause()
        
        # Check chat scroll children
        chat_scroll = app.query_one("#chat-scroll", VerticalScroll)
        bubbles = list(chat_scroll.query(MessageBubble))
        
        # We expect 2 user bubbles
        user_bubbles = [b for b in bubbles if b.role == "user"]
        assert len(user_bubbles) >= 2
        
        # The second one should have the "queued" class
        queued_bubbles = [b for b in user_bubbles if "queued" in b.classes]
        assert len(queued_bubbles) >= 1
        
        queued_texts = [b.initial_content for b in queued_bubbles]
        assert "Message 2" in queued_texts

@pytest.mark.asyncio
async def test_ui_pull_back_to_input():
    """Test clicking a queued bubble pulls it back to the input field."""
    app = PlexirApp()
    async with app.run_test() as pilot:
        # Manually mount a queued bubble
        chat_scroll = app.query_one("#chat-scroll", VerticalScroll)
        bubble = MessageBubble(role="user", content="Queued Text")
        bubble.add_class("queued")
        await chat_scroll.mount(bubble)
        await pilot.pause()
        
        # Register it in the app's internal state
        app.queued_bubbles.append(("Queued Text", bubble))
        async with app.queue_condition:
            app.message_queue_list.append("Queued Text")

        # Click the bubble
        # We need to click exactly the bubble that is queued
        await pilot.click(MessageBubble)
        await pilot.pause()
        
        # Verify it was removed from UI
        bubbles = list(chat_scroll.query(MessageBubble))
        assert bubble not in bubbles
        assert "Queued Text" not in app.message_queue_list
        
        # Verify input field content
        input_widget = app.query_one("#user-input", TextArea)
        assert input_widget.text == "Queued Text"

@pytest.mark.asyncio
async def test_ui_expanded_reasoning_rendering():
    """Test that reasoning blocks respect the expanded_reasoning config."""
    from plexir.core.config_manager import config_manager
    config_manager.update_app_setting("expanded_reasoning", True)
    
    app = PlexirApp()
    async with app.run_test() as pilot:
        # Simulate an incoming message with reasoning
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "model", "content": "<think>I am thinking</think>Hello!"}
        ]
        
        app._load_history_to_chat(history)
        await pilot.pause()
        
        collapsible = app.query_one(Collapsible)
        assert collapsible.collapsed is False # Because config is True
        
        # Toggle config
        config_manager.update_app_setting("expanded_reasoning", False)
        app._load_history_to_chat(history)
        await pilot.pause()
        
        collapsible = app.query_one(Collapsible)
        assert collapsible.collapsed is True # Now it should be collapsed
