packer {
  required_plugins {
    amazon = {
      version = ">= 1.0.0, < 2.0.0"
      source  = "github.com/hashicorp/amazon"
    }
    # googlecompute = {
    #   source  = "github.com/hashicorp/googlecompute"
    #   version = "~> 1"
    # }
  }
}

variable "aws_profile" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "source_ami" {
  type    = string
  default = "ami-04b4f1a9cf54c11d0"
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "subnet_id" {
  type    = string
  default = "subnet-07ac8cfb0d5c02f4b"
}

variable "ssh_username" {
  type    = string
  default = "ubuntu"
}

# variable "db_name" {
#   type    = string
#   default = "webapp"
# }

# variable "db_user" {
#   type    = string
#   default = "tejas"
# }

# variable "db_password" {
#   type = string
# }

variable "dev_account_id" {
  type    = string
  default = "442426868126"
}

variable "demo_account_id" {
  type    = string
  default = "980921734991"
}

# variable "gcp_project_id" {
#   type    = string
#   default = "devproject-452020"
# }

# variable "demo_gcp_project_id" {
#   type    = string
#   default = "demoproject-452122"
# }

# variable "gcp_region" {
#   type    = string
#   default = "us-central1"
# }

# variable "gcp_zone" {
#   type    = string
#   default = "us-central1-a"
# }

# variable "gcp_machine_type" {
#   type    = string
#   default = "e2-medium"
# }

# variable "gcp_source_image" {
#   type    = string
#   default = "ubuntu-2404-noble-amd64-v20250214"
# }

# variable "gcp_source_image_family" {
#   type    = string
#   default = "ubuntu-2404-noble-amd64"
# }


# variable "gcp_image_name" {
#   type    = string
#   default = "csye6225-webapp-gcp"
# }

# variable "gcp_image_family" {
#   type    = string
#   default = "gcp-webapp-image"
# }

# variable "gcp_disk_type" {
#   type    = string
#   default = "pd-standard"
# }

# variable "gcp_network" {
#   type    = string
#   default = "default"
# }

# variable "gcp_credentials_file" {
#   type = string
# }

source "amazon-ebs" "webapp-ami" {
  profile         = "${var.aws_profile}"
  region          = "${var.region}"
  ami_name        = "csye6225-webapp-spring25-${formatdate("YYYY-MM-DD", timestamp())}"
  ami_description = "CSYE6225 Webapp Spring 2025 AMI"

  ami_regions = [
    "us-east-1",
  ]

  ami_users = [
    var.dev_account_id,
    var.demo_account_id,
  ]

  instance_type = "${var.instance_type}"
  source_ami    = "${var.source_ami}"
  ssh_username  = "${var.ssh_username}"
  subnet_id     = "${var.subnet_id}"

  launch_block_device_mappings {
    delete_on_termination = true
    device_name           = "/dev/sda1"
    volume_size           = 8
    volume_type           = "gp2"
  }
}


# source "googlecompute" "webapp-image" {
#   project_id              = "${var.gcp_project_id}"
#   source_image            = "${var.gcp_source_image}"
#   source_image_family     = "${var.gcp_source_image_family}"
#   credentials_file        = "${var.gcp_credentials_file}"
#   region                  = "${var.gcp_region}"
#   zone                    = "${var.gcp_zone}"
#   machine_type            = "${var.gcp_machine_type}"
#   disk_size               = 10
#   disk_type               = "${var.gcp_disk_type}"
#   network                 = "${var.gcp_network}"
#   tags                    = ["csye6225"]
#   image_name              = "${var.gcp_image_name}"
#   image_family            = "${var.gcp_image_family}"
#   image_description       = "WebApp Ubuntu 24.04 server image"
#   image_storage_locations = ["us"]
#   ssh_username            = "${var.ssh_username}"
# }


build {
  sources = [
    "source.amazon-ebs.webapp-ami",
    # "source.googlecompute.webapp-image",
  ]

  provisioner "file" {
    source      = "../webapp"
    destination = "/tmp/webapp"
  }

  provisioner "shell" {
    inline = [
      "set -ex",
      "echo 'Updating package list'",
      "sudo apt-get update -y",
      "echo 'Upgrading packages'",
      "sudo apt-get upgrade -y",
      # "echo 'Installing MySQL server'",
      # "sudo apt-get install -y mysql-server",
      # "echo 'Starting MySQL service'",
      # "sudo systemctl start mysql",
      # "echo 'Creating database ${var.db_name}'",
      # "sudo mysql -e \"CREATE DATABASE ${var.db_name};\"",
      # "echo 'Creating MySQL user ${var.db_user}'",
      # "sudo mysql -e \"CREATE USER '${var.db_user}'@'localhost' IDENTIFIED BY '${var.db_password}';\"",
      # "echo 'Granting privileges to user ${var.db_user}'",
      # "sudo mysql -e \"GRANT ALL PRIVILEGES ON ${var.db_name}.* TO '${var.db_user}'@'localhost';\"",
      # "echo 'Flushing privileges'",
      # "sudo mysql -e \"FLUSH PRIVILEGES;\"",
      # "echo 'Installing unzip'",
      # "sudo apt-get install -y unzip",
    ]
  }

  # Install CloudWatch agent first
  provisioner "shell" {
    inline = [
      "set -ex",
      "echo 'Installing CloudWatch agent'",
      "sudo apt-get install -y wget",
      "wget https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb",
      "sudo dpkg -i amazon-cloudwatch-agent.deb",
      "sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc",
      "sudo cp /tmp/webapp/cloudwatch-config.json /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json",
      "sudo chown root:root /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json",
      "sudo chmod 644 /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json",
      "echo 'Creating empty log file'",
      "sudo touch /var/log/csye6225.log",
      "sudo chmod 666 /var/log/csye6225.log",
      "echo 'Enabling CloudWatch agent to start on boot'",
      "sudo systemctl enable amazon-cloudwatch-agent",
      "echo 'CloudWatch agent configured successfully'",
    ]
  }

  provisioner "shell" {
    inline = [
      "set -ex",
      "echo 'Creating local user csye6225'",
      "sudo groupadd csye6225",
      "sudo useradd -m -g csye6225 -s /usr/sbin/nologin csye6225",
      "echo 'Installing libmysqlclient-dev'",
      "sudo apt-get install -y pkg-config libmysqlclient-dev",
      "echo 'Installing Python3 and pip'",
      "sudo apt install -y python3 python3-pip",
      "echo 'Installing Python3 virtual environment'",
      "sudo apt-get install -y python3-venv",
      "echo 'Creating virtual environment at /opt/venv'",
      "sudo python3 -m venv /opt/venv",
      "echo 'Changing ownership of virtual environment directory...'",
      "sudo chown -R $(whoami):$(whoami) /opt/venv",
      "echo 'Activating virtual environment'",
      ". /opt/venv/bin/activate",
      "echo 'Installing Python packages'",
      "/opt/venv/bin/pip install Flask Flask-SQLAlchemy SQLAlchemy mysqlclient Werkzeug pytest boto3 watchtower statsd",
      "echo 'Copying webapp contents to /opt/csye6225'",
      "sudo mkdir -p /opt/csye6225/webapp",
      "sudo cp -r /tmp/webapp/* /opt/csye6225/webapp/",
      "echo 'Changing ownership of /opt/csye6225/webapp directory...'",
      "sudo chown -R $(whoami):$(whoami) /opt/csye6225/webapp",
      "echo 'Adding appropriate permissions to directories'",
      "sudo chmod -R 755 /opt/venv",
      "sudo chmod -R 755 /opt/csye6225/webapp",
    ]
  }
  provisioner "shell" {
    inline = [
      "set -ex",
      # "echo 'Setting environment variables in /etc/environment'",
      # "echo 'DB_USERNAME=${var.db_user}' | sudo tee -a /etc/environment",
      # "echo 'DB_PASSWORD=${var.db_password}' | sudo tee -a /etc/environment",
      # "echo 'DB_NAME=${var.db_name}' | sudo tee -a /etc/environment",
      # ". /etc/environment",
      "echo 'Creating systemd service file'",
      "sudo cp /tmp/webapp/csye6225.service /etc/systemd/system/csye6225.service",
      "echo 'Reloading systemd daemon'",
      "sudo systemctl daemon-reload",
      "echo 'Enabling csye6225.service'",
      "sudo systemctl enable csye6225.service",
      # "echo 'Starting csye6225.service'",
      # "sudo systemctl start csye6225.service"
    ]
  }
}
