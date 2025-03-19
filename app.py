from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import uuid
import boto3
from werkzeug.utils import secure_filename
from datetime import date

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



def bootstrap_db():
    try:
        with app.app_context():
            db.create_all()
    except Exception as e:
        print("Exception occurred while creating database: ", e)

@app.route('/healthz', methods=['GET'])
def health_check():
    if request.method not in ['GET']:
        return method_not_allowed(None)

    if request.data or request.form or request.args:
        response = app.response_class(
            response='',
            status=400,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        return response
    
    try:
        new_check = HealthCheck()
        db.session.add(new_check)
        db.session.commit()
        response = app.response_class(
            response='',
            status=200,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        return response
    
    except Exception as e:
        print("Exception occurred while inserting data: ", e)
        response = app.response_class(
            response='',
            status=503,
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        return response

@app.route('/v1/file', methods=['POST'])
def upload_file():
    # Check if the request has a file
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    
    # Check if file is empty
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    try:
        # Generate secure filename and unique ID
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        
        # Get S3 client and bucket name
        s3_client = get_s3_client()
        bucket_name = get_bucket_name()
        
        # Define S3 path/key
        s3_key = f"{file_id}/{filename}"
        
        # Upload to S3
        s3_client.upload_fileobj(
            file,
            bucket_name,
            s3_key
        )
        
        # Create URL
        url = f"{bucket_name}/{s3_key}"
        
        # Store metadata in database
        new_file = File(
            id=file_id,
            file_name=filename,
            url=url,
            upload_date=date.today()
        )
        
        db.session.add(new_file)
        db.session.commit()
        
        # Return success response
        response = {
            "file_name": filename,
            "id": file_id,
            "url": url,
            "upload_date": new_file.upload_date.strftime("%Y-%m-%d")
        }
        
        return jsonify(response), 201
        
    except Exception as e:
        print(f"Error uploading file: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to upload file"}), 400

@app.route('/v1/file/<string:id>', methods=['GET'])
def get_file(id):
    try:
        # Find file in database
        file = File.query.get(id)
        
        if not file:
            return jsonify({"error": "File not found"}), 404
        
        # Return file metadata
        response = {
            "file_name": file.file_name,
            "id": file.id,
            "url": file.url,
            "upload_date": file.upload_date.strftime("%Y-%m-%d")
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Error retrieving file: {e}")
        return jsonify({"error": "Failed to retrieve file"}), 500

@app.route('/v1/file/<string:id>', methods=['DELETE'])
def delete_file(id):
    try:
        # Find file in database
        file = File.query.get(id)
        
        if not file:
            return jsonify({"error": "File not found"}), 404
        
        # Delete from S3
        s3_client = get_s3_client()
        bucket_name = get_bucket_name()
        
        # Extract the key from the URL
        s3_key = file.url.replace(f"{bucket_name}/", "", 1)
        
        # Delete the object from S3
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=s3_key
        )
        
        # Delete from database
        db.session.delete(file)
        db.session.commit()
        
        # Return success with no content
        return '', 204
        
    except Exception as e:
        print(f"Error deleting file: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to delete file"}), 500

@app.errorhandler(405)
def method_not_allowed(e):
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
        return method_not_allowed(None)

if __name__ == '__main__':
    try:
        bootstrap_db()
        app.run(debug=False, host='0.0.0.0')
    except Exception as e:
        print("Exception occurred while starting application: ", e)