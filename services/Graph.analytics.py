import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from neo4j import GraphDatabase, Driver, Session
from typing import Dict, List, Any

load_dotenv()

class RepositoryAnalytics:
    def __init__(self, driver: Driver):
        self.driver = driver
        
    def get_repository_summary(self, repo_name: str) -> Dict[str, Any]:
        """Get a summary of repository metrics"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                OPTIONAL MATCH (d:Developer)-[:BELONGS_TO]->(r)
                OPTIONAL MATCH (c:Commit)-[:BELONGS_TO]->(r)
                OPTIONAL MATCH (f:File)-[:BELONGS_TO]->(r)
                RETURN 
                    r.name as name,
                    r.url as url,
                    count(DISTINCT d) as developers,
                    count(DISTINCT c) as commits,
                    count(DISTINCT f) as files
            """, repo_name=repo_name)
            return result.single().data()
            
    # 1. Key Developers Categorization
    
    def get_jack_developers(self, repo_name: str, min_file_coverage: float = 0.3) -> List[Dict[str, Any]]:
        """
        Get 'Jack' developers - those with broad knowledge across many files
        
        Args:
            repo_name: Repository name
            min_file_coverage: Minimum percentage of repo files the developer must have touched
        """
        with self.driver.session() as session:
            result = session.run("""
                // Get total number of files in repo
                MATCH (r:Repository {name: $repo_name})
                MATCH (f:File)-[:BELONGS_TO]->(r)
                WITH r, count(f) as total_files
                
                // Get developers and the number of files they've touched
                MATCH (d:Developer)-[:BELONGS_TO]->(r)
                OPTIONAL MATCH (c:Commit)-[:COMMITTED_BY]->(d)
                OPTIONAL MATCH (c)-[rel:ADDED|MODIFIED|DELETED]->(f:File)
                WITH d, r, total_files, count(DISTINCT f) as files_touched
                
                // Calculate coverage and filter for Jacks
                WITH d, r, total_files, files_touched, 
                     toFloat(files_touched) / total_files as coverage
                WHERE coverage >= $min_file_coverage
                
                RETURN 
                    d.github as github,
                    d.name as name,
                    d.email as email,
                    files_touched as files_touched,
                    total_files as total_files,
                    coverage as coverage
                ORDER BY coverage DESC
            """, repo_name=repo_name, min_file_coverage=min_file_coverage)
            
            return [record.data() for record in result]
            
    def get_maven_developers(self, repo_name: str, min_file_commits: int = 5) -> List[Dict[str, Any]]:
        """
        Get 'Maven' developers - those with deep expertise in specific files
        
        Args:
            repo_name: Repository name
            min_file_commits: Minimum number of commits to a file to be considered an expert
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (d:Developer)-[:BELONGS_TO]->(r)
                MATCH (c:Commit)-[:COMMITTED_BY]->(d)
                MATCH (c)-[rel:ADDED|MODIFIED|DELETED]->(f:File)
                
                // Count commits per developer per file
                WITH d, f, count(c) as commit_count
                WHERE commit_count >= $min_file_commits
                
                // Get total commits to this file
                MATCH (f)<-[rel:ADDED|MODIFIED|DELETED]-(allCommit:Commit)
                WITH d, f, commit_count, count(allCommit) as total_file_commits
                
                // Calculate expertise level (percentage of all commits to this file)
                WITH d, f, commit_count, total_file_commits,
                     toFloat(commit_count) / total_file_commits as expertise_level
                
                RETURN 
                    d.github as github,
                    d.name as name,
                    f.path as file_path,
                    commit_count as commits_to_file,
                    total_file_commits as total_file_commits,
                    expertise_level as expertise_level
                ORDER BY expertise_level DESC
            """, repo_name=repo_name, min_file_commits=min_file_commits)
            
            return [record.data() for record in result]
            
    def get_connector_developers(self, repo_name: str) -> List[Dict[str, Any]]:
        """
        Get 'Connector' developers - those who work across different parts of the codebase
        Measured by betweenness centrality in the file collaboration network
        """
        with self.driver.session() as session:
            # First create a temporary graph projection for centrality algorithms
            session.run("""
                CALL gds.graph.project.cypher(
                  'file_collaboration',
                  'MATCH (d:Developer)-[:BELONGS_TO]->({name: $repo_name}) RETURN id(d) AS id',
                  'MATCH (d1:Developer)-[:BELONGS_TO]->({name: $repo_name})
                   MATCH (d2:Developer)-[:BELONGS_TO]->({name: $repo_name})
                   MATCH (c1:Commit)-[:COMMITTED_BY]->(d1)
                   MATCH (c2:Commit)-[:COMMITTED_BY]->(d2)
                   MATCH (c1)-[:ADDED|MODIFIED|DELETED]->(f:File)<-[:ADDED|MODIFIED|DELETED]-(c2)
                   WHERE id(d1) < id(d2)
                   RETURN id(d1) AS source, id(d2) AS target, count(DISTINCT f) AS weight'
                )
            """, repo_name=repo_name)
            
            # Run betweenness centrality algorithm
            result = session.run("""
                CALL gds.betweenness.stream('file_collaboration')
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) AS developer, score
                WHERE developer.repository = $repo_name
                RETURN 
                    developer.github as github,
                    developer.name as name,
                    developer.email as email,
                    score as betweenness_centrality
                ORDER BY betweenness_centrality DESC
            """, repo_name=repo_name)
            
            # Drop the temporary graph
            session.run("CALL gds.graph.drop('file_collaboration')")
            
            return [record.data() for record in result]
    
    # 2. Developer Contribution Metrics
    
    def get_developer_contributions(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get comprehensive contribution metrics for all developers"""
        with self.driver.session() as session:
            result = session.run("""
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
                
                RETURN 
                    d.github as github,
                    d.name as name,
                    d.email as email,
                    commit_count as commits,
                    files_touched as files_touched,
                    total_files as total_files,
                    toFloat(files_touched) / total_files as file_coverage
                ORDER BY commits DESC
            """, repo_name=repo_name)
            
            return [record.data() for record in result]
    
    # 3. Replacement Recommendations
    
    def get_replacement_recommendations(self, repo_name: str, developer_github: str) -> List[Dict[str, Any]]:
        """
        Find developers who could replace a given developer based on shared file knowledge
        
        Args:
            repo_name: Repository name
            developer_github: GitHub username of the developer to find replacements for
        """
        with self.driver.session() as session:
            result = session.run("""
                // Get the files the target developer has worked on
                MATCH (target:Developer {github: $developer_github, repository: $repo_name})
                MATCH (c1:Commit)-[:COMMITTED_BY]->(target)
                MATCH (c1)-[:ADDED|MODIFIED|DELETED]->(f:File)
                WITH target, collect(f) as target_files
                
                // Find other developers and their overlap with target's files
                MATCH (other:Developer)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                WHERE other.github <> $developer_github
                
                OPTIONAL MATCH (c2:Commit)-[:COMMITTED_BY]->(other)
                OPTIONAL MATCH (c2)-[:ADDED|MODIFIED|DELETED]->(f:File)
                WHERE f IN target_files
                
                WITH other, target, target_files, 
                     collect(DISTINCT f) as shared_files
                
                // Calculate overlap percentage
                WITH other, target, target_files, shared_files,
                     size(shared_files) as shared_count,
                     size(target_files) as target_count,
                     toFloat(size(shared_files)) / size(target_files) as knowledge_overlap
                
                RETURN 
                    other.github as github,
                    other.name as name,
                    other.email as email,
                    target_count as target_developer_files,
                    shared_count as shared_files,
                    knowledge_overlap as knowledge_overlap
                ORDER BY knowledge_overlap DESC
            """, repo_name=repo_name, developer_github=developer_github)
            
            return [record.data() for record in result]
    
    # 4. Knowledge Distribution
    
    def get_knowledge_distribution(self, repo_name: str) -> Dict[str, Any]:
        """
        Analyze the knowledge distribution across the team to determine if the project
        is hero-based (imbalanced) or balanced
        """
        with self.driver.session() as session:
            result = session.run("""
                // Get all files in the repository
                MATCH (r:Repository {name: $repo_name})
                MATCH (f:File)-[:BELONGS_TO]->(r)
                
                // For each file, find the developer with the most commits
                OPTIONAL MATCH (c:Commit)-[:ADDED|MODIFIED|DELETED]->(f)
                OPTIONAL MATCH (c)-[:COMMITTED_BY]->(d:Developer)
                
                WITH f, d, count(c) as commit_count
                ORDER BY f, commit_count DESC
                WITH f, collect({developer: d.github, commits: commit_count})[0] as top_contributor
                
                // Calculate what percentage of files have the same top contributor
                WITH top_contributor.developer as top_dev, count(f) as file_count
                ORDER BY file_count DESC
                
                WITH collect({developer: top_dev, file_count: file_count}) as top_devs
                
                // Get total files for percentage calculation
                MATCH (f:File)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                WITH top_devs, count(f) as total_files
                
                // Calculate Gini coefficient to measure inequality
                MATCH (d:Developer)-[:BELONGS_TO]->(:Repository {name: $repo_name})
                OPTIONAL MATCH (c:Commit)-[:COMMITTED_BY]->(d)
                WITH top_devs, total_files, d, count(c) as commit_count
                ORDER BY commit_count
                
                WITH top_devs, total_files, 
                     collect(commit_count) as sorted_counts,
                     count(d) as dev_count,
                     sum(commit_count) as total_commits
                
                // Simplified Gini calculation
                WITH top_devs, total_files, sorted_counts, dev_count, total_commits,
                     CASE 
                        WHEN dev_count <= 1 THEN 0
                        ELSE apoc.coll.sum([i in range(0, size(sorted_counts)-1) | 
                             (i+1) * sorted_counts[i]]) * 2.0 / (dev_count * total_commits) - (dev_count + 1.0) / dev_count
                     END as gini_coefficient
                
                // Determine if project is hero-based or balanced
                RETURN 
                    top_devs[0].developer as top_contributor,
                    top_devs[0].file_count as files_owned,
                    total_files as total_files,
                    1.0 * top_devs[0].file_count / total_files as ownership_ratio,
                    gini_coefficient as knowledge_inequality,
                    CASE 
                        WHEN gini_coefficient > 0.5 OR 1.0 * top_devs[0].file_count / total_files > 0.3
                        THEN 'hero-based'
                        ELSE 'balanced'
                    END as distribution_type
            """, repo_name=repo_name)
            
            return result.single().data()
    
    # 5. Developer Interactions
    
    def get_developer_collaborations(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get collaboration metrics between developers based on shared files"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (d1:Developer)-[:BELONGS_TO]->(r)
                MATCH (d2:Developer)-[:BELONGS_TO]->(r)
                WHERE id(d1) < id(d2)
                
                // Find commits from both developers
                MATCH (c1:Commit)-[:COMMITTED_BY]->(d1)
                MATCH (c2:Commit)-[:COMMITTED_BY]->(d2)
                
                // Find files they both worked on
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
            """, repo_name=repo_name)
            
            return [record.data() for record in result]
            
    def get_file_contributor_count(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get the number of contributors per file to identify critical files"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Repository {name: $repo_name})
                MATCH (f:File)-[:BELONGS_TO]->(r)
                
                // Find all developers who committed to this file
                OPTIONAL MATCH (c:Commit)-[:ADDED|MODIFIED|DELETED]->(f)
                OPTIONAL MATCH (c)-[:COMMITTED_BY]->(d:Developer)
                
                WITH f, count(DISTINCT d) as contributor_count
                
                RETURN 
                    f.path as file_path,
                    f.filename as filename,
                    contributor_count as contributors
                ORDER BY contributor_count
            """, repo_name=repo_name)
            
            return [record.data() for record in result]