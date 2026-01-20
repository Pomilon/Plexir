"""
Standalone Authentication Helper for Plexir.
Run this script to generate OAuth credentials for Plexir using your own Client Secrets.
"""

import os
import json
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: 'google-auth-oauthlib' is required. Run: pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    'https://www.googleapis.com/auth/cloud-platform',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/generative-language.retriever'
]

def authenticate():
    print("--- Plexir Authentication Helper ---")
    
    secrets_path = os.path.expanduser("~/.plexir/client_secrets.json")
    if not os.path.exists(secrets_path):
        print(f"❌ Error: Client secrets file not found at {secrets_path}")
        print("\nTo use OAuth, you must provide your own Client ID:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
        print("2. Create Project (if needed) -> 'Create Credentials' -> 'OAuth client ID'.")
        print("3. Application Type: 'Desktop app'.")
        print("4. Download the JSON file.")
        print(f"5. Rename it to 'client_secrets.json' and move it to: {os.path.dirname(secrets_path)}/")
        return

    print(f"Found secrets at: {secrets_path}")
    print("Starting OAuth Flow...")
    print("-" * 60)
    print("1. If the browser opens, log in there.")
    print("2. If running remotely (SSH) or headless:")
    print("   a. Run this on your local machine: ssh -L 8090:localhost:8090 <your-user>@<your-server>")
    print("   b. Open the URL below in your local browser.")
    print("   c. The redirect to http://localhost:8090/ will be tunneled back here.")
    print("-" * 60)
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
        # Use Fixed Port 8090 to allow SSH tunneling
        creds = flow.run_local_server(port=8090, open_browser=True)

        # Save credentials
        save_path = os.path.expanduser("~/.plexir/oauth_creds.json")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # We must save the full info including client_id so refreshing works
        with open(save_path, 'w') as f:
            f.write(creds.to_json())
        
        print(f"\n✅ Success! Credentials saved to: {save_path}")
        print("You can now run Plexir and use 'auth_mode=oauth'.")
        
    except Exception as e:
        print(f"❌ Auth Flow Failed: {e}")

    input("\nPress Enter to exit...")

if __name__ == "__main__":
    authenticate()
