#!/bin/bash

# Variable Declaration
DB_NAME="testDb"
DB_USER="sampleUser"
DB_PASSWORD="samplePassword"
APP_DIR="/opt/csye6225"
ZIP_FILE="nameOfYourZip.zip"

# Update package lists and upgrade system packages
sudo apt update && sudo apt upgrade -y

# Install MySQL Server (Modify for PostgreSQL/MariaDB if needed)
sudo apt install -y mysql-server

# Start MySQL and enable it to start on boot
sudo systemctl start mysql
sudo systemctl enable mysql

# Create database and user
sudo mysql -e "CREATE DATABASE ${DB_NAME};"
sudo mysql -e "CREATE USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
sudo mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"

# Create a new Linux group and user for the application
sudo groupadd appgroup
sudo useradd -m -g appgroup -s /bin/bash appuser

# Ensure the /opt/csye6225 directory exists
sudo mkdir -p ${APP_DIR}

# Unzip the application inside /opt/csye6225 (no need to move it)
sudo unzip ${APP_DIR}/${ZIP_FILE} -d ${APP_DIR}

# Remove the zip file after extraction
sudo rm ${APP_DIR}/${ZIP_FILE}

# Change ownership and set permissions
sudo chown -R appuser:appgroup ${APP_DIR}
sudo chmod -R 750 ${APP_DIR}

echo "Setup completed successfully."