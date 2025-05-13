CREATE TABLE repositories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_name VARCHAR(255) NOT NULL,
    owner VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE commits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sha VARCHAR(255) NOT NULL,
    repo_id INT,
    author_name VARCHAR(255),
    author_email VARCHAR(255),
    date TIMESTAMP,
    message TEXT,
    url VARCHAR(255),
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE commit_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    commit_id INT,
    filename VARCHAR(255),
    status VARCHAR(50),
    additions INT,
    deletions INT,
    changes INT,
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

CREATE TABLE pull_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_id INT,
    pr_number INT,
    state VARCHAR(50),
    title VARCHAR(255),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    url VARCHAR(255),
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE issues (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_id INT,
    issue_number INT,
    state VARCHAR(50),
    title VARCHAR(255),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    url VARCHAR(255),
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_id INT,
    pr_number INT,
    review_id INT,
    user_id VARCHAR(255),
    state VARCHAR(50),
    submitted_at TIMESTAMP,
    body TEXT,
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE contributors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_id INT,
    username VARCHAR(255),
    contributions INT,
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE contribution_periods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    repo_id INT,
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);

CREATE TABLE developer_contributions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contribution_period_id INT,
    contributor_username VARCHAR(255),
    commits_count INT DEFAULT 0,
    pull_requests_count INT DEFAULT 0,
    issues_count INT DEFAULT 0,
    reviews_count INT DEFAULT 0,
    contributions_total INT DEFAULT 0,
    FOREIGN KEY (contribution_period_id) REFERENCES contribution_periods(id)
);

CREATE TABLE repo_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_id INT,
    snapshot_date DATE NOT NULL,
    commits INT,
    issues INT,
    pull_requests INT,
    open_issues INT,
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);
