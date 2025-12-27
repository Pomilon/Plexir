from textual.app import App, ComposeResult
from textual.widgets import Label

class DebugApp(App):
    def compose(self) -> ComposeResult:
        yield Label("Hello", id="test-label")

async def debug():
    app = DebugApp()
    async with app.run_test() as pilot:
        label = app.query_one("#test-label")
        print(f"Attributes: {dir(label)}")
        try:
            print(f"Renderable: {label.renderable}")
        except Exception as e:
            print(f"Renderable error: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug())
