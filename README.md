# SM Image Processing API

A professional image enhancement and upscaling API using Flux Kontext and LoRA models, designed for production deployment with scalable architecture.

## 🚀 Features

- **Image Enhancement**: High-quality image enhancement using Flux Kontext models
- **Image Upscaling**: Advanced upscaling with custom LoRA models
- **Batch Processing**: Process up to 3 images per request
- **Flexible Parameters**: Configurable samplers, schedulers, and quality settings
- **Credit System**: Built-in credit management for monetization
- **Secure Authentication**: JWT + API Key dual authentication
- **Rate Limiting**: Configurable rate limits per user
- **Webhook Notifications**: Real-time job completion notifications
- **Production Ready**: Docker-based deployment with monitoring
- **GPU Optimized**: NVIDIA GPU acceleration support

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RunPod Server (RTX 3090)                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │     Nginx       │  │   FastAPI       │  │    Redis     │ │
│  │ (Load Balancer) │  │     API         │  │ (Cache/Queue)│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Celery Workers  │  │  PostgreSQL     │  │   Storage    │ │
│  │ (GPU Processing)│  │   (Database)    │  │   (Files)    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Requirements

### System Requirements
- **GPU**: NVIDIA RTX 3090 (or compatible)
- **RAM**: 32GB minimum
- **Storage**: 100GB+ SSD
- **OS**: Ubuntu 22.04 LTS

### Software Requirements
- Docker 24.0+
- Docker Compose 2.0+
- NVIDIA Docker Runtime
- Git

## 🛠️ Installation

### 1. Server Setup (RunPod)

```bash
# Clone the repository
git clone https://github.com/ayahareedyya/sm_up_api.git
cd sm_up_api

# Run the RunPod setup script
sudo bash scripts/setup_runpod.sh

# Reboot the server
sudo reboot
```

### 2. Model Setup

```bash
# Create models directory structure
mkdir -p models/flux-dev models/lora-upscale

# Download your Flux Kontext model to models/flux-dev/
# Download your LoRA upscaling model to models/lora-upscale/
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (update with your values)
nano .env
```

### 4. Deployment

```bash
# Make deployment script executable
chmod +x scripts/deploy.sh

# Deploy the application
./scripts/deploy.sh
```

## ⚙️ Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# API Configuration
API_TITLE="SM Image Processing API"
DEBUG=false
ENVIRONMENT=production

# Security
JWT_SECRET="your-jwt-secret-key"
FRONTEND_API_KEY="your-frontend-api-key"

# Database
DATABASE_URL="postgresql://user:pass@postgres:5432/sm_image_api"

# AI Models
FLUX_MODEL_PATH="/app/models/flux-dev"
LORA_MODEL_PATH="/app/models/lora-upscale"

# Processing Limits
MAX_IMAGE_SIZE_MB=10
MAX_IMAGES_PER_REQUEST=3

# Credit Costs
CREDIT_COSTS_ENHANCE_LOW=1
CREDIT_COSTS_ENHANCE_MEDIUM=2
CREDIT_COSTS_ENHANCE_HIGH=3
CREDIT_COSTS_UPSCALE_2X=2
CREDIT_COSTS_UPSCALE_4X=4
```

## 📚 API Documentation

### Authentication

All requests require dual authentication:
1. **API Key**: `X-API-Key` header
2. **JWT Token**: `Authorization: Bearer <token>` header

### Endpoints

#### Image Processing
```http
POST /api/v1/images/process
```

**Request Body:**
```json
{
  "images": [
    {
      "data": "base64_encoded_image_data",
      "filename": "image1.jpg"
    }
  ],
  "operation": "enhance",
  "parameters": {
    "sampler": "euler",
    "quality": "medium",
    "steps": 20,
    "guidance_scale": 7.5
  },
  "callback_url": "https://your-app.com/webhook"
}
```

**Response:**
```json
{
  "job_id": "uuid-job-id",
  "status": "queued",
  "estimated_time": 120,
  "credits_used": 2,
  "credits_remaining": 148,
  "message": "Job queued successfully"
}
```

#### Job Status
```http
GET /api/v1/images/status/{job_id}
```

#### User Credits
```http
GET /api/v1/auth/user-credits
```

### Supported Parameters

#### Samplers
- `euler` (default)
- `deis`
- `ddim`
- `ddpm`

#### Quality Levels
- `low` (1 credit)
- `medium` (2 credits)
- `high` (3 credits)
- `ultra` (4 credits)

#### Operations
- `enhance`: Improve image quality
- `upscale`: Increase image resolution (2x, 4x)

## 🔧 Management

### Service Management

```bash
# Start services
./scripts/deploy.sh start

# Stop services
./scripts/deploy.sh stop

# Restart services
./scripts/deploy.sh restart

# View logs
./scripts/deploy.sh logs

# Check status
./scripts/deploy.sh status

# Health check
./scripts/deploy.sh health
```

### Docker Commands

```bash
# View running containers
docker-compose ps

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Scale workers
docker-compose up -d --scale worker=2

# Execute commands in containers
docker-compose exec api bash
docker-compose exec postgres psql -U sm_user -d sm_image_api
```

## 🔍 Monitoring

### Health Checks

```bash
# API health
curl http://localhost/api/v1/health

# Database health
curl http://localhost/api/v1/health/database

# GPU health
curl http://localhost/api/v1/health/gpu
```

### Metrics (Optional)

Enable monitoring with Prometheus and Grafana:

```bash
# Start monitoring stack
docker-compose --profile monitoring up -d

# Access Grafana
open http://localhost:3000
# Login: admin/admin123
```

## 🚨 Troubleshooting

### Common Issues

#### GPU Not Detected
```bash
# Check NVIDIA drivers
nvidia-smi

# Test NVIDIA Docker
docker run --rm --gpus all nvidia/cuda:11.8-base nvidia-smi
```

#### Out of Memory
```bash
# Check GPU memory
nvidia-smi

# Reduce batch size or enable memory optimization
# Edit .env: GPU_MEMORY_FRACTION=0.7
```

#### Database Connection Issues
```bash
# Check database status
docker-compose exec postgres pg_isready

# Reset database
docker-compose down
docker volume rm sm_up_api_postgres_data
docker-compose up -d postgres
```

### Log Analysis

```bash
# API logs
docker-compose logs api | grep ERROR

# Worker logs
docker-compose logs worker | grep -E "(ERROR|FAILED)"

# System logs
journalctl -u docker.service
```

## 🔐 Security

### Production Security Checklist

- [ ] Change default passwords in `.env`
- [ ] Use strong JWT secrets
- [ ] Enable HTTPS with SSL certificates
- [ ] Configure firewall rules
- [ ] Remove debug endpoints
- [ ] Set up log monitoring
- [ ] Regular security updates

### SSL Setup

```bash
# Generate SSL certificate (Let's Encrypt)
certbot certonly --standalone -d your-domain.com

# Update nginx configuration
# Uncomment HTTPS server block in docker/nginx.conf
```

## 📈 Scaling

### Horizontal Scaling

```bash
# Scale API instances
docker-compose up -d --scale api=3

# Scale workers
docker-compose up -d --scale worker=2

# Load balancer will distribute requests automatically
```

### Vertical Scaling

- Increase server resources (GPU, RAM, CPU)
- Optimize model parameters
- Enable memory optimizations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check this README and API docs
- **Issues**: Create a GitHub issue
- **Email**: support@sm-api.com

## 🔄 Updates

### Version 1.0.0
- Initial release
- Flux Kontext integration
- LoRA upscaling support
- Credit system
- Production deployment

---

**Made with ❤️ for professional image processing**
