import sys
import os

# Add parent directory to path to make imports work from module root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from fastapi import APIRouter, HTTPException, Query, Request
import httpx
from typing import List
import asyncio
from utils.github_auth import get_github_headers
import crud as crud
from dotenv import load_dotenv
import services.Graph_db_service as graph_db_service
import time

router = APIRouter()
load_dotenv()

GITHUB_API_BASE = "https://api.github.com"

def get_github_headers():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GitHub token not found.")
    return {"Authorization": f"token {token}"}


def get_github_headers_from_request(request):
    """Get GitHub headers from the request's Authorization header"""
    authorization = request.headers.get("Authorization")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    token = authorization.replace("Bearer ", "")
    return {"Authorization": f"token {token}"}

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
            response = await client.get(url, headers=get_github_headers())
            raw_commits = response.json()
            
            start_detail_time = time.time()
            # Get detailed commit data for each commit
            detailed_commits = []
            for commit in raw_commits:
                sha = commit.get("sha")
                detail_url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{sha}"
                detail_resp = await client.get(detail_url, headers=get_github_headers())
                if detail_resp.status_code == 200:
                    detailed_commits.append(detail_resp.json())
                else:
                    print(f"Warning: Could not fetch details for commit {sha}")
                    detailed_commits.append(commit)  # Use basic commit info if details not available

            end_detail_time = time.time()
            print(f"Time taken to fetch detailed commit data: {end_detail_time - start_detail_time} seconds")

        commits = []
        repository_info = {
            "name": repo,
            "url": f"https://github.com/{repo}",
            "description": f"Repository {repo}, branch {branch}"
        }
        
        for c in detailed_commits:
            print("Processing commit:", c.get("sha"))
            sha = c.get("sha")
            
            # Get basic commit info
            commit_details = c.get("commit", {})
            author_details = commit_details.get("author", {})
            author_name = author_details.get("name", "Unknown")
            author_email = author_details.get("email", "")
            date = author_details.get("date")
            message = commit_details.get("message", "")
            commit_url = c.get("html_url", "")
            
            # Get GitHub username (login) if available
            github_author = c.get("author", {})
            author_github = github_author.get("login", "") if github_author else ""
            
            # Extract file changes
            files = c.get("files", [])
            added_files = []
            modified_files = []
            deleted_files = []
            
            for file in files:
                status = file.get("status", "")
                path = file.get("filename", "")
                
                if status == "added":
                    added_files.append(path)
                elif status == "modified":
                    modified_files.append(path)
                elif status == "removed":
                    deleted_files.append(path)
            
            # Save to SQL database
            repo_id = get_repo_id(repo)
            start_crud_time = time.time()
            crud.insert_commit(repo_id, sha, author_name, date, message, commit_url)
            end_crud_time = time.time()
            print(f"Time taken to insert commit data into SQL: {end_crud_time - start_crud_time} seconds")
            
            start_graph_time = time.time()
            # Process for Neo4j graph database
            await graph_db_service.process_commit_data(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                author_github=author_github,
                date=date,
                message=message,
                added_files=added_files,
                modified_files=modified_files,
                deleted_files=deleted_files,
                repository_info=repository_info
            )
            end_graph_time = time.time()
            print(f"Time taken to insert commit data into Neo4j: {end_graph_time - start_graph_time} seconds")

            # Build response
            commits.append({
                "sha": sha,
                "author": author_name,
                "date": date,
                "message": message,
                "url": commit_url,
                "files_changed": len(added_files) + len(modified_files) + len(deleted_files)
            })

        return {"repository": repo, "branch": branch, "commits": commits}

    except httpx.HTTPStatusError as e:
        print(f"Error response from GitHub API: {e.response.text}")
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
async def fetch_pull_requests(request: Request, repo: str, state: str = "all"):
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
async def fetch_repo_info(repo: str, request: Request):
    """
    Fetch basic metadata of a GitHub repository (format: owner/repo).
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            data = resp.json()
            return {
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "language": data.get("language"),
                "stars": data.get("stargazers_count"),
                "forks": data.get("forks_count"),
                "url": data.get("html_url"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at")
            }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/sync")
async def sync_all(request: Request, repo: str = Query(...), branch: str = Query("main")):
    """
    Sync all GitHub data for a repository (commits, PRs, issues, contributors).
    """
    try:
        return {
            "commits": await fetch_commits(request=request, repo=repo, branch=branch),
            "pull_requests": await fetch_pull_requests(request=request, repo=repo),
            "issues": await fetch_issues(request=request, repo=repo),
            "contributors": await fetch_contributors(request=request, repo=repo)

        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during sync: {str(e)}")

@router.get("/repo/{owner}/{repo}/stats")
async def get_repo_stats(owner: str, repo: str):
    """
    Get and store total numbers of commits, issues, and PRs for a repository.
    """
    headers = get_github_headers()
    base_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"

    try:
        async with httpx.AsyncClient() as client:
            # 1. Repo info (open issue count)
            repo_info_resp = await client.get(base_url, headers=headers)
            repo_info_resp.raise_for_status()
            repo_info = repo_info_resp.json()
            open_issues_count = repo_info.get("open_issues_count", 0)
            description = repo_info.get("description", "")

            # 2. PR count using pagination
            pr_resp = await client.get(f"{base_url}/pulls?state=all&per_page=1", headers=headers)
            pr_count = extract_total_from_link_header(pr_resp.headers.get("Link"))

            # 3. Actual issue count (excluding PRs)
            issue_resp = await client.get(
                f"{GITHUB_API_BASE}/search/issues?q=repo:{owner}/{repo}+type:issue",
                headers=headers
            )
            issues_total = issue_resp.json().get("total_count", 0)

            # 4. Commit count via stats endpoint (poll if necessary)
            stats_url = f"{base_url}/stats/contributors"
            for _ in range(3):
                stats_resp = await client.get(stats_url, headers=headers)
                if stats_resp.status_code == 202:
                    await asyncio.sleep(1)
                    continue
                stats_resp.raise_for_status()
                break
            else:
                raise HTTPException(status_code=202, detail="GitHub is computing commit stats. Try again later.")

            contributors_data = stats_resp.json()
            commit_total = sum(c.get("total", 0) for c in contributors_data) if contributors_data else 0

            # 5. Store in DB
            repo_id = crud.get_or_create_repository_id(owner, repo, description)
            crud.insert_repo_stats(repo_id, commit_total, issues_total, pr_count, open_issues_count)

            return {
                "commits": commit_total,
                "issues": issues_total,
                "pull_requests": pr_count,
                "open_issues_count_from_repo": open_issues_count
            }

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
    
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

