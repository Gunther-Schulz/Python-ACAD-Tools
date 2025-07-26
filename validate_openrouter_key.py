import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def validate_openrouter_key():
    """
    Validates the OpenRouter API key by making a request to the API
    """
    print("Validating OpenRouter API key...")

    # Get the API key from environment variables
    api_key = os.getenv('OR_F1_API_KEY')

    if not api_key:
        print("Error: OR_F1_API_KEY not found in environment variables")
        return

    try:
        # Make request to OpenRouter API to validate key
        response = requests.get(
            url="https://openrouter.ai/api/v1/key",
            headers={
                "Authorization": f"Bearer {api_key}"
            }
        )

        # Check if request was successful
        if response.status_code == 200:
            data = response.json()
            print("✅ API key is valid!")
            print(json.dumps(data, indent=2))

            # Extract key information
            key_data = data.get("data", {})
            print("\nKey Information:")
            print(f"  Label: {key_data.get('label', 'N/A')}")
            print(f"  Limit: {key_data.get('limit', 'N/A')}")
            print(f"  Usage: {key_data.get('usage', 'N/A')}")
            print(f"  Remaining: {key_data.get('limit_remaining', 'N/A')}")
            print(f"  Free Tier: {key_data.get('is_free_tier', 'N/A')}")

        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    validate_openrouter_key()
