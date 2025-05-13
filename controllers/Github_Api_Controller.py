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
import services.Graph_db_service as graph_db_service
import time
import openai
import json
from services.Graph_db_service import get_db_driver

router = APIRouter()
load_dotenv()

GITHUB_API_BASE = "https://api.github.com"

# Initialize OpenAI client with API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("WARNING: OPENAI_API_KEY environment variable not set")

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
                    "owner": {
                        "login": repo.get("owner", {}).get("login"),
                        "id": str(repo.get("owner", {}).get("id")),
                        "avatar_url": repo.get("owner", {}).get("avatar_url")
                    },
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
    headers = get_github_headers_from_request(request)

    try:
        async with httpx.AsyncClient() as client:
            # Get list of commits
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Failed to fetch commits: {response.text}"
                )
                
            raw_commits = response.json()
            
            # Get detailed commit data for each commit
            start_detail_time = time.time()
            detailed_commits = []
            
            for commit in raw_commits:
                sha = commit.get("sha")
                detail_url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{sha}"
                detail_resp = await client.get(detail_url, headers=headers)
                
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
            total_additions = 0
            total_deletions = 0
            
            for file in files:
                status = file.get("status", "")
                path = file.get("filename", "")
                
                # Collect lines added/removed information
                additions = file.get("additions", 0)
                deletions = file.get("deletions", 0)
                total_additions += additions
                total_deletions += deletions
                
                if status == "added":
                    added_files.append(path)
                elif status == "modified":
                    modified_files.append(path)
                elif status == "removed":
                    deleted_files.append(path)
            
            # Call the LLM scoring method to evaluate commit quality
            start_score_time = time.time()
            commit_score = await score_commit_with_llm(
                message=message,
                additions=total_additions,
                deletions=total_deletions,
                added_files=added_files,
                modified_files=modified_files,
                deleted_files=deleted_files
            )
            end_score_time = time.time()
            print(f"Time taken to score commit with LLM: {end_score_time - start_score_time} seconds")
            
            # Extract scores from the LLM response
            overall_code_quality = commit_score.get("OverallCodeQuality", 0)
            commit_type_set = commit_score.get("CommitTypeSet", [])
            raw_scores = commit_score.get("RawScores", {})
            
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
                repository_info=repository_info,
                lines_added=total_additions,
                lines_removed=total_deletions,
                overall_code_quality=overall_code_quality,
                commit_type_set=commit_type_set
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
                "files_changed": len(added_files) + len(modified_files) + len(deleted_files),
                "lines_added": total_additions,
                "lines_removed": total_deletions,
                "overall_code_quality": overall_code_quality,
                "commit_types": commit_type_set,
                "type_scores": raw_scores
            })

        return {"repository": repo, "branch": branch, "commits": commits}

    except httpx.HTTPStatusError as e:
        print(f"Error response from GitHub API: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        print(f"Unexpected error fetching commits: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Update the score_commit_with_llm function to use the updated ChatCompletion API format:
async def score_commit_with_llm(message, additions, deletions, added_files, modified_files, deleted_files):
    """
    Score a commit using GPT-4.1 Nano to evaluate its quality and determine its types.
    
    Returns:
        dict: A dictionary containing OverallCodeQuality (float) and CommitTypeSet (list)
    """
    # Prepare a summary of file changes for the LLM
    file_changes_summary = []
    for file in added_files:
        file_changes_summary.append(f"Added: {file}")
    for file in modified_files:
        file_changes_summary.append(f"Modified: {file}")
    for file in deleted_files:
        file_changes_summary.append(f"Deleted: {file}")
    
    diff_summary = "\n".join(file_changes_summary)
    diff_summary += f"\nTotal lines added: {additions}\nTotal lines removed: {deletions}"
    
    # Define the function schema for function calling
    functions = [
        {
            "name": "commit_classification",
            "description": "Classify a commit based on its message and changes",
            "parameters": {
                "type": "object",
                "properties": {
                    "OverallCodeQuality": {
                        "type": "number",
                        "description": "A score between 0 and 1 indicating the overall quality of the commit based on effort, code quality, and documentation"
                    },
                    "feat": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit adds a new feature"
                    },
                    "fix": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit fixes a bug"
                    },
                    "docs": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit changes documentation only"
                    },
                    "style": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit makes code formatting changes with no logic changes"
                    },
                    "refactor": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit refactors code without adding features or fixing bugs"
                    },
                    "perf": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit improves performance"
                    },
                    "test": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit adds or modifies tests"
                    },
                    "chore": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit makes routine changes like config or metadata"
                    },
                    "build": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit changes build system or dependencies"
                    },
                    "ci": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit makes CI/CD changes"
                    },
                    "revert": {
                        "type": "number",
                        "description": "Confidence score (0 to 1) for whether this commit reverts previous commits"
                    }
                },
                "required": ["OverallCodeQuality", "feat", "fix", "docs", "style", "refactor", 
                           "perf", "test", "chore", "build", "ci", "revert"]
            }
        }
    ]
    
    # Prepare the prompt for the LLM
    prompt = f"""You are a commit classification engine that analyzes Git commit messages and diffs to determine the functional purpose of the commit and assess its overall quality.

    Your task:
    1. Analyze the commit message and code diff information provided.
    2. Assign a confidence score (0 to 1) for each category.
    3. Assign an OverallCodeQuality score (0 to 1) based on:
    - The effort needed to make the code changes
    - Quality and clarity of the code
    - Completeness of documentation
    - Adherence to best practices
    - Complexity and scope of the changes

    Available categories are:
    - feat: A new feature
    - fix: A bug fix
    - docs: Documentation only changes
    - style: Code formatting, no logic changes
    - refactor: Code changes that neither fix a bug nor add a feature
    - perf: Performance improvements
    - test: Adding or modifying tests
    - chore: Routine changes like config or metadata
    - build: Build system or dependency changes
    - ci: Continuous integration/deployment changes
    - revert: Reverting previous commits

    Input:
    - Commit Message: "{message}"
    - Commit Diff Summary:
    {diff_summary}

    IMPORTANT: You must respond using the commit_classification function provided to you. Include every field mentioned in the output. Your output must follow this exact structure:
    {{
    "OverallCodeQuality": 0.XX, // A score between 0 and 1
    "feat": 0.XX, // Score for feature changes
    "fix": 0.XX, // Score for bug fixes
    "docs": 0.XX, // And so on for each category
    ...
    }}

    Make sure every category has a value, and all values are decimal numbers between 0 and 1.
    """
    
    try:
        # Updated OpenAI API call to use the client, not the deprecated acreate method
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = client.chat.completions.create(
            model="gpt-4.1-nano",  # Replace with the actual model name if different
            messages=[
                {"role": "system", "content": "You are a commit classification engine that provides accurate and consistent assessments."},
                {"role": "user", "content": prompt}
            ],
            functions=functions,
            function_call={"name": "commit_classification"}
        )
        
        # Extract the function call arguments (updated for new API format)
        function_call = response.choices[0].message.function_call
        if function_call:
            function_args = json.loads(function_call.arguments)
            
            # Get the overall code quality score
            overall_quality = function_args.get("OverallCodeQuality", 0.5)
            
            # For CommitTypeSet, we'll include any category with a score >= 0.6
            threshold = 0.6
            commit_types = []
            
            categories = {
                "feat": "FEATURE",
                "fix": "BUG_FIX",
                "docs": "DOCUMENTATION",
                "style": "STYLE",
                "refactor": "REFACTORING",
                "perf": "PERFORMANCE",
                "test": "TESTING",
                "chore": "MAINTENANCE",
                "build": "BUILD",
                "ci": "CI_CD",
                "revert": "REVERT"
            }
            
            for category, enum_value in categories.items():
                if function_args.get(category, 0) >= threshold:
                    commit_types.append(enum_value)
            
            # If no category meets the threshold, add GENERAL
            if not commit_types:
                commit_types.append("GENERAL")
            
            return {
                "OverallCodeQuality": overall_quality,
                "CommitTypeSet": commit_types,
                # Include the raw scores for debugging or more granular usage
                "RawScores": {k: v for k, v in function_args.items() if k != "OverallCodeQuality"}
            }
        
        # Fallback if function calling failed
        return {
            "OverallCodeQuality": 0.5,
            "CommitTypeSet": ["GENERAL"],
            "RawScores": {}
        }
    
    except Exception as e:
        print(f"Error calling LLM API: {str(e)}")
        # Provide a fallback response in case of errors
        return {
            "OverallCodeQuality": 0.5,
            "CommitTypeSet": ["GENERAL"],
            "Error": str(e)
        }

@router.get("/repo/developer-quality-scores")
async def get_developer_quality_scores(
    repo: str = Query(..., description="Format: username/repository")
):
    """
    Get the sum of code quality scores for each developer in a repository.
    
    Returns a list of developers sorted by their total quality score (highest first).
    """
    try:
        # Create a Cypher query to sum quality scores per developer
        query = """
        MATCH (c:Commit)-[:BELONGS_TO]->(r:Repository {name: $repo_name})
        MATCH (c)-[:COMMITTED_BY]->(d:Developer)
        WITH d, SUM(c.overall_code_quality) AS total_quality_score, COUNT(c) AS commit_count
        RETURN d.name AS developer_name, 
               d.github AS github_username, 
               d.email AS email,
               total_quality_score,
               commit_count
        ORDER BY total_quality_score DESC
        """
        
        # Execute the query in a separate thread to avoid blocking
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            _execute_neo4j_query,
            query,
            {"repo_name": repo}
        )
        
        # Format the results
        developer_scores = []
        for record in results:
            developer_scores.append({
                "name": record["developer_name"],
                "github": record["github_username"],
                "email": record["email"],
                "total_quality_score": record["total_quality_score"],
                "commit_count": record["commit_count"],
                "average_quality": round(record["total_quality_score"] / record["commit_count"], 2) if record["commit_count"] > 0 else 0
            })
        
        return {
            "repository": repo,
            "developer_scores": developer_scores
        }
    
    except Exception as e:
        print(f"Error getting developer quality scores: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving developer scores: {str(e)}")


def _execute_neo4j_query(query, params=None):
    """Helper function to execute a Neo4j query and return results"""
    driver = get_db_driver()
    try:
        with driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    finally:
        driver.close()

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

