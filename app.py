from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
if os.getenv('TESTING')=='True':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://<username>:<password>@<host>/<database-name>'
db = SQLAlchemy(app)


class HealthCheck(db.Model):
    __tablename__ = 'healthCheck'
    check_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

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
        app.run(debug=False)
    except Exception as e:
        print("Exception occurred while starting application: ", e)