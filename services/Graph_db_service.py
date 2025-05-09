# services/Graph_db_service.py
import os
from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv
import asyncio

load_dotenv()

# Neo4j connection
def get_db_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(username, password))

async def process_commit_data(
    sha: str, 
    author_name: str,
    author_email: str,
    author_github: str,
    date: str,
    message: str,
    added_files: list = None,
    modified_files: list = None,
    deleted_files: list = None,
    repository_info: dict = None
):
    """Process a commit with repository context using individual fields"""
    if not repository_info:
        return
        
    # Make the database operations run in a separate thread to not block
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, 
        _process_commit_sync,
        sha, 
        author_name,
        author_email,
        author_github,
        date,
        message,
        added_files or [],
        modified_files or [],
        deleted_files or [],
        repository_info
    )

def _process_commit_sync(
    sha, 
    author_name,
    author_email,
    author_github,
    date,
    message,
    added_files,
    modified_files,
    deleted_files,
    repository_info
):
    """Synchronous version to run in executor"""
    driver = get_db_driver()
    try:
        with driver.session() as session:
            # Create or update repository node
            _create_repository(session, repository_info)
            
            # Create developer entity
            author = {
                "name": author_name,
                "email": author_email,
                "github": author_github or "unknown"  # Ensure we always have a value
            }
            _create_developer(session, author, repository_info["name"])
            
            # Create commit entity
            commit_data = {
                "hash": sha,
                "timestamp": date,
                "message": message,
                "author": author
            }
            _create_commit(session, commit_data, repository_info["name"])
            
            # Create relationships
            _link_commit_to_developer(session, commit_data, repository_info["name"])
            
            # Process file relationships
            if added_files:
                _handle_file_relationships(session, {"hash": sha, "added_files": added_files}, 
                                         "added_files", "ADDED", repository_info["name"])
            if modified_files:
                _handle_file_relationships(session, {"hash": sha, "modified_files": modified_files}, 
                                         "modified_files", "MODIFIED", repository_info["name"])
            if deleted_files:
                _handle_file_relationships(session, {"hash": sha, "deleted_files": deleted_files}, 
                                         "deleted_files", "DELETED", repository_info["name"])
    finally:
        driver.close()

def _create_repository(session, repo_info):
    session.run("""
        MERGE (r:Repository {name: $name})
        SET r.url = $url,
            r.description = $description
    """, name=repo_info["name"], url=repo_info["url"], description=repo_info.get("description", ""))


def _create_developer(session, author, repo_name):
    """Create a developer node specific to this repository"""
    session.run("""
        MERGE (d:Developer {github: $github, repository: $repo_name})
        SET d.name = $name, 
            d.email = $email
        WITH d
        MATCH (r:Repository {name: $repo_name})
        MERGE (d)-[:BELONGS_TO]->(r)
    """, 
    github=author["github"], 
    name=author["name"], 
    email=author["email"],
    repo_name=repo_name)


def _create_commit(session, commit, repo_name):
    session.run("""
        MERGE (c:Commit {hash: $hash})
        SET c.timestamp = datetime($timestamp), 
            c.message = $message
        WITH c
        MATCH (r:Repository {name: $repo_name})
        MERGE (c)-[:BELONGS_TO]->(r)
    """, hash=commit["hash"], timestamp=commit["timestamp"], message=commit["message"], repo_name=repo_name)


def _link_commit_to_developer(session, commit, repo_name):
    session.run("""
        MATCH (d:Developer {github: $github, repository: $repo_name}), 
              (c:Commit {hash: $hash})
        MERGE (c)-[:COMMITTED_BY]->(d)
    """, github=commit["author"]["github"], hash=commit["hash"], repo_name=repo_name)


def _handle_file_relationships(session, commit, file_key, relation_type, repo_name):
    for file_path in commit.get(file_key, []):
        # Create file node with repository context
        session.run("""
            MERGE (f:File {path: $path, repository: $repo_name})
            SET f.filename = $filename
            WITH f
            MATCH (r:Repository {name: $repo_name})
            MERGE (f)-[:BELONGS_TO]->(r)
            WITH f
            MATCH (c:Commit {hash: $hash})
            MERGE (c)-[:%s]->(f)
        """ % relation_type, 
        path=file_path, 
        filename=file_path.split("/")[-1], 
        hash=commit["hash"],
        repo_name=repo_name)