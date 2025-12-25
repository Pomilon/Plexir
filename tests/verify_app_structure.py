from plexir.ui.app import PlexirApp

def test_app_structure():
    """Verify that PlexirApp has the expected structure and methods."""
    app = PlexirApp()
    
    # Verify generate_response exists and is a method
    assert hasattr(app, 'generate_response'), "PlexirApp is missing 'generate_response' method"
    assert callable(app.generate_response), "'generate_response' is not callable"
    
    # Verify helper exists
    assert hasattr(app, '_add_message'), "PlexirApp is missing '_add_message' method"
    
    print("PlexirApp structure verified successfully.")

if __name__ == "__main__":
    test_app_structure()