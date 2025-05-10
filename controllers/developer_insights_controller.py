from fastapi import FastAPI, HTTPException, Depends, Query, APIRouter
from typing import List, Dict, Any, Optional
import os
from pydantic import BaseModel
from services.GraphQueries import GraphQueries

# Neo4j connection settings from environment variables
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

router = APIRouter()

def get_graph_queries():
    """Dependency to get a GraphQueries instance"""
    queries = GraphQueries(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)
    try:
        yield queries
    finally:
        queries.close()

# Response models
class Developer(BaseModel):
    github: str
    name: Optional[str] = None
    email: Optional[str] = None

class Jack(Developer):
    files_reached: int
    total_files: int
    knowledge_breadth: float

class Maven(Developer):
    rare_files_count: int
    mavenness: float

class Connector(Developer):
    betweenness_centrality: float

class Replacement(BaseModel):
    github: str  # Change from the Developer inheritance
    name: Optional[str] = None
    email: Optional[str] = None
    leaving_dev_file_count: int
    shared_file_count: int
    overlap_ratio: float

class KnowledgeDistribution(BaseModel):
    top_contributor: str
    top_coverage: float
    average_coverage: float
    coverage_std_dev: float
    skewness: float
    distribution_type: str

class DeveloperContribution(Developer):
    commits: int
    files_touched: int
    total_files: int
    knowledge_breadth: float

class DeveloperCollaboration(BaseModel):
    developer1: str
    name1: Optional[str] = None
    developer2: str
    name2: Optional[str] = None
    collaboration_strength: int

class CriticalFile(BaseModel):
    file_path: str
    filename: str
    contributors: int

# API Routes
@router.get("/api/repos/{owner}/{repo}/key-developers/jacks", response_model=List[Jack])
async def get_jacks(
    owner: str, 
    repo: str, 
    limit: int = Query(10, description="Maximum number of developers to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get developers with broad knowledge (Jacks) based on file coverage."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_jacks(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving jacks: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/key-developers/mavens", response_model=List[Maven])
async def get_mavens(
    owner: str, 
    repo: str,  
    limit: int = Query(10, description="Maximum number of developers to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get developers with deep expertise in specific areas (Mavens)."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_mavens(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving mavens: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/key-developers/connectors", response_model=List[Connector])
async def get_connectors(
    owner: str, 
    repo: str,  
    limit: int = Query(10, description="Maximum number of developers to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get developers who connect different parts of the codebase (Connectors)."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_connectors(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving connectors: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/developers/{github}/replacements", response_model=List[Replacement])
async def get_replacements(
    owner: str, 
    repo: str, 
    github: str,
    limit: int = Query(3, description="Maximum number of replacements to recommend"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get recommended replacements for a leaving developer."""
    repo_name = f"{owner}/{repo}"
    try:
        replacements = queries.get_replacements(repo_name, github, limit)
        if not replacements:
            raise HTTPException(status_code=404, detail=f"Developer {github} not found or has no replacements")
        return replacements
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding replacements: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/knowledge-distribution", response_model=KnowledgeDistribution)
async def get_knowledge_distribution(
    owner: str, 
    repo: str, 
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Analyze the knowledge distribution in the team (balanced vs. hero-based)."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_knowledge_distribution(repo_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing knowledge distribution: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/developers/contributions", response_model=List[DeveloperContribution])
async def get_developer_contributions(
    owner: str, 
    repo: str, 
    limit: int = Query(50, description="Maximum number of developers to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get comprehensive contribution metrics for all developers."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_developer_contributions(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving developer contributions: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/collaborations", response_model=List[DeveloperCollaboration])
async def get_developer_collaborations(
    owner: str, 
    repo: str, 
    limit: int = Query(20, description="Maximum number of collaborations to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get collaboration metrics between developers based on shared files."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_developer_collaborations(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving developer collaborations: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/critical-files", response_model=List[CriticalFile])
async def get_critical_files(
    owner: str, 
    repo: str, 
    limit: int = Query(20, description="Maximum number of files to return"),
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get critical files based on the number of contributors who can reach them."""
    repo_name = f"{owner}/{repo}"
    try:
        return queries.get_critical_files(repo_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving critical files: {str(e)}")

@router.get("/api/repos/{owner}/{repo}/summary")
async def get_repo_summary(
    owner: str, 
    repo: str, 
    queries: GraphQueries = Depends(get_graph_queries)
):
    """Get a summary of the repository with key metrics."""
    repo_name = f"{owner}/{repo}"
    try:
        # Get top developers from each category
        jacks = queries.get_jacks(repo_name, 3)
        mavens = queries.get_mavens(repo_name, 3)
        connectors = queries.get_connectors(repo_name, 3)
        knowledge_dist = queries.get_knowledge_distribution(repo_name)
        
        # Return summary
        return {
            "repository": repo_name,
            "knowledge_distribution": knowledge_dist["distribution_type"],
            "top_contributor": knowledge_dist["top_contributor"],
            "top_jacks": [{"github": dev["github"], "knowledge_breadth": dev["knowledge_breadth"]} for dev in jacks],
            "top_mavens": [{"github": dev["github"], "mavenness": dev["mavenness"]} for dev in mavens],
            "top_connectors": [{"github": dev["github"], "centrality": dev["betweenness_centrality"]} for dev in connectors]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving repository summary: {str(e)}")
