# BackendService

FastAPI monolithic backend project

Group-5 / Cs453 / Spring 2025  
**!!! Make sure you use the "yaşar" branch**

---

## ⚙️ How to Run the Project

Follow these steps to get the backend service up and running:

1. **Make sure Python 3.9 or newer is installed** on your system.

2. **(Optional)** Create and activate a virtual environment:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. **Install required dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4. **Run the application:**

    ```bash
    python main.py
    ```

The app will start and typically be available at `http://localhost:8000`.

---

## 🔐 Environment Configuration

Create a `.env` file in the root directory with the following content (make sure to fill in your GitHub token and OpenAI API key):

```env
NEO4J_URI="neo4j+s://a453bd55.databases.neo4j.io"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="9BSPQwMEm4TWSp_TiN1gkEYfr1OGmv0xdpxZtsruQik"
GITHUB_TOKEN=""
DB_HOST="insightsdb.czy2mo0kejlp.eu-north-1.rds.amazonaws.com"
DB_USER="admin"
DB_PASSWORD="DevInsights453"
DB_NAME="devinsights"

GITHUB_CLIENT_ID=Ov23libNDZVqB6GpNjNX
GITHUB_CLIENT_SECRET=636584ba17e3be0de62ed295a4ea270a97430379
OPENAI_API_KEY=
