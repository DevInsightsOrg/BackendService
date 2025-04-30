import os

def get_github_headers():
    """
    Returns authorization headers for GitHub API using a personal access token.
    You must set the GITHUB_TOKEN environment variable.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("Missing GITHUB_TOKEN in environment variables.")
    return {"Authorization": f"Bearer {token}"}
