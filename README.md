# webapp
Submission for Assignment-01 for the course CSYE-6225\
Following are the set-up requirements and instructions to run the app locally -
## Requirements

- Python 3.x
- Flask
- Flask-SQLAlchemy
- MySQL

## Setup

1. Clone the repository:
    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. Create a virtual environment and activate it:
    ```sh
    python -m venv venv
    source <directory-to-venv>/venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

4. Update the database URI in :
    ```python
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://<username>:<password>@<host>/<database>'
    ```
    > **Make sure to create the database manually on MySQLWorkbench or any MySQL Client you're working on before running the project.**

5. Initialize the database:
    ```sh
    python app.py
    ```

## Running the Application

1. Start the Flask application:
    ```sh
    python app.py
    ```

2. The application will be available at `http://127.0.0.1:5000`.

## Endpoints

- `GET /healthz`: Health check endpoint. Logs the health check request to the database and returns a `200 OK` status if successful.

### Error Handling

- `405 Method Not Allowed`: Returned if the request method is not `GET`.
- `400 Bad Request`: Returned if the request contains data or form parameters.
- `503 Service Unavailable`: Returned if there is an error while inserting data into the database.