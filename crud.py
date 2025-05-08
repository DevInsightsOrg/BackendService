# app/crud.py
from database import get_db_connection
from fastapi import HTTPException
import mysql.connector

def insert_commit(repo_id: int, sha: str, author_name: str, date: str, message: str, url: str):
    """
    Insert a new commit or update if it already exists.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the commit already exists
        query = "SELECT id FROM commits WHERE sha = %s AND repo_id = %s"
        cursor.execute(query, (sha, repo_id))
        existing_commit = cursor.fetchone()

        if existing_commit:
            # Commit already exists, update if needed
            query = """
            UPDATE commits
            SET author_name = %s, date = %s, message = %s, url = %s
            WHERE sha = %s AND repo_id = %s
            """
            values = (author_name, date, message, url, sha, repo_id)
            cursor.execute(query, values)
        else:
            # Insert a new commit
            query = """
            INSERT INTO commits (sha, repo_id, author_name, date, message, url)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            values = (sha, repo_id, author_name, date, message, url)
            cursor.execute(query, values)

        connection.commit()
        cursor.close()
        connection.close()

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")
    

def insert_issue(repo_id: int, issue_number: int, state: str, title: str, created_at: str, updated_at: str, url: str):
    """
    Insert a new issue or update if it already exists.
    """
    print(f"Inserting issue: {repo_id}, {issue_number}, {state}, {title}, {created_at}, {updated_at}, {url}")

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the issue already exists
        query = "SELECT id FROM issues WHERE issue_number = %s AND repo_id = %s"
        cursor.execute(query, (issue_number, repo_id))
        existing_issue = cursor.fetchone()

        if existing_issue:
            # Issue already exists, update if needed
            query = """
            UPDATE issues
            SET state = %s, title = %s, created_at = %s, updated_at = %s, url = %s
            WHERE issue_number = %s AND repo_id = %s
            """
            values = (state, title, created_at, updated_at, url, issue_number, repo_id)
            cursor.execute(query, values)
        else:
            # Insert a new issue
            query = """
            INSERT INTO issues (repo_id, issue_number, state, title, created_at, updated_at, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            values = (repo_id, issue_number, state, title, created_at, updated_at, url)
            cursor.execute(query, values)

        connection.commit()
        cursor.close()
        connection.close()

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")
    

def insert_review(repo_id: int, pr_number: int, review_id: int, user_id: str, state: str, submitted_at: str, body: str):
    """
    Insert a new review or update if it already exists.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the review already exists
        query = "SELECT id FROM reviews WHERE review_id = %s AND pr_number = %s AND repo_id = %s"
        cursor.execute(query, (review_id, pr_number, repo_id))
        existing_review = cursor.fetchone()

        if existing_review:
            # Review already exists, update if needed
            query = """
            UPDATE reviews
            SET state = %s, user_id = %s, submitted_at = %s, body = %s
            WHERE review_id = %s AND pr_number = %s AND repo_id = %s
            """
            values = (state, user_id, submitted_at, body, review_id, pr_number, repo_id)
            cursor.execute(query, values)
        else:
            # Insert a new review
            query = """
            INSERT INTO reviews (repo_id, pr_number, review_id, user_id, state, submitted_at, body)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            values = (repo_id, pr_number, review_id, user_id, state, submitted_at, body)
            cursor.execute(query, values)

        connection.commit()
        cursor.close()
        connection.close()

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")
    

def insert_contributor(repo_id: int, username: str, contributions: int):
    """
    Insert a new contributor or update if they already exist.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the contributor already exists
        query = "SELECT id FROM contributors WHERE username = %s AND repo_id = %s"
        cursor.execute(query, (username, repo_id))
        existing_contributor = cursor.fetchone()

        if existing_contributor:
            # Contributor already exists, update if needed
            query = """
            UPDATE contributors
            SET contributions = %s
            WHERE username = %s AND repo_id = %s
            """
            values = (contributions, username, repo_id)
            cursor.execute(query, values)
        else:
            # Insert a new contributor
            query = """
            INSERT INTO contributors (repo_id, username, contributions)
            VALUES (%s, %s, %s)
            """
            values = (repo_id, username, contributions)
            cursor.execute(query, values)

        connection.commit()
        cursor.close()
        connection.close()

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")


def insert_contribution_period(repo_id: int, start_date: str, end_date: str):
    """
    Insert a new contribution period into the database.
    """
    try:
        connection = get_db_connection()  # Get DB connection from database.py
        cursor = connection.cursor()  # Create a cursor to execute queries

        query = """
        INSERT INTO contribution_periods (repo_id, start_date, end_date)
        VALUES (%s, %s, %s)
        """
        values = (repo_id, start_date, end_date)

        cursor.execute(query, values)  # Execute the query with the provided values
        connection.commit()  # Commit the transaction to the database
        cursor.close()  # Close the cursor
        connection.close()  # Close the database connection

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")
    

def insert_developer_contribution(contribution_period_id: int, contributor_username: str, commits: int, prs: int, issues: int, reviews: int):
    """
    Insert developer contributions for a two-week period into the database.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        contributions_total = commits + prs + issues + reviews  # Total contributions

        query = """
        INSERT INTO developer_contributions (contribution_period_id, contributor_username, commits_count, pull_requests_count, issues_count, reviews_count, contributions_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            commits_count = commits_count + VALUES(commits_count),
            pull_requests_count = pull_requests_count + VALUES(pull_requests_count),
            issues_count = issues_count + VALUES(issues_count),
            reviews_count = reviews_count + VALUES(reviews_count),
            contributions_total = contributions_total + VALUES(contributions_total)
        """
        values = (contribution_period_id, contributor_username, commits, prs, issues, reviews, contributions_total)

        cursor.execute(query, values)
        connection.commit()
        cursor.close()
        connection.close()

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"MySQL error: {str(err)}")

# crud.py

import mysql.connector


