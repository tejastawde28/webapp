# WebApp for the course CSYE-6225

Following are the set-up requirements and instructions to run the app locally:

## Requirements

- Python 3.x
- Flask
- Flask-SQLAlchemy
- mysqlclient
- MySQL Server (or MariaDB/PostgreSQL if preferred)
- Werkzeug
- pytest (to run tests)

## Setup

1. **Clone the repository**:
    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. **Create a virtual environment and activate it**:
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

3. **Install the required packages**:
    ```sh
    pip install -r requirements.txt
    ```

4. **Set up MySQL Database**:
    - Install MySQL Server if it's not already installed (can be modified for PostgreSQL or MariaDB).
    - Create a new database and user:
        ```sh
        mysql -u root -p
        CREATE DATABASE <database-name>;
        CREATE USER '<username>'@'localhost' IDENTIFIED BY '<password>';
        GRANT ALL PRIVILEGES ON <database-name>.* TO '<username>'@'localhost';
        FLUSH PRIVILEGES;
        EXIT;
        ```
> Enter your username and password in place of `<username>` and `<password>`.

5. **Update the database URI**:
    - Modify the following line in your `app.py` file:
    ```python
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://<username>:<password>@<localhost>/<database-name>'
    ```
> Make sure to configure the Database URL as per your database before running the project. Also substitute your credentials/port value in place of `<username>`, `<password>`, `<localhost>` and `<database-name>`

6. **Initialize the database**:
    - Run the following command to create tables in the MySQL database:
    ```sh
    python app.py
    ```

## Running the Application

1. **Start the Flask application**:
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

## Running Tests
1. Install `pytest` in your `venv`
```sh
pip install pytest
```
2. Set the environment variable `TESTING` as `True` as follows for mac/Linux
```sh
export TESTING="True"
```
or as follows for Windows 
```sh
set TESTING=True
```
3. Run the test
```sh
pytest --verbose
```

Changes here
