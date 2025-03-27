from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import os
import uuid
import boto3
import time
import logging
import json
import watchtower
from werkzeug.utils import secure_filename
from datetime import date
from statsd import StatsClient

# Custom JSON formatter for logs
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "path": getattr(record, 'path', ''),
            "method": getattr(record, 'method', ''),
            "status_code": getattr(record, 'status_code', ''),
            "remote_addr": getattr(record, 'remote_addr', ''),
            "duration_ms": getattr(record, 'duration_ms', ''),
            "operation": getattr(record, 'operation', '')
        }
        
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

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
json_formatter = JsonFormatter()

# Add CloudWatch handler
if not os.getenv('TESTING') == 'True':
    try:
        # Create CloudWatch handler with JSON formatter
        cloudwatch_handler = watchtower.CloudWatchLogHandler(
            log_group=log_group,
            stream_name=log_stream,
            create_log_group=True
        )
        cloudwatch_handler.setFormatter(json_formatter)
        logger.addHandler(cloudwatch_handler)
        
        # Also add file handler for application logs
        app_file_handler = logging.FileHandler('/var/log/csye6225.log')
        app_file_handler.setFormatter(json_formatter)
        logger.addHandler(app_file_handler)
        
        # Also add console handler for local debugging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(json_formatter)
        logger.addHandler(console_handler)
        
        extra = {'path': '', 'method': '', 'remote_addr': ''}
        logger.info("CloudWatch logging initialized successfully", extra=extra)
    except Exception as e:
        print(f"Failed to initialize CloudWatch logging: {e}")
        # Fallback to console logging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(json_formatter)
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
        
        extra = {
            'operation': f's3.{operation_name}',
            'duration_ms': f"{duration:.2f}",
            'path': request.path if request else '',
            'method': request.method if request else ''
        }
        logger.info(f"S3 operation {operation_name} completed", extra=extra)
        return result
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        statsd_client.timing(f's3.{operation_name}.error', duration)
        
        extra = {
            'operation': f's3.{operation_name}',
            'duration_ms': f"{duration:.2f}",
            'path': request.path if request else '',
            'method': request.method if request else ''
        }
        logger.error(f"S3 operation {operation_name} failed: {str(e)}", exc_info=True, extra=extra)
        raise

def time_db_operation(operation_name, func, *args, **kwargs):
    # Time a database operation and record metrics
    start_time = time.time()
    try:
        result = func(*args, **kwargs)
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        statsd_client.timing(f'db.{operation_name}', duration)
        
        extra = {
            'operation': f'db.{operation_name}',
            'duration_ms': f"{duration:.2f}",
            'path': request.path if request else '',
            'method': request.method if request else ''
        }
        logger.info(f"Database operation {operation_name} completed", extra=extra)
        return result
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        statsd_client.timing(f'db.{operation_name}.error', duration)
        
        extra = {
            'operation': f'db.{operation_name}',
            'duration_ms': f"{duration:.2f}",
            'path': request.path if request else '',
            'method': request.method if request else ''
        }
        logger.error(f"Database operation {operation_name} failed: {str(e)}", exc_info=True, extra=extra)
        raise

def bootstrap_db():
    try:
        with app.app_context():
            db.create_all()
            extra = {'path': '', 'method': '', 'remote_addr': ''}
            logger.info("Database initialized successfully", extra=extra)
    except Exception as e:
        error_msg = f"Exception occurred while creating database: {e}"
        extra = {'path': '', 'method': '', 'remote_addr': ''}
        logger.error(error_msg, exc_info=True, extra=extra)
        print(error_msg)

@app.before_request
def log_request_info():
    extra = {
        'path': request.path,
        'method': request.method,
        'remote_addr': request.remote_addr
    }
    logger.info(f"Request received", extra=extra)

@app.after_request
def log_response_info(response):
    extra = {
        'path': request.path,
        'method': request.method,
        'remote_addr': request.remote_addr,
        'status_code': response.status_code
    }
    logger.info(f"Response sent", extra=extra)
    return response

@app.route('/healthz', methods=['GET'])
def health_check():
    start_time = time.time()
    statsd_client.incr('api.health_check')
    
    if request.method not in ['GET']:
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr
        }
        logger.warning(f"Method not allowed for health check endpoint", extra=extra)
        return method_not_allowed(None)

    if request.data or request.form or request.args:
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr
        }
        logger.warning("Bad request: health check with parameters", extra=extra)
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
        
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'duration_ms': f"{(time.time() - start_time) * 1000:.2f}"
        }
        logger.info("Health check successful", extra=extra)

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
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'duration_ms': f"{duration:.2f}"
        }
        logger.error(f"Health check failed: {str(e)}", exc_info=True, extra=extra)
        
        response = app.response_class(
            response='',
            status=503,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        statsd_client.timing('api.health_check.time', duration)
        return response

@app.route('/v1/file', methods=['POST'])
def upload_file():
    start_time = time.time()
    statsd_client.incr('api.upload_file')
    
    if request.method != 'POST':
        if request.method in ['GET', 'DELETE']:
            extra = {
                'path': request.path,
                'method': request.method,
                'remote_addr': request.remote_addr
            }
            logger.warning(f"Invalid method for upload endpoint", extra=extra)
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
            extra = {
                'path': request.path,
                'method': request.method,
                'remote_addr': request.remote_addr
            }
            logger.warning(f"Method not allowed for upload endpoint", extra=extra)
            return method_not_allowed(None)
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.upload_file.time', duration)
        return response
    
    # Check if the request has a file
    if 'file' not in request.files:
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr
        }
        logger.warning("Upload attempt with no file provided", extra=extra)
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
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr
        }
        logger.warning("Upload attempt with empty filename", extra=extra)
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
        
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': file_id,
            'file_name': filename
        }
        logger.info(f"Processing file upload", extra=extra)
        
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
        
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': file_id,
            'duration_ms': f"{duration:.2f}"
        }
        logger.info(f"File uploaded successfully", extra=extra)
        
        statsd_client.timing('api.upload_file.time', duration)
        return jsonify(response), 201
        
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'duration_ms': f"{duration:.2f}"
        }
        logger.error(f"Error uploading file: {str(e)}", exc_info=True, extra=extra)
        
        try:
            time_db_operation('file_rollback', db.session.rollback)
        except:
            pass
            
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        statsd_client.timing('api.upload_file.time', duration)
        return response

@app.route('/v1/file/<string:id>', methods=['GET'])
def get_file(id):
    start_time = time.time()
    statsd_client.incr('api.get_file')
    
    if request.method != 'GET':
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id
        }
        logger.warning(f"Method not allowed for get file endpoint", extra=extra)
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.get_file.time', duration)
        return method_not_allowed(None)
    
    try:
        # Find file in database with timing
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id
        }
        logger.info(f"Retrieving file", extra=extra)
        
        file = time_db_operation('get_file', File.query.get, id)
        
        if not file:
            extra = {
                'path': request.path,
                'method': request.method,
                'remote_addr': request.remote_addr,
                'file_id': id
            }
            logger.warning(f"File not found", extra=extra)
            
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
        
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id,
            'duration_ms': f"{duration:.2f}"
        }
        logger.info(f"File retrieved successfully", extra=extra)
        
        statsd_client.timing('api.get_file.time', duration)
        return jsonify(response), 200
        
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id,
            'duration_ms': f"{duration:.2f}"
        }
        logger.error(f"Error retrieving file: {str(e)}", exc_info=True, extra=extra)
        
        response = app.response_class(
            response='',
            status=500,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        statsd_client.timing('api.get_file.time', duration)
        return response

@app.route('/v1/file/<string:id>', methods=['DELETE'])
def delete_file(id):
    start_time = time.time()
    statsd_client.incr('api.delete_file')
    
    if request.method != 'DELETE':
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id
        }
        logger.warning(f"Method not allowed for delete file endpoint", extra=extra)
        
        duration = (time.time() - start_time) * 1000
        statsd_client.timing('api.delete_file.time', duration)
        return method_not_allowed(None)
    
    try:
        # Find file in database with timing
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id
        }
        logger.info(f"Deleting file", extra=extra)
        
        file = time_db_operation('get_file_for_delete', File.query.get, id)
        
        if not file:
            extra = {
                'path': request.path,
                'method': request.method,
                'remote_addr': request.remote_addr,
                'file_id': id
            }
            logger.warning(f"File not found for deletion", extra=extra)
            
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
        
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id,
            'duration_ms': f"{duration:.2f}"
        }
        logger.info(f"File deleted successfully", extra=extra)
        
        # Return success with no content
        statsd_client.timing('api.delete_file.time', duration)
        return '', 204
        
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr,
            'file_id': id,
            'duration_ms': f"{duration:.2f}"
        }
        logger.error(f"Error deleting file: {str(e)}", exc_info=True, extra=extra)
        
        try:
            time_db_operation('file_delete_rollback', db.session.rollback)
        except:
            pass
            
        response = app.response_class(
            response='',
            status=500,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        statsd_client.timing('api.delete_file.time', duration)
        return response

@app.errorhandler(405)
def method_not_allowed(e):
    extra = {
        'path': request.path,
        'method': request.method,
        'remote_addr': request.remote_addr
    }
    logger.warning(f"Method not allowed", extra=extra)
    
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
        extra = {
            'path': request.path,
            'method': request.method,
            'remote_addr': request.remote_addr
        }
        logger.warning(f"OPTIONS request blocked", extra=extra)
        
        return method_not_allowed(None)

if __name__ == '__main__':
    try:
        bootstrap_db()
        extra = {'path': '', 'method': '', 'remote_addr': ''}
        logger.info("Application starting up", extra=extra)
        
        app.run(debug=False, host='0.0.0.0')
    except Exception as e:
        error_msg = f"Exception occurred while starting application: {e}"
        extra = {'path': '', 'method': '', 'remote_addr': ''}
        logger.error(error_msg, exc_info=True, extra=extra)
        print(error_msg)