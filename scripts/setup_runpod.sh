#!/bin/bash

# RunPod Server Setup Script for SM Image Processing API
# This script prepares a fresh RunPod server for deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root. This is acceptable for initial setup."
    else
        log_info "Running as non-root user: $(whoami)"
    fi
}

# Update system packages
update_system() {
    log_info "Updating system packages..."
    
    apt-get update
    apt-get upgrade -y
    
    log_success "System packages updated"
}

# Install essential packages
install_essentials() {
    log_info "Installing essential packages..."
    
    apt-get install -y \
        curl \
        wget \
        git \
        vim \
        htop \
        unzip \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release \
        build-essential \
        python3 \
        python3-pip \
        python3-dev
    
    log_success "Essential packages installed"
}

# Install Docker
install_docker() {
    log_info "Installing Docker..."
    
    # Remove old versions
    apt-get remove -y docker docker-engine docker.io containerd runc || true
    
    # Add Docker's official GPG key
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    
    # Add Docker repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
    
    # Add current user to docker group (if not root)
    if [[ $EUID -ne 0 ]]; then
        usermod -aG docker $USER
        log_warning "Please log out and back in for Docker group membership to take effect"
    fi
    
    log_success "Docker installed successfully"
}

# Install Docker Compose
install_docker_compose() {
    log_info "Installing Docker Compose..."
    
    # Get latest version
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    
    # Download and install
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Create symlink
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    
    log_success "Docker Compose installed successfully"
}

# Install NVIDIA Docker
install_nvidia_docker() {
    log_info "Installing NVIDIA Docker runtime..."
    
    # Check if NVIDIA drivers are installed
    if ! command -v nvidia-smi &> /dev/null; then
        log_error "NVIDIA drivers not found. Please install NVIDIA drivers first."
        return 1
    fi
    
    # Add NVIDIA Docker repository
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list
    
    # Install NVIDIA Docker
    apt-get update
    apt-get install -y nvidia-docker2
    
    # Restart Docker
    systemctl restart docker
    
    # Test NVIDIA Docker
    if docker run --rm --gpus all nvidia/cuda:11.8-base nvidia-smi; then
        log_success "NVIDIA Docker installed and tested successfully"
    else
        log_error "NVIDIA Docker test failed"
        return 1
    fi
}

# Configure firewall
configure_firewall() {
    log_info "Configuring firewall..."
    
    # Install ufw if not present
    apt-get install -y ufw
    
    # Reset firewall rules
    ufw --force reset
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH
    ufw allow ssh
    
    # Allow HTTP and HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    
    # Allow specific ports for development (remove in production)
    ufw allow 8000/tcp  # API
    ufw allow 5432/tcp  # PostgreSQL (remove in production)
    ufw allow 6379/tcp  # Redis (remove in production)
    
    # Enable firewall
    ufw --force enable
    
    log_success "Firewall configured"
}

# Optimize system for AI workloads
optimize_system() {
    log_info "Optimizing system for AI workloads..."
    
    # Increase file limits
    cat >> /etc/security/limits.conf << EOF
* soft nofile 65536
* hard nofile 65536
* soft nproc 65536
* hard nproc 65536
EOF
    
    # Optimize kernel parameters
    cat >> /etc/sysctl.conf << EOF
# Network optimizations
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 65536 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
net.core.netdev_max_backlog = 5000

# Memory optimizations
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
EOF
    
    # Apply sysctl changes
    sysctl -p
    
    log_success "System optimizations applied"
}

# Create project directory and clone repository
setup_project() {
    log_info "Setting up project directory..."
    
    PROJECT_DIR="/opt/sm_up_api"
    
    # Create project directory
    mkdir -p $PROJECT_DIR
    cd $PROJECT_DIR
    
    # Clone repository (you'll need to update this URL)
    log_info "Cloning repository..."
    # git clone https://github.com/ayahareedyya/sm_up_api.git .
    
    log_warning "Please clone your repository manually:"
    log_warning "cd $PROJECT_DIR && git clone https://github.com/ayahareedyya/sm_up_api.git ."
    
    # Set permissions
    chown -R $USER:$USER $PROJECT_DIR
    
    log_success "Project directory setup completed"
}

# Install Python dependencies for management scripts
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    pip3 install --upgrade pip
    pip3 install docker-compose
    
    log_success "Python dependencies installed"
}

# Create systemd service for auto-start
create_systemd_service() {
    log_info "Creating systemd service..."
    
    cat > /etc/systemd/system/sm-image-api.service << EOF
[Unit]
Description=SM Image Processing API
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/sm_up_api
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable sm-image-api.service
    
    log_success "Systemd service created"
}

# Main setup function
main() {
    log_info "Starting RunPod server setup for SM Image Processing API..."
    
    check_root
    update_system
    install_essentials
    install_docker
    install_docker_compose
    
    # Install NVIDIA Docker if GPU is available
    if command -v nvidia-smi &> /dev/null; then
        install_nvidia_docker
    else
        log_warning "NVIDIA drivers not found. Skipping NVIDIA Docker installation."
    fi
    
    configure_firewall
    optimize_system
    setup_project
    install_python_deps
    create_systemd_service
    
    log_success "RunPod server setup completed successfully!"
    
    echo
    log_info "Next steps:"
    echo "1. Clone your repository to /opt/sm_up_api"
    echo "2. Add your AI models to the models/ directory"
    echo "3. Configure your .env file"
    echo "4. Run the deployment script: ./scripts/deploy.sh"
    
    echo
    log_warning "Please reboot the server to ensure all changes take effect:"
    log_warning "sudo reboot"
}

# Run main function
main "$@"
