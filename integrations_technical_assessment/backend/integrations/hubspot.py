# HubSpot OAuth integration completed
import json
import secrets
import base64
import hashlib
import asyncio
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = 'b7ac70d4-30cb-42ef-aba5-26b2c8748e4d'
CLIENT_SECRET = '0367597c-223d-4421-b460-40d3010eefda'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
SCOPES = 'crm.objects.contacts.read crm.objects.contacts.write crm.objects.companies.read crm.objects.companies.write crm.objects.deals.read crm.objects.deals.write oauth'


authorization_url = (
    f'https://app.hubspot.com/oauth/authorize?client_id={CLIENT_ID}'
    f'&response_type=code&redirect_uri={REDIRECT_URI}&scope={SCOPES}'
)


async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')

    auth_url = f'{authorization_url}&state={encoded_state}&code_challenge={code_challenge}&code_challenge_method=S256'

    await asyncio.gather(
        add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', json.dumps(state_data), expire=600),
        add_key_value_redis(f'hubspot_verifier:{org_id}:{user_id}', code_verifier, expire=600)
    )

    return {"authorization_url": auth_url}

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error_description'))

    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(base64.urlsafe_b64decode(encoded_state).decode())

    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')
    original_state = state_data.get('state')

    saved_state, code_verifier = await asyncio.gather(
        get_value_redis(f'hubspot_state:{org_id}:{user_id}'),
        get_value_redis(f'hubspot_verifier:{org_id}:{user_id}')
    )

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            'https://api.hubapi.com/oauth/v1/token',
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': REDIRECT_URI,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'code_verifier': code_verifier
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

    await asyncio.gather(
        delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        delete_key_redis(f'hubspot_verifier:{org_id}:{user_id}')
    )

    if token_response.status_code != 200:
        raise HTTPException(status_code=token_response.status_code, detail=token_response.text)

    await add_key_value_redis(
        f'hubspot_credentials:{org_id}:{user_id}',
        json.dumps(token_response.json()),
        expire=600
    )

    return HTMLResponse('<html><script>window.close();</script></html>')

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')
    return json.loads(credentials)

def create_integration_item_metadata_object(response_json, item_type='Contact', parent_id=None, parent_name=None) -> IntegrationItem:
    name = (
        (response_json.get('properties', {}).get('firstname', '') + ' ' +
         response_json.get('properties', {}).get('lastname', '')).strip()
        or 'Unnamed Contact'
    )
    return IntegrationItem(
        id=response_json.get('id'),
        type=item_type,
        name=name,
        parent_id=parent_id,
        parent_path_or_name=parent_name,
        creation_time=response_json.get('createdAt'),
        last_modified_time=response_json.get('updatedAt'),
    )

async def get_items_hubspot(credentials):
    credentials = json.loads(credentials)
    access_token = credentials.get('access_token')

    url = 'https://api.hubapi.com/crm/v3/objects/contacts'
    headers = {'Authorization': f'Bearer {access_token}'}
    list_of_integration_items = []

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        for item in response.json().get('results', []):
            list_of_integration_items.append(
                create_integration_item_metadata_object(item, 'Contact')
            )

    print(f'HubSpot Integration Items: {list_of_integration_items}')
    return [item.__dict__ for item in list_of_integration_items]
