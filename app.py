from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import uuid
import boto3
import time
import logging
import watchtower
from werkzeug.utils import secure_filename
from datetime import date
from statsd import StatsClient

# Initialize StatsClient for metrics
statsd_client = StatsClient(host='localhost', port=8125, prefix='webapp')

app = Flask(__name__)
if os.getenv('TESTING')=='True':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
else:
    db_username = os.getenv('DB_USERNAME')
    db_password = os.getenv('DB_PASSWORD')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_name = os.getenv('DB_NAME', 'webapp')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql://{db_username}:{db_password}@{db_host}/{db_name}'

db = SQLAlchemy(app)

# Configure CloudWatch logging
log_group = os.getenv('CLOUDWATCH_LOG_GROUP', 'webapp-logs')
log_stream = os.getenv('CLOUDWATCH_LOG_STREAM', 'app-logs')

# Set up logging
logger = logging.getLogger('webapp')
logger.setLevel(logging.INFO)

# Add CloudWatch handler
if not os.getenv('TESTING') == 'True':
    try:
        cloudwatch_handler = watchtower.CloudWatchLogHandler(
            log_group=log_group,
            stream_name=log_stream,
            create_log_group=True
        )
        logger.addHandler(cloudwatch_handler)
        
        # Also add console handler for local debugging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
        
        logger.info("CloudWatch logging initialized successfully")
    except Exception as e:
        print(f"Failed to initialize CloudWatch logging: {e}")
        # Fallback to console logging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)


class HealthCheck(db.Model):
    __tablename__ = 'healthCheck'
    check_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.String(36), primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    upload_date = db.Column(db.Date, default=date.today)

def get_s3_client():
    return boto3.client('s3')

def get_bucket_name():
    return os.getenv('S3_BUCKET_NAME')

def time_s3_operation(operation_name, func, *args, **kwargs):
    # Time an S3 operation and record metrics
    start_time = time.time()
    try:
        result = func(*args, **kwargs)
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        statsd_client.timing(f's3.{operation_name}', duration)
        logger.info(f"S3 operation {operation_name} completed in {duration:.2f}ms")
        return result
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        statsd_client.timing(f's3.{operation_name}.error', duration)
        logger.error(f"S3 operation {operation_name} failed after {duration:.2f}ms: {e}", exc_info=True)
        raise

def time_db_operation(operation_name, func, *args, **kwargs):
    # Time a database operation and record metrics
    start_time = time.time()
    try:
        result = func(*args, **kwargs)
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        statsd_client.timing(f'db.{operation_name}', duration)
        logger.info(f"Database operation {operation_name} completed in {duration:.2f}ms")
        return result
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        statsd_client.timing(f'db.{operation_name}.error', duration)
        logger.error(f"Database operation {operation_name} failed after {duration:.2f}ms: {e}", exc_info=True)
        raise

def bootstrap_db():
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database initialized successfully")
    except Exception as e:
        error_msg = f"Exception occurred while creating database: {e}"
        logger.error(error_msg, exc_info=True)
        print(error_msg)

@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response_info(response):
    logger.info(f"Response: {response.status_code}")
    return response

@app.route('/healthz', methods=['GET'])
def health_check():
    start_time = time.time()
    statsd_client.incr('api.health_check')
    
    if request.method not in ['GET']:
        logger.warning(f"Method not allowed: {request.method} for /healthz")
        return method_not_allowed(None)

    if request.data or request.form or request.args:
        logger.warning("Bad request: health check with parameters")
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.health_check.time', duration)
        return response
    
    try:
        new_check = HealthCheck()
        time_db_operation('health_check_insert', db.session.add, new_check)
        time_db_operation('health_check_commit', db.session.commit)
        logger.info("Health check successful")

        response = app.response_class(
            response='',
            status=200,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.health_check.time', duration)
        return response
    
    except Exception as e:
        error_msg = f"Health check failed: {e}"
        logger.error(error_msg, exc_info=True)
        response = app.response_class(
            response='',
            status=503,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.health_check.time', duration)
        return response

@app.route('/v1/file', methods=['POST'])
def upload_file():
    start_time = time.time()
    statsd_client.incr('api.upload_file')
    
    if request.method != 'POST':
        if request.method in ['GET', 'DELETE']:
            logger.warning(f"Invalid method {request.method} for upload endpoint")
            response = app.response_class(
                response='',
                status=400,
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
        else:
            logger.warning(f"Method not allowed: {request.method} for upload endpoint")
            return method_not_allowed(None)
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return response
    
    # Check if the request has a file
    if 'file' not in request.files:
        logger.warning("Upload attempt with no file provided")
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return response
    
    file = request.files['file']
    
    # Check if file is empty
    if file.filename == '':
        logger.warning("Upload attempt with empty filename")
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return response
    
    try:
        # Generate secure filename and unique ID
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        logger.info(f"Processing upload for file: {filename}, ID: {file_id}")
        
        # Get S3 client and bucket name
        s3_client = get_s3_client()
        bucket_name = get_bucket_name()
        
        # Define S3 path/key
        s3_key = f"{file_id}/{filename}"
        
        # Upload to S3 with timing
        time_s3_operation('upload_file', s3_client.upload_fileobj, file, bucket_name, s3_key)
        
        # Create URL
        url = f"{bucket_name}/{s3_key}"
        
        # Store metadata in database
        new_file = File(
            id=file_id,
            file_name=filename,
            url=url,
            upload_date=date.today()
        )
        
        time_db_operation('file_insert', db.session.add, new_file)
        time_db_operation('file_commit', db.session.commit)
        
        # Return success response
        response = {
            "file_name": filename,
            "id": file_id,
            "url": url,
            "upload_date": new_file.upload_date.strftime("%Y-%m-%d")
        }
        
        logger.info(f"File uploaded successfully: {file_id}")
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return jsonify(response), 201
        
    except Exception as e:
        error_msg = f"Error uploading file: {e}"
        logger.error(error_msg, exc_info=True)
        time_db_operation('file_rollback', db.session.rollback)
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return response

@app.route('/v1/file/<string:id>', methods=['GET'])
def get_file(id):
    start_time = time.time()
    statsd_client.incr('api.get_file')
    
    if request.method != 'GET':
        logger.warning(f"Method not allowed: {request.method} for get file endpoint")
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.get_file.time', duration)
        return method_not_allowed(None)
    
    try:
        # Find file in database with timing
        logger.info(f"Retrieving file with ID: {id}")
        file = time_db_operation('get_file', File.query.get, id)
        
        if not file:
            logger.warning(f"File not found: {id}")
            response = app.response_class(
                response='',
                status=400,
                headers = {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
            duration = (time.time() - start_time) * 1000
            statsd_client.timing('api.get_file.time', duration)
            return response
        
        # Return file metadata
        response = {
            "file_name": file.file_name,
            "id": file.id,
            "url": file.url,
            "upload_date": file.upload_date.strftime("%Y-%m-%d")
        }
        
        logger.info(f"File retrieved successfully: {id}")
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.get_file.time', duration)
        return jsonify(response), 200
        
    except Exception as e:
        error_msg = f"Error retrieving file: {e}"
        logger.error(error_msg, exc_info=True)
        response = app.response_class(
            response='',
            status=500,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.get_file.time', duration)
        return response

@app.route('/v1/file/<string:id>', methods=['DELETE'])
def delete_file(id):
    start_time = time.time()
    statsd_client.incr('api.delete_file')
    
    if request.method != 'DELETE':
        logger.warning(f"Method not allowed: {request.method} for delete file endpoint")
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.delete_file.time', duration)
        return method_not_allowed(None)
    
    try:
        # Find file in database with timing
        logger.info(f"Deleting file with ID: {id}")
        file = time_db_operation('get_file_for_delete', File.query.get, id)
        
        if not file:
            logger.warning(f"File not found for deletion: {id}")
            response = app.response_class(
                response='',
                status=404,
                headers = {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
            duration = (time.time() - start_time) * 1000
            statsd_client.timing('api.delete_file.time', duration)
            return response
        
        # Delete from S3 with timing
        s3_client = get_s3_client()
        bucket_name = get_bucket_name()
        
        # Extract the key from the URL
        s3_key = file.url.replace(f"{bucket_name}/", "", 1)
        
        # Delete the object from S3
        time_s3_operation('delete_file', s3_client.delete_object, Bucket=bucket_name, Key=s3_key)
        
        # Delete from database with timing
        time_db_operation('file_delete', db.session.delete, file)
        time_db_operation('file_delete_commit', db.session.commit)
        
        logger.info(f"File deleted successfully: {id}")
        # Return success with no content
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.delete_file.time', duration)
        return '', 204
        
    except Exception as e:
        error_msg = f"Error deleting file: {e}"
        logger.error(error_msg, exc_info=True)
        time_db_operation('file_delete_rollback', db.session.rollback)
        response = app.response_class(
            response='',
            status=500,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.delete_file.time', duration)
        return response

@app.errorhandler(405)
def method_not_allowed(e):
    logger.warning(f"Method not allowed: {request.method} {request.path}")
    response = app.response_class(
        response='',
        status=405,
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'X-Content-Type-Options': 'nosniff'
        }
    )
    return response

@app.before_request
def block_options_request():
    if request.method == 'OPTIONS':
        logger.warning(f"OPTIONS request blocked: {request.path}")
        return method_not_allowed(None)

if __name__ == '__main__':
    try:
        bootstrap_db()
        logger.info("Application starting up")
        app.run(debug=False, host='0.0.0.0')
    except Exception as e:
        error_msg = f"Exception occurred while starting application: {e}"
        logger.error(error_msg, exc_info=True)
        print(error_msg)