#!/bin/bash

# SM Image Processing API Deployment Script
# This script deploys the API to a RunPod server

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="sm_up_api"
DOCKER_COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

# Functions
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

check_requirements() {
    log_info "Checking system requirements..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if NVIDIA Docker is available
    if ! docker run --rm --gpus all nvidia/cuda:11.8-base nvidia-smi &> /dev/null; then
        log_warning "NVIDIA Docker runtime not available. GPU acceleration will not work."
    fi
    
    log_success "System requirements check completed"
}

setup_environment() {
    log_info "Setting up environment..."
    
    # Create .env file if it doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        log_info "Creating .env file from template..."
        cp .env.example "$ENV_FILE"
        
        # Generate random secrets
        JWT_SECRET=$(openssl rand -hex 32)
        API_KEY=$(openssl rand -hex 16)
        
        # Update .env file
        sed -i "s/your-super-secret-jwt-key-change-this-in-production/$JWT_SECRET/g" "$ENV_FILE"
        sed -i "s/your-frontend-api-key-change-this/$API_KEY/g" "$ENV_FILE"
        
        log_warning "Please review and update the .env file with your specific configuration"
        log_warning "Generated JWT_SECRET and FRONTEND_API_KEY have been set"
    fi
    
    # Create necessary directories
    mkdir -p logs storage/temp storage/results models
    
    log_success "Environment setup completed"
}

download_models() {
    log_info "Checking AI models..."
    
    # Check if models directory exists and has content
    if [ ! -d "models" ] || [ -z "$(ls -A models)" ]; then
        log_warning "Models directory is empty"
        log_info "Please download your Flux Kontext and LoRA models to the 'models' directory"
        log_info "Expected structure:"
        log_info "  models/"
        log_info "    flux-dev/"
        log_info "      (Flux model files)"
        log_info "    lora-upscale/"
        log_info "      (LoRA model files)"
        
        read -p "Continue without models? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Deployment cancelled. Please add models first."
            exit 1
        fi
    else
        log_success "Models directory found"
    fi
}

build_images() {
    log_info "Building Docker images..."
    
    # Build the main application image
    docker-compose build --no-cache
    
    log_success "Docker images built successfully"
}

start_services() {
    log_info "Starting services..."
    
    # Start core services first
    log_info "Starting database and Redis..."
    docker-compose up -d postgres redis
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    sleep 10
    
    # Start API service
    log_info "Starting API service..."
    docker-compose up -d api
    
    # Wait for API to be ready
    log_info "Waiting for API to be ready..."
    sleep 15
    
    # Start workers
    log_info "Starting workers..."
    docker-compose up -d worker worker-cleanup scheduler
    
    # Start nginx
    log_info "Starting nginx..."
    docker-compose up -d nginx
    
    log_success "All services started successfully"
}

check_health() {
    log_info "Checking service health..."
    
    # Wait a bit for services to fully start
    sleep 10
    
    # Check API health
    if curl -f http://localhost/api/v1/health/simple > /dev/null 2>&1; then
        log_success "API is healthy"
    else
        log_error "API health check failed"
        return 1
    fi
    
    # Check database connection
    if docker-compose exec -T postgres pg_isready -U sm_user -d sm_image_api > /dev/null 2>&1; then
        log_success "Database is healthy"
    else
        log_error "Database health check failed"
        return 1
    fi
    
    # Check Redis connection
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis is healthy"
    else
        log_error "Redis health check failed"
        return 1
    fi
    
    log_success "All health checks passed"
}

show_status() {
    log_info "Service status:"
    docker-compose ps
    
    echo
    log_info "API endpoints:"
    echo "  Health Check: http://localhost/api/v1/health"
    echo "  API Documentation: http://localhost/docs"
    echo "  API Info: http://localhost/api/v1/info"
    
    echo
    log_info "Logs:"
    echo "  View all logs: docker-compose logs -f"
    echo "  View API logs: docker-compose logs -f api"
    echo "  View worker logs: docker-compose logs -f worker"
}

cleanup() {
    log_info "Cleaning up..."
    docker-compose down
    docker system prune -f
    log_success "Cleanup completed"
}

# Main deployment function
deploy() {
    log_info "Starting deployment of $PROJECT_NAME..."
    
    check_requirements
    setup_environment
    download_models
    build_images
    start_services
    
    if check_health; then
        show_status
        log_success "Deployment completed successfully!"
        log_info "Your SM Image Processing API is now running"
    else
        log_error "Deployment failed during health checks"
        log_info "Check logs with: docker-compose logs"
        exit 1
    fi
}

# Script options
case "${1:-deploy}" in
    "deploy")
        deploy
        ;;
    "start")
        log_info "Starting services..."
        docker-compose up -d
        check_health && show_status
        ;;
    "stop")
        log_info "Stopping services..."
        docker-compose down
        log_success "Services stopped"
        ;;
    "restart")
        log_info "Restarting services..."
        docker-compose restart
        check_health && show_status
        ;;
    "logs")
        docker-compose logs -f
        ;;
    "status")
        show_status
        ;;
    "cleanup")
        cleanup
        ;;
    "health")
        check_health
        ;;
    *)
        echo "Usage: $0 {deploy|start|stop|restart|logs|status|cleanup|health}"
        echo
        echo "Commands:"
        echo "  deploy   - Full deployment (default)"
        echo "  start    - Start all services"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  logs     - Show logs"
        echo "  status   - Show service status"
        echo "  cleanup  - Stop services and clean up"
        echo "  health   - Check service health"
        exit 1
        ;;
esac
