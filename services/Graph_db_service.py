import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from neo4j import GraphDatabase, Driver, Session

load_dotenv()

def process_commit(commit, driver, repository_info):
    """Process a commit with repository context"""
    with driver.session() as session:
        # Create or update repository node
        _create_repository(session, repository_info)
        
        # Create other entities with repository context
        _create_developer(session, commit["author"], repository_info["name"])
        _create_commit(session, commit, repository_info["name"])
        
        # Create relationships
        _link_commit_to_developer(session, commit, repository_info["name"])
        _handle_file_relationships(session, commit, "added_files", "ADDED", repository_info["name"])
        _handle_file_relationships(session, commit, "modified_files", "MODIFIED", repository_info["name"])
        _handle_file_relationships(session, commit, "deleted_files", "DELETED", repository_info["name"])


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