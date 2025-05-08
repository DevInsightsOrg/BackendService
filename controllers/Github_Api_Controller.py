from fastapi import APIRouter, HTTPException, Query, Request
import httpx
import os
from typing import List
import asyncio
import sys
sys.path.append('/Users/zehraiyigun/Desktop/DevInsights')
from utils.github_auth import get_github_headers  # Fixed import path
import crud as crud
from dotenv import load_dotenv

router = APIRouter()
load_dotenv()

GITHUB_API_BASE = "https://api.github.com"

@router.get("/user/repositories")
async def get_user_repositories(request: Request):
    """
    Get repositories for the authenticated user
    """
    authorization = request.headers.get("Authorization")
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos?sort=updated&per_page=100",
                headers={"Authorization": f"token {token}"}
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch repositories")
            
            repos_data = response.json()
            
            # Transform to your app's repository format
            repositories = []
            for repo in repos_data:
                repositories.append({
                    "id": str(repo.get("id")),
                    "name": repo.get("name"),
                    "description": repo.get("description"),
                    "language": repo.get("language"),
                    "isPrivate": repo.get("private", False),
                    "fullName": repo.get("full_name"),
                    "url": repo.get("html_url"),
                    "lastSyncDate": None  # You would track this in your database
                })
            
            return repositories
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch repositories: {str(e)}")

# Utility to get GitHub headers
def get_github_headers():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GitHub token not found.")
    return {"Authorization": f"Bearer {token}"}

# Function to get repo_id from repository name (this was missing)
def get_repo_id(repo_name):
    """
    Get repository ID from the database based on repository name format: username/repository
    If repository doesn't exist, create it first
    """
    try:
        # Extract owner and repository name from the format: username/repository
        parts = repo_name.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid repository format: {repo_name}. Expected format: owner/repo")
        
        owner, repo = parts
        
        # Get connection to database
        connection = crud.get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Search for repository in the database
        query = "SELECT id FROM repositories WHERE owner = %s AND repo_name = %s"
        cursor.execute(query, (owner, repo))
        result = cursor.fetchone()
        
        if result:
            # Repository exists, return its ID
            repo_id = result['id']
        else:
            # Repository doesn't exist, create a new entry
            query = """
            INSERT INTO repositories (repo_name, owner, created_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            """
            cursor.execute(query, (repo, owner))
            connection.commit()
            
            # Get the ID of the newly inserted repository
            repo_id = cursor.lastrowid
        
        cursor.close()
        connection.close()
        return repo_id
        
    except Exception as e:
        # Log the error and fall back to placeholder value in case of any error
        print(f"Error getting repository ID: {str(e)}")
        return 1  # Fallback to placeholder value


# @router.get("/commits")
# async def fetch_commits(
#     repo: str = Query(..., description="Format: username/repository"),
#     branch: str = Query("main", description="Branch name (default: main)"),
#     limit: int = Query(10, description="Number of commits to fetch")
# ):
#     """
#     Fetch latest commits from a GitHub repository branch.
#     """
#     url = f"{GITHUB_API_BASE}/repos/{repo}/commits?sha={branch}&per_page={limit}"

#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers=get_github_headers())
#             response.raise_for_status()  # This will raise an exception for 4xx/5xx errors
#             raw_commits = response.json()

#         commits = []
#         for c in raw_commits:
#             sha = c.get("sha")
#             author_name = c.get("commit", {}).get("author", {}).get("name")
#             date = c.get("commit", {}).get("author", {}).get("date")
#             message = c.get("commit", {}).get("message")
#             commit_url = c.get("html_url")
            
#             # Save to database
#             repo_id = get_repo_id(repo)
#             crud.insert_commit(repo_id, sha, author_name, date, message, commit_url)
            
#             commits.append({
#                 "sha": sha,
#                 "author": author_name,
#                 "date": date,
#                 "message": message,
#                 "url": commit_url
#             })

#         return {"repository": repo, "branch": branch, "commits": commits}

#     except httpx.HTTPStatusError as e:
#         print(f"Error response from GitHub API: {e.response.text}")  # Print the full response error message
#         raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

def get_github_headers_from_request(request):
    """Get GitHub headers from the request's Authorization header"""
    authorization = request.headers.get("Authorization")
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    
    token = authorization.replace("Bearer ", "")
    return {"Authorization": f"token {token}"}

# Then update each endpoint to use this function:
@router.get("/commits")
async def fetch_commits(
    request: Request,
    repo: str = Query(..., description="Format: username/repository"),
    branch: str = Query("main", description="Branch name (default: main)"),
    limit: int = Query(10, description="Number of commits to fetch")
):
    """
    Fetch latest commits from a GitHub repository branch.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits?sha={branch}&per_page={limit}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=get_github_headers_from_request(request))
        
        commits = []
        for c in raw_commits:
            sha = c.get("sha")
            author_name = c.get("commit", {}).get("author", {}).get("name")
            date = c.get("commit", {}).get("author", {}).get("date")
            message = c.get("commit", {}).get("message")
            commit_url = c.get("html_url")
            
            # Save to database
            repo_id = get_repo_id(repo)
            crud.insert_commit(repo_id, sha, author_name, date, message, commit_url)
            
            commits.append({
                "sha": sha,
                "author": author_name,
                "date": date,
                "message": message,
                "url": commit_url
            })

        return {"repository": repo, "branch": branch, "commits": commits}

    except httpx.HTTPStatusError as e:
        print(f"Error response from GitHub API: {e.response.text}")  # Print the full response error message
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#NOT TESTED 
@router.get("/commit/{sha}/files")
async def get_diff_files(repo: str, sha: str):
    """
    Get list of files changed in a specific commit and store them in the database.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{sha}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()  # This will raise an exception if the status code is 4xx/5xx
            commit_data = resp.json()

            # Fetch the list of files modified in the commit
            files = commit_data.get("files", [])

            # Fetch repo_id from the database (or create it if necessary)
            repo_id = get_repo_id(repo)

            # Insert commit files into the database
            for file in files:
                crud.insert_commit_file(sha, repo_id, file)

            return [{
                "filename": file["filename"],
                "status": file["status"],
                "additions": file["additions"],
                "deletions": file["deletions"],
                "changes": file["changes"]
            } for file in files]

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/pulls")
async def fetch_pull_requests(repo: str, state: str = "all"):
    """
    Fetch pull requests from a GitHub repo (open, closed, all).
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls?state={state}&per_page=100"
    
    # Log the URL for debugging purposes
    print(f"Fetching pull requests from: {url}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status() 
            
            # Check if the response contains pull requests data
            pull_requests = resp.json()
            if not pull_requests:
                return {"message": "No pull requests found for the given state."}

            # Return the pull requests data in a structured format
            return [{
                "id": pr["id"],
                "title": pr["title"],
                "state": pr["state"],
                "user": pr["user"]["login"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "url": pr["html_url"]
            } for pr in pull_requests]

    except httpx.HTTPStatusError as e:
        # Handle HTTP error with more detailed information
        print(f"Error response from GitHub API: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        # Handle other types of errors (e.g., network issues)
        print(f"Error making request to GitHub API: {str(e)}")
        raise HTTPException(status_code=500, detail="Error making request to GitHub API")
    except Exception as e:
        # General error handling
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/issues")
async def fetch_issues(repo: str, state: str = "all"):
    """
    Fetch issues from a GitHub repo and save them to the database.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues?state={state}&per_page=100"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            
            issues = resp.json()
            if not issues:
                return {"message": "No issues found for the given state."}

            # Insert the issues into the database
            repo_id = get_repo_id(repo)
            for issue in issues:
                crud.insert_issue(
                    repo_id=repo_id,
                    issue_number=issue["number"],
                    state=issue["state"],
                    title=issue["title"],
                    created_at=issue["created_at"],
                    updated_at=issue["updated_at"],
                    url=issue["html_url"]
                )
            
            return [{
                "id": issue["id"],
                "title": issue["title"],
                "state": issue["state"],
                "user": issue["user"]["login"],
                "created_at": issue["created_at"],
                "updated_at": issue["updated_at"],
                "url": issue["html_url"]
            } for issue in issues]

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail="Error making request to GitHub API")
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@router.get("/reviews")
async def fetch_reviews(repo: str, pr_number: int):
    """
    Fetch code reviews for a specific pull request and save them to the database.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            
            reviews = resp.json()
            if not reviews:
                return {"message": "No reviews found for the given pull request."}

            # Insert the reviews into the database
            repo_id = get_repo_id(repo)
            for review in reviews:
                crud.insert_review(
                    repo_id=repo_id,
                    pr_number=pr_number,
                    review_id=review["id"],
                    user_id=review["user"]["login"],
                    state=review["state"],
                    submitted_at=review["submitted_at"],
                    body=review["body"]
                )

            return [{
                "review_id": review["id"],
                "user": review["user"]["login"],
                "state": review["state"],
                "submitted_at": review["submitted_at"],
                "body": review["body"]
            } for review in reviews]

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail="Error making request to GitHub API")
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/contributors")
async def fetch_contributors(repo: str, limit: int = 100):
    """
    Fetch contributor info for a GitHub repo and save them to the database.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/contributors?per_page={limit}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()

            contributors = resp.json()
            if not contributors:
                return {"message": "No contributors found for the given repository."}

            # Insert the contributors into the database
            repo_id = get_repo_id(repo)
            for contributor in contributors:
                crud.insert_contributor(
                    repo_id=repo_id,
                    username=contributor["login"],
                    contributions=contributor["contributions"]
                )

            return [{
                "username": contributor["login"],
                "contributions": contributor["contributions"]
            } for contributor in contributors]

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail="Error making request to GitHub API")
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/repo")
async def fetch_repo_info(repo: str):
    """
    Fetch basic metadata of the repository.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync")
async def sync_all(repo: str, branch: str = "main"):
    """
    Sync all GitHub data (commits, PRs, issues, reviews, contributors) for a repo.
    """
    return {
        "commits": await fetch_commits(repo, branch),
        "pull_requests": await fetch_pull_requests(repo),
        "issues": await fetch_issues(repo),
        "contributors": await fetch_contributors(repo),
    }

@router.get("/repo/{owner}/{repo}/stats")
async def get_repo_stats(owner: str, repo: str):
    """
    Get total numbers of commits, issues, PRs for a repository.
    """
    headers = get_github_headers()

    async with httpx.AsyncClient() as client:
        try:
            # Total issues (with PRs included)
            repo_info = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers)
            repo_info.raise_for_status()
            issues_count = repo_info.json().get("open_issues_count", 0)

            # PR count (get last page number)
            prs_resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls?state=all&per_page=1", headers=headers)
            pr_count = extract_total_from_link_header(prs_resp.headers.get("Link"))

            # Actual issues (subtract PRs or use search)
            search_resp = await client.get(f"{GITHUB_API_BASE}/search/issues?q=repo:{owner}/{repo}+type:issue", headers=headers)
            issues_total = search_resp.json().get("total_count", 0)

            # Commits via stats/contributors (slow but accurate)
            contribs_resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/stats/contributors", headers=headers)
            await asyncio.sleep(1)  # Wait for stats to be ready
            commits_data = contribs_resp.json()
            commit_total = sum(c["total"] for c in commits_data) if commits_data else None

            return {
                "commits": commit_total,
                "issues": issues_total,
                "pull_requests": pr_count,
                "open_issues_count_from_repo": issues_count
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


def extract_total_from_link_header(link_header: str):
    """
    Parses GitHub Link header to get the last page number.
    """
    if not link_header:
        return 0
    try:
        parts = link_header.split(",")
        for part in parts:
            if 'rel="last"' in part:
                url = part.split(";")[0].strip()[1:-1]
                params = httpx.URL(url).params
                return int(params.get("page", 0))
    except:
        return 0

@router.get("/commit/{sha}/details")
async def get_commit_details(repo: str, sha: str):
    """
    Returns a detailed view of a specific commit including author, committer, message, 
    changed files, and their change types.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{sha}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            commit = resp.json()

        return {
            "commit_hash": commit.get("sha"),
            "author_id": commit.get("author", {}).get("login"),         # GitHub username
            "committer_id": commit.get("committer", {}).get("login"),   # GitHub username
            "commit_datetime": commit.get("commit", {}).get("author", {}).get("date"),
            "commit_message": commit.get("commit", {}).get("message"),
            "repository": repo,
            "files_changed": [
                {
                    "filename": f.get("filename"),
                    "status": f.get("status"),  # modified, added, deleted
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                    "changes": f.get("changes")
                }
                for f in commit.get("files", [])
            ]
        }

    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"GitHub API error: {str(e)}")

