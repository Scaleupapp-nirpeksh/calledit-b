#!/bin/bash
# =============================================================
# CalledIt Backend — EC2 Setup Script (Ubuntu 22.04 / 24.04)
# Run this ONCE on a fresh EC2 instance.
# Usage: chmod +x setup-ec2.sh && ./setup-ec2.sh
# =============================================================

set -e

echo "=== CalledIt EC2 Setup ==="

# 1. System updates
echo "[1/6] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Docker
echo "[2/6] Installing Docker..."
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

# 3. Install Nginx
echo "[3/6] Installing Nginx..."
sudo apt-get install -y nginx

# 4. Install Certbot (for SSL later)
echo "[4/6] Installing Certbot..."
sudo apt-get install -y certbot python3-certbot-nginx

# 5. Install Git
echo "[5/6] Installing Git..."
sudo apt-get install -y git

# 6. Create app directory
echo "[6/6] Creating app directory..."
sudo mkdir -p /opt/calledit
sudo chown $USER:$USER /opt/calledit

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Log out and back in (for docker group to take effect)"
echo "  2. Clone the repo:  cd /opt/calledit && git clone https://github.com/Scaleupapp-nirpeksh/calledit-b.git ."
echo "  3. Create .env:     cp .env.example .env && nano .env"
echo "  4. Deploy:          docker compose -f docker-compose.prod.yml up -d --build"
echo "  5. Setup Nginx:     sudo cp deploy/nginx.conf /etc/nginx/sites-available/calledit"
echo "                      sudo ln -s /etc/nginx/sites-available/calledit /etc/nginx/sites-enabled/"
echo "                      sudo rm /etc/nginx/sites-enabled/default"
echo "                      sudo nginx -t && sudo systemctl reload nginx"
