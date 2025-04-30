from fastapi import FastAPI, HTTPException, Query
import httpx
import os
from typing import List
import asyncio
from utils.github_auth import get_github_headers  # Adjust import to your project
from urllib.parse import parse_qs, urlparse

app = FastAPI(title="DevInsights GitHub API")

GITHUB_API_BASE = "https://api.github.com"

# Utility to get GitHub headers
def get_github_headers():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise Exception("GitHub token not found.")
    return {"Authorization": f"Bearer {token}"}

# Route: GET /commits
@app.get("/commits")
async def fetch_commits(
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
            response.raise_for_status()
            raw_commits = response.json()

        commits = []
        for c in raw_commits:
            commits.append({
                "sha": c.get("sha"),
                "author": c.get("commit", {}).get("author", {}).get("name"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
                "message": c.get("commit", {}).get("message"),
                "url": c.get("html_url")
            })

        return {"repository": repo, "branch": branch, "commits": commits}

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/commit/{sha}/files")
async def get_diff_files(repo: str, sha: str):
    """
    Get list of files changed in a specific commit.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{sha}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            commit_data = resp.json()
            files = commit_data.get("files", [])
            return [{
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "changes": f["changes"]
            } for f in files]
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"GitHub API error: {str(e)}")

@app.get("/pulls")
async def fetch_pull_requests(repo: str, state: str = "all"):
    """
    Fetch pull requests from a GitHub repo (open, closed, all).
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls?state={state}&per_page=100"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/issues")
async def fetch_issues(repo: str, state: str = "all"):
    """
    Fetch issues from a GitHub repo.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues?state={state}&per_page=100"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reviews")
async def fetch_reviews(repo: str, pr_number: int):
    """
    Fetch code reviews for a specific pull request.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/contributors")
async def fetch_contributors(repo: str):
    """
    Fetch contributor info for a GitHub repo.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/contributors"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=get_github_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/repo")
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

@app.get("/sync")
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

@app.get("/repo/{owner}/{repo}/stats")
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

@app.get("/commit/{sha}/details")
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
