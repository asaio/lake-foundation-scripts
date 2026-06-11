import os
import logging
import requests
import hvac

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_vault_secret():
    # Connect to Vault
    client = hvac.Client(url=os.environ['VAULT_ADDR'])
    # Authenticate (example: AppRole)
    client.auth_approle(
        role_id=os.environ['VAULT_ROLE_ID'],
        secret_id=os.environ['VAULT_SECRET_ID']
    )
    # Read secret
    secret = client.secrets.kv.v2.read_secret_version(path='azuread')
    return secret['data']['data']

def lambda_handler(event, context):
    email = event['email']
    message_text = event['message']

    # Step 1: Fetch secrets from Vault
    secrets = get_vault_secret()
    tenant_id = secrets['tenant_id']
    client_id = secrets['client_id']
    client_secret = secrets['client_secret']

    # Step 2: Get OAuth2 token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        'client_id': client_id,
        'scope': 'https://graph.microsoft.com/.default',
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    token_response = requests.post(token_url, data=token_data)
    token_response.raise_for_status()
    access_token = token_response.json()['access_token']
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    # Step 3: Resolve email → user
    user_url = f"https://graph.microsoft.com/v1.0/users/{email}"
    user_response = requests.get(user_url, headers=headers)
    user_response.raise_for_status()
    user_id = user_response.json()['id']

    # Step 4: Create/find chat
    chat_url = "https://graph.microsoft.com/v1.0/chats"
    chat_payload = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{user_id}"
            }
        ]
    }
    chat_response = requests.post(chat_url, headers=headers, json=chat_payload)
    chat_response.raise_for_status()
    chat_id = chat_response.json()['id']

    # Step 5: Send message
    message_url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
    message_payload = {"body": {"content": message_text}}
    send_response = requests.post(message_url, headers=headers, json=message_payload)
    send_response.raise_for_status()

    logger.info("Teams message sent successfully")
    return {"status": "success", "detail": "Teams message delivered"}
