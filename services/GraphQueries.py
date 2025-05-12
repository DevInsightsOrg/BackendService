from neo4j import GraphDatabase
import os
from typing import Dict, List, Any, Optional
from datetime import datetime


class GraphQueries:
    """
    Utility class that encapsulates Neo4j graph database queries for developer insights.
    """
    
    def __init__(self, uri: str, username: str, password: str):
        """
        Initialize the Neo4j driver with connection details.
        
        Args:
            uri: The Neo4j connection URI
            username: Neo4j database username
            password: Neo4j database password
        """
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        
    def close(self):
        """Close the database driver connection."""
        self.driver.close()
        
    def get_jacks(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find developers with broad knowledge (Jacks) based on file coverage.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of developers to return
            
        Returns:
            List of developers sorted by decreasing file coverage
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (d:Developer)-[:BELONGS_TO]->(r)
                MATCH (f:File)-[:BELONGS_TO]->(r)

                // Count total files in the repository
                WITH r, d, count(f) as total_files

                // Find all files that each developer can reach through their commits
                OPTIONAL MATCH path = (d)<-[:COMMITTED_BY]-(c:Commit)-[:ADDED|MODIFIED|DELETED]->(reachable_file:File)
                WHERE length(path) <= 10
                // The distance threshold of 10 mentioned in the paper

                WITH d, r, total_files, COUNT(DISTINCT reachable_file) as files_touched

                // Calculate file coverage (percentage of repo files the developer knows)
                WITH d, r, total_files, files_touched, 
                     toFloat(files_touched) / total_files as file_coverage

                // Order by file coverage to identify the broadest knowledge developers
                RETURN 
                    d.github as github,
                    d.name as name,
                    d.email as email,
                    files_touched as files_reached,
                    total_files as total_files,
                    file_coverage as knowledge_breadth
                ORDER BY knowledge_breadth DESC
                LIMIT $limit
            """, repo_name=repo_name, limit=limit)
            
            return [dict(record) for record in result]
        
    def get_mavens(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Identify mavens by directly using the critical files approach.
        
        This implementation first finds files with single contributors (critical files),
        then identifies the developers who are those sole contributors.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of developers to return
            
        Returns:
            List of mavens sorted by decreasing mavenness score
        """
        with self.driver.session() as session:
            # First, find all critical files (files with a single contributor)
            critical_files_result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (f:File)-[:BELONGS_TO]->(r)
                
                // Find all developers who contributed to this file
                OPTIONAL MATCH (c:Commit)-[:ADDED|MODIFIED|DELETED]->(f)
                OPTIONAL MATCH (c)-[:COMMITTED_BY]->(d:Developer)
                
                WITH f, count(DISTINCT d) as contributor_count
                WHERE contributor_count = 1
                
                // Find who that single contributor is
                MATCH (c:Commit)-[:ADDED|MODIFIED|DELETED]->(f)
                MATCH (c)-[:COMMITTED_BY]->(sole_contributor:Developer)
                
                RETURN 
                    f.path as file_path,
                    sole_contributor.github as github
            """, repo_name=repo_name)
            
            # Build a map of developer to their critical files
            dev_to_files = {}
            for record in critical_files_result:
                github = record["github"]
                file_path = record["file_path"]
                
                if github not in dev_to_files:
                    dev_to_files[github] = []
                
                dev_to_files[github].append(file_path)
            
            # Get the total number of files for calculating mavenness
            file_count_result = session.run("""
                MATCH (f:File)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                RETURN count(f) as total_files
            """, repo_name=repo_name)
            
            total_files = file_count_result.single()["total_files"]
            
            # Get developer details and build the maven results
            maven_results = []
            for github, files in dev_to_files.items():
                # Get developer details
                dev_result = session.run("""
                    MATCH (d:Developer {github: $github})-[:BELONGS_TO]->(:Repository {name: $repo_name})
                    RETURN d.name as name, d.email as email
                """, github=github, repo_name=repo_name)
                
                dev_record = dev_result.single()
                
                # Calculate mavenness score
                rare_files_count = len(files)
                mavenness = float(rare_files_count) / total_files
                
                maven_results.append({
                    "github": github,
                    "name": dev_record["name"] if dev_record and "name" in dev_record else None,
                    "email": dev_record["email"] if dev_record and "email" in dev_record else None,
                    "rare_files_count": rare_files_count,
                    "mavenness": mavenness
                })
            
            # Sort by mavenness score and limit results
            maven_results.sort(key=lambda x: x["mavenness"], reverse=True)
            return maven_results[:limit]
        
    def get_connectors(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find developers who connect different parts of the project (Connectors) based on 
        a simplified centrality measure in the developer collaboration network.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of developers to return
            
        Returns:
            List of connectors sorted by decreasing centrality
        """
        with self.driver.session() as session:
            result = session.run("""
                // Get all developers in the repository
                MATCH (d:Developer)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                
                // Calculate a simplified centrality measure:
                // How many other developers this developer collaborates with,
                // weighted by the number of shared files
                OPTIONAL MATCH (d)<-[:COMMITTED_BY]-(c1:Commit)
                OPTIONAL MATCH (c1)-[:ADDED|MODIFIED|DELETED]->(f:File)<-[:ADDED|MODIFIED|DELETED]-(c2:Commit)
                OPTIONAL MATCH (c2)-[:COMMITTED_BY]->(other:Developer)
                WHERE d <> other AND other.repository = $repo_name
                
                // Calculate number of unique collaborators and total collaboration strength
                WITH d, 
                    count(DISTINCT other) as collaborator_count,
                    count(DISTINCT f) as shared_file_count
                
                // Calculate a centrality score: collaborator count * shared file count
                WITH d, 
                    collaborator_count,
                    shared_file_count,
                    collaborator_count * shared_file_count as centrality_score
                
                RETURN 
                    d.github as github,
                    d.name as name,
                    d.email as email,
                    collaborator_count as collaborator_count,
                    shared_file_count as shared_file_count,
                    centrality_score as betweenness_centrality
                ORDER BY betweenness_centrality DESC
                LIMIT $limit
            """, repo_name=repo_name, limit=limit)
            
            connector_records = list(result)
            return [record.data() for record in connector_records]
        
    def get_replacements(self, repo_name: str, leaving_github: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Find potential replacements for a leaving developer based on overlapping knowledge.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            leaving_github: GitHub username of the leaving developer
            limit: Maximum number of replacements to recommend
            
        Returns:
            List of recommended replacements sorted by decreasing knowledge overlap
        """
        with self.driver.session() as session:
            result = session.run("""
                // Find replacement recommendations for a leaving developer
                MATCH (leaving:Developer {github: $leaving_github, repository: $repo_name})

                // Find all files this developer can reach
                MATCH path = (leaving)<-[:COMMITTED_BY]-(c:Commit)-[:ADDED|MODIFIED|DELETED]->(leaving_files:File)
                WHERE leaving_files.repository = $repo_name AND length(path) <= 10
                WITH leaving, collect(DISTINCT leaving_files) as leaving_dev_files

                // Find all other developers in the repository
                MATCH (other:Developer)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                WHERE other.github <> $leaving_github

                // Find files these developers can reach
                MATCH path = (other)<-[:COMMITTED_BY]-(c:Commit)-[:ADDED|MODIFIED|DELETED]->(other_files:File)
                WHERE other_files.repository = $repo_name AND length(path) <= 10
                WITH leaving, leaving_dev_files, other, collect(DISTINCT other_files) as other_dev_files

                // Calculate overlapping knowledge
                WITH leaving, other, leaving_dev_files, other_dev_files,
                    [f IN other_dev_files WHERE f IN leaving_dev_files] as overlapping_files
                    
                // Calculate the replacement score (% of leaving developer's files known by the other dev)
                WITH leaving, other, 
                    size(leaving_dev_files) as leaving_knowledge,
                    size(overlapping_files) as shared_knowledge,
                    toFloat(size(overlapping_files)) / size(leaving_dev_files) as knowledge_overlap

                RETURN 
                    other.github as github,  // Changed from recommended_replacement to github
                    other.name as name,
                    other.email as email,
                    leaving_knowledge as leaving_dev_file_count,
                    shared_knowledge as shared_file_count,
                    knowledge_overlap as overlap_ratio
                ORDER BY overlap_ratio DESC
                LIMIT $limit
            """, repo_name=repo_name, leaving_github=leaving_github, limit=limit)
            
            replacement_records = list(result)
            return [record.data() for record in replacement_records]
        
    def get_knowledge_distribution(self, repo_name: str) -> Dict[str, Any]:
        """
        Analyze knowledge distribution to determine if the project is hero-based or balanced.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            
        Returns:
            Dictionary with knowledge distribution metrics and classification
        """
        with self.driver.session() as session:
            result = session.run("""
                // Evaluating knowledge distribution - balanced vs hero team
                MATCH (r:Repository {name: $repo_name})
                MATCH (d:Developer)-[:BELONGS_TO]->(r)
                
                // Count total files in repository
                WITH r, count(d) as dev_count
                MATCH (f:File)-[:BELONGS_TO]->(r)
                WITH r, dev_count, count(f) as total_files
                
                // Find files each developer can reach
                MATCH (d:Developer)-[:BELONGS_TO]->(r)
                OPTIONAL MATCH path = (d)<-[:COMMITTED_BY]-(c:Commit)-[:ADDED|MODIFIED|DELETED]->(reachable_file:File)
                WHERE length(path) <= 10
                
                WITH d, r, dev_count, total_files, 
                    COUNT(DISTINCT reachable_file) as files_touched
                
                // Calculate file coverage for each developer
                WITH d.github AS github, d.name AS name, 
                    toFloat(files_touched) / total_files as coverage,
                    dev_count, total_files
                
                // Collect all coverage values to calculate distribution statistics
                WITH collect(coverage) as coverage_values,
                    collect({github: github, name: name, coverage: coverage}) as developers,
                    dev_count, total_files
                
                // Calculate distribution statistics
                WITH developers, coverage_values, dev_count, total_files,
                    reduce(max = 0.0, cov IN coverage_values | 
                        CASE WHEN cov > max THEN cov ELSE max END) as max_coverage,
                    CASE WHEN size(coverage_values) > 0 
                        THEN reduce(sum = 0.0, cov IN coverage_values | sum + cov) / size(coverage_values) 
                        ELSE 0.0 END as average_coverage,
                    CASE WHEN size(coverage_values) > 0 
                        THEN sqrt(reduce(sum = 0.0, cov IN coverage_values | 
                            sum + ((cov - (reduce(s = 0.0, c IN coverage_values | s + c) / size(coverage_values))) ^ 2)
                        ) / size(coverage_values))
                        ELSE 0.0 END as coverage_std_dev
                    
                // Sort coverage values for percentile calculation
                WITH developers, coverage_values, dev_count, total_files,
                    max_coverage, average_coverage, coverage_std_dev,
                    apoc.coll.sort(coverage_values) as sorted_coverages
                
                // Calculate skewness manually
                WITH developers, coverage_values, dev_count, total_files,
                    sorted_coverages, max_coverage, average_coverage, coverage_std_dev,
                    CASE 
                        WHEN coverage_std_dev > 0
                        THEN reduce(s = 0.0, cov IN coverage_values | 
                            s + ((cov - average_coverage) / coverage_std_dev) ^ 3
                        ) / size(coverage_values)
                        ELSE 0 
                    END as skewness
                
                // Get top contributor (developer with highest coverage)
                WITH developers, coverage_values, dev_count, total_files,
                    sorted_coverages, max_coverage, average_coverage, coverage_std_dev, skewness,
                    [d in developers WHERE d.coverage = max_coverage] as top_devs
                
                // Return knowledge distribution metrics
                RETURN 
                    CASE WHEN size(top_devs) > 0 THEN top_devs[0].github ELSE 'unknown' END as top_contributor,
                    max_coverage as top_coverage,
                    average_coverage,
                    coverage_std_dev,
                    skewness,
                    dev_count,
                    total_files,
                    
                    // Classify knowledge distribution
                    CASE
                        WHEN skewness > 1.0 OR max_coverage > (3 * average_coverage)
                        THEN 'hero' // Right-skewed distribution or top contributor has too much knowledge
                        ELSE 'balanced' // Normal or uniform distribution
                    END as distribution_type
            """, repo_name=repo_name)
            
            record = result.single()
            if record is None:
                return {
                    "top_contributor": "unknown",
                    "top_coverage": 0.0,
                    "average_coverage": 0.0,
                    "coverage_std_dev": 0.0,
                    "skewness": 0.0,
                    "dev_count": 0,
                    "total_files": 0,
                    "distribution_type": "unknown"
                }
                
            return record.data()
        
    def get_developer_contributions(self, repo_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get comprehensive contribution metrics for developers.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of developers to return
            
        Returns:
            List of developers with their contribution metrics
        """
        with self.driver.session() as session:
            result = session.run("""
                // Get comprehensive contribution metrics
                MATCH (r:Repository {name: $repo_name})
                MATCH (d:Developer)-[:BELONGS_TO]->(r)

                // Count commits
                OPTIONAL MATCH (c:Commit)-[:COMMITTED_BY]->(d)
                WITH d, r, count(c) as commit_count

                // Count files touched
                OPTIONAL MATCH (c:Commit)-[:COMMITTED_BY]->(d)
                OPTIONAL MATCH (c)-[:ADDED|MODIFIED|DELETED]->(f:File)
                WITH d, r, commit_count, count(DISTINCT f) as files_touched

                // Get total files in repo for coverage calculation
                MATCH (allFiles:File)-[:BELONGS_TO]->(r)
                WITH d, r, commit_count, files_touched, count(allFiles) as total_files

                // Calculate file coverage 
                WITH d, r, commit_count, files_touched, total_files,
                     toFloat(files_touched) / total_files as file_coverage

                RETURN 
                    d.github as github,
                    d.name as name,
                    d.email as email,
                    commit_count as commits,
                    files_touched as files_touched,
                    total_files as total_files,
                    file_coverage as knowledge_breadth
                ORDER BY file_coverage DESC
                LIMIT $limit
            """, repo_name=repo_name, limit=limit)
            
            return [dict(record) for record in result]
        
    def get_developer_collaborations(self, repo_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Analyze developer collaborations through shared files.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of collaborations to return
            
        Returns:
            List of developer pairs and their collaboration strength
        """
        with self.driver.session() as session:
            result = session.run("""
                // Analyze developer collaborations through shared files
                MATCH (r:Repository {name: $repo_name})
                MATCH (d1:Developer)-[:BELONGS_TO]->(r)
                MATCH (d2:Developer)-[:BELONGS_TO]->(r)
                WHERE id(d1) < id(d2) // Prevent duplicates

                // Find files these developers have both worked on
                MATCH (c1:Commit)-[:COMMITTED_BY]->(d1)
                MATCH (c2:Commit)-[:COMMITTED_BY]->(d2)
                MATCH (c1)-[:ADDED|MODIFIED|DELETED]->(f:File)<-[:ADDED|MODIFIED|DELETED]-(c2)

                WITH d1, d2, count(DISTINCT f) as shared_files
                WHERE shared_files > 0

                RETURN 
                    d1.github as developer1,
                    d1.name as name1,
                    d2.github as developer2,
                    d2.name as name2,
                    shared_files as collaboration_strength
                ORDER BY collaboration_strength DESC
                LIMIT $limit
            """, repo_name=repo_name, limit=limit)
            
            return [dict(record) for record in result]
        
    def get_critical_files(self, repo_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Identify critical files based on who can reach them.
        
        Args:
            repo_name: Repository name (e.g., "username/repo")
            limit: Maximum number of files to return
            
        Returns:
            List of files ordered by increasing number of contributors (most critical first)
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (f:File)-[:BELONGS_TO]->(r)
                
                // Find all developers who contributed to this file
                OPTIONAL MATCH (c:Commit)-[:ADDED|MODIFIED|DELETED]->(f)
                OPTIONAL MATCH (c)-[:COMMITTED_BY]->(d:Developer)
                
                WITH f, count(DISTINCT d) as contributor_count
                
                RETURN 
                    f.path as file_path,
                    f.filename as filename,
                    contributor_count as contributors
                ORDER BY contributor_count
                LIMIT $limit
            """, repo_name=repo_name, limit=limit)
            
            return [dict(record) for record in result]