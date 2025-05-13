# from fastapi import APIRouter, HTTPException, Request
# import httpx
# import os
# from dotenv import load_dotenv
# import json

# router = APIRouter(prefix="/auth")
# load_dotenv()

# GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
# GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# @router.post("/github/callback")
# async def github_callback(request: Request):
#     """
#     Exchange GitHub authorization code for access token
#     """
#     try:
#         # Get the request body as JSON
#         body = await request.json()
#         code = body.get("code")

#         print(f"Received code: {code[:10]}..." if code else "No code received")

#         if not code:
#             raise HTTPException(status_code=400, detail="No authorization code provided")

#         # Exchange code for token
#         token_url = "https://github.com/login/oauth/access_token"
#         payload = {
#             "client_id": GITHUB_CLIENT_ID,
#             "client_secret": GITHUB_CLIENT_SECRET,
#             "code": code
#         }
#         headers = {"Accept": "application/json"}

#         print(f"Sending request to GitHub with client_id: {GITHUB_CLIENT_ID[:5]}...")

#         async with httpx.AsyncClient() as client:
#             response = await client.post(token_url, json=payload, headers=headers)
#             token_data = response.json()

#             print(f"GitHub token response status: {response.status_code}")

#             if "error" in token_data:
#                 print(f"GitHub API error: {token_data}")
#                 raise HTTPException(status_code=400, detail=token_data.get("error_description", "Failed to exchange code for token"))

#             access_token = token_data.get("access_token")

#             if not access_token:
#                 print("No access token received from GitHub")
#                 raise HTTPException(status_code=400, detail="No access token received from GitHub")

#             print(f"Received token: {access_token[:10]}...")

#             # Fetch user data from GitHub
#             user_response = await client.get(
#                 "https://api.github.com/user",
#                 headers={"Authorization": f"token {access_token}"}
#             )

#             print(f"GitHub user data response status: {user_response.status_code}")

#             if user_response.status_code != 200:
#                 print(f"GitHub API error: {user_response.text}")
#                 raise HTTPException(status_code=400, detail="Failed to fetch user data")

#             user_data = user_response.json()

#             # Return token and user data
#             return {
#                 "token": access_token,
#                 "user": {
#                     "id": user_data.get("id"),
#                     "name": user_data.get("name"),
#                     "username": user_data.get("login"),
#                     "email": user_data.get("email"),
#                     "avatarUrl": user_data.get("avatar_url")
#                 }
#             }
#     except HTTPException:
#         raise  # Re-raise HTTP exceptions
#     except Exception as e:
#         import traceback
#         print(f"Authentication error: {str(e)}")
#         print(traceback.format_exc())
#         raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

# @router.get("/validate")
# async def validate_token(request: Request):
#     """
#     Validate GitHub token and return user info
#     """
#     try:
#         authorization = request.headers.get("Authorization")

#         print(f"Authorization header: {authorization[:15]}..." if authorization else "No Authorization header")

#         if not authorization or not authorization.startswith("Bearer "):
#             raise HTTPException(status_code=401, detail="Invalid or missing token")

#         token = authorization.replace("Bearer ", "")

#         print(f"Token to validate: {token[:10]}...")

#         async with httpx.AsyncClient() as client:
#             response = await client.get(
#                 "https://api.github.com/user",
#                 headers={"Authorization": f"token {token}"}
#             )

#             print(f"GitHub API response status: {response.status_code}")

#             if response.status_code != 200:
#                 print(f"GitHub API error response: {response.text}")
#                 raise HTTPException(status_code=401, detail="Invalid token")

#             user_data = response.json()

#             return {
#                 "user": {
#                     "id": user_data.get("id"),
#                     "name": user_data.get("name"),
#                     "username": user_data.get("login"),
#                     "email": user_data.get("email"),
#                     "avatarUrl": user_data.get("avatar_url")
#                 }
#             }
#     except HTTPException:
#         raise
#     except Exception as e:
#         import traceback
#         print(f"Token validation error: {str(e)}")
#         print(traceback.format_exc())
#         raise HTTPException(status_code=500, detail=f"Token validation failed: {str(e)}")

from fastapi import APIRouter, HTTPException, Request
import httpx
import os
from dotenv import load_dotenv
import json
from functools import lru_cache
import time

router = APIRouter(prefix="/auth")
load_dotenv()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# Simple cache for user data to reduce GitHub API calls
user_cache = {}

@router.post("/github/callback")
async def github_callback(request: Request):
    """
    Exchange GitHub authorization code for access token
    """
    try:
        start_time = time.time()
        # Get the request body as JSON
        body = await request.json()
        code = body.get("code")

        print(f"Received code: {code[:10]}..." if code else "No code received")

        if not code:
            raise HTTPException(status_code=400, detail="No authorization code provided")

        # Exchange code for token
        token_url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code
        }
        headers = {"Accept": "application/json"}

        print(f"Sending request to GitHub with client_id: {GITHUB_CLIENT_ID[:5]}...")

        # Create a client with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First API call - get token
            token_start = time.time()
            response = await client.post(token_url, json=payload, headers=headers)
            token_data = response.json()
            token_time = time.time() - token_start
            print(f"GitHub token response status: {response.status_code} (took {token_time:.2f}s)")

            if "error" in token_data:
                print(f"GitHub API error: {token_data}")
                raise HTTPException(status_code=400, detail=token_data.get("error_description", "Failed to exchange code for token"))

            access_token = token_data.get("access_token")

            if not access_token:
                print("No access token received from GitHub")
                raise HTTPException(status_code=400, detail="No access token received from GitHub")

            print(f"Received token: {access_token[:10]}...")

            # Second API call - get user data
            user_start = time.time()
            user_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {access_token}"}
            )
            user_time = time.time() - user_start
            print(f"GitHub user data response status: {user_response.status_code} (took {user_time:.2f}s)")

            if user_response.status_code != 200:
                print(f"GitHub API error: {user_response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch user data")

            user_data = user_response.json()
            
            # Cache the user data with the token
            user_obj = {
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "username": user_data.get("login"),
                "email": user_data.get("email"),
                "avatarUrl": user_data.get("avatar_url")
            }
            user_cache[access_token] = user_obj
            
            total_time = time.time() - start_time
            print(f"Total callback processing time: {total_time:.2f}s")

            # Return token and user data
            return {
                "token": access_token,
                "user": user_obj
            }
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        import traceback
        print(f"Authentication error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/validate")
async def validate_token(request: Request):
    """
    Validate GitHub token and return user info
    """
    try:
        start_time = time.time()
        authorization = request.headers.get("Authorization")

        print(f"Authorization header: {authorization[:15]}..." if authorization else "No Authorization header")

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid or missing token")

        token = authorization.replace("Bearer ", "")

        print(f"Token to validate: {token[:10]}...")
        
        # Check cache first to avoid GitHub API call
        if token in user_cache:
            print(f"User data found in cache for token {token[:10]}...")
            response_time = time.time() - start_time
            print(f"Token validation (from cache) completed in {response_time:.2f}s")
            return {
                "user": user_cache[token]
            }

        # Not in cache, validate with GitHub
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}"}
            )

            api_time = time.time() - start_time
            print(f"GitHub API response status: {response.status_code} (took {api_time:.2f}s)")

            if response.status_code != 200:
                print(f"GitHub API error response: {response.text}")
                raise HTTPException(status_code=401, detail="Invalid token")

            user_data = response.json()
            
            # Create user object
            user_obj = {
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "username": user_data.get("login"),
                "email": user_data.get("email"),
                "avatarUrl": user_data.get("avatar_url")
            }
            
            # Cache the result
            user_cache[token] = user_obj
            
            total_time = time.time() - start_time
            print(f"Total validation processing time: {total_time:.2f}s")

            return {
                "user": user_obj
            }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Token validation error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Token validation failed: {str(e)}")