"""DeploymentGuide artifact generator for platform-specific deployment instructions.

Generates comprehensive deployment guides with platform-specific instructions,
environment configuration, security checklists, and troubleshooting sections.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeploymentGuide:
    """Generates structured deployment guides for various cloud platforms.

    Produces comprehensive deployment guidance including:
    - Platform-specific deployment instructions (AWS, GCP, Azure, Heroku, Self-hosted)
    - Environment configuration guides
    - Security checklist for deployment
    - Troubleshooting sections
    """

    # Supported platforms and their characteristics
    PLATFORMS = {
        "aws": {
            "name": "Amazon Web Services",
            "description": "Deploy to AWS using EC2, Lambda, RDS, S3, and other services",
            "services": ["EC2", "Lambda", "RDS", "S3", "CloudFront", "ElastiCache"],
        },
        "gcp": {
            "name": "Google Cloud Platform",
            "description": "Deploy to GCP using Compute Engine, Cloud Run, Firestore, and other services",
            "services": [
                "Compute Engine",
                "Cloud Run",
                "Firestore",
                "Cloud Storage",
                "Cloud CDN",
                "Memorystore",
            ],
        },
        "azure": {
            "name": "Microsoft Azure",
            "description": "Deploy to Azure using App Service, Functions, CosmosDB, and other services",
            "services": [
                "App Service",
                "Functions",
                "CosmosDB",
                "Blob Storage",
                "Application Gateway",
                "Cache for Redis",
            ],
        },
        "heroku": {
            "name": "Heroku",
            "description": "Deploy to Heroku with standard or premium dynos",
            "services": ["Dynos", "Postgres", "Redis", "Heroku Connect", "CI/CD"],
        },
        "self_hosted": {
            "name": "Self-Hosted",
            "description": "Deploy to self-hosted infrastructure (bare metal or Docker)",
            "services": ["Docker", "Docker Compose", "Kubernetes", "Bare Metal", "VPS"],
        },
    }

    def __init__(self) -> None:
        """Initialize the DeploymentGuide generator."""
        logger.info("[DeploymentGuide] Initializing deployment guide generator")

    def generate(
        self,
        project_name: str,
        tech_stack: Dict[str, Any],
        platforms: Optional[List[str]] = None,
        project_requirements: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a comprehensive deployment guide.

        Args:
            project_name: Name of the project
            tech_stack: Technology stack configuration
            platforms: List of platforms to generate guides for (defaults to all)
            project_requirements: Optional project requirements and constraints

        Returns:
            Markdown string with deployment guide
        """
        logger.info(f"[DeploymentGuide] Generating deployment guide for {project_name}")

        if platforms is None:
            platforms = list(self.PLATFORMS.keys())
        else:
            # Validate platform names
            platforms = [p for p in platforms if p in self.PLATFORMS]
            if not platforms:
                platforms = list(self.PLATFORMS.keys())
                logger.warning("[DeploymentGuide] No valid platforms specified, using all")

        content = "# Deployment Guide\n\n"

        # Add introduction
        content += self._generate_introduction(project_name)

        # Add table of contents
        content += self._generate_table_of_contents(platforms)

        # Add quick start section
        content += self._generate_quick_start_section(tech_stack)

        # Add platform-specific sections
        for platform in platforms:
            content += self._generate_platform_section(platform, tech_stack, project_requirements)

        # Add environment configuration section
        content += self._generate_environment_section(tech_stack)

        # Add security checklist
        content += self._generate_security_checklist()

        # Add troubleshooting section
        content += self._generate_troubleshooting_section(platforms)

        # Add monitoring and maintenance
        content += self._generate_monitoring_section()

        return content

    def _generate_introduction(self, project_name: str) -> str:
        """Generate introduction section."""
        section = "## Introduction\n\n"
        section += f"This deployment guide provides step-by-step instructions for deploying **{project_name}** "
        section += "to various cloud platforms and self-hosted environments.\n\n"
        section += "Choose the deployment platform that best fits your requirements, budget, and operational needs.\n\n"
        return section

    def _generate_table_of_contents(self, platforms: List[str]) -> str:
        """Generate table of contents."""
        section = "## Table of Contents\n\n"
        section += "- [Introduction](#introduction)\n"
        section += "- [Quick Start](#quick-start)\n"

        for platform in platforms:
            platform_info = self.PLATFORMS[platform]
            platform_display = platform_info["name"].replace(" ", "-").lower()
            section += f"- [{platform_info['name']}](#{platform_display})\n"

        section += "- [Environment Configuration](#environment-configuration)\n"
        section += "- [Security Checklist](#security-checklist)\n"
        section += "- [Troubleshooting](#troubleshooting)\n"
        section += "- [Monitoring & Maintenance](#monitoring--maintenance)\n\n"
        return section

    def _generate_quick_start_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate quick start section with common deployment steps."""
        section = "## Quick Start\n\n"
        section += "### Prerequisites\n\n"
        section += "Before deploying, ensure you have:\n\n"
        section += "- [ ] Git installed and repository cloned\n"
        section += "- [ ] Required runtime installed (Node.js, Python, Go, Java, etc.)\n"
        section += "- [ ] Docker installed (for containerized deployments)\n"
        section += "- [ ] Cloud CLI tools configured (AWS CLI, gcloud, az, etc.)\n"
        section += "- [ ] Environment variables configured\n"
        section += "- [ ] Database credentials and connection strings ready\n\n"

        section += "### General Deployment Steps\n\n"
        section += "```bash\n"
        section += "# 1. Clone or access your repository\n"
        section += "git clone <repository-url>\n"
        section += "cd <project-directory>\n\n"
        section += "# 2. Install dependencies\n"
        section += self._get_install_command(tech_stack)
        section += "\n"
        section += "# 3. Configure environment\n"
        section += "cp .env.example .env\n"
        section += "# Edit .env with your values\n\n"
        section += "# 4. Test locally\n"
        section += self._get_test_command(tech_stack)
        section += "\n"
        section += "# 5. Deploy to your chosen platform (see specific section below)\n"
        section += "```\n\n"
        return section

    def _generate_platform_section(
        self,
        platform: str,
        tech_stack: Dict[str, Any],
        project_requirements: Optional[Dict[str, Any]],
    ) -> str:
        """Generate platform-specific deployment section."""
        platform_info = self.PLATFORMS[platform]
        section = f"## {platform_info['name']}\n\n"
        section += f"{platform_info['description']}\n\n"

        if platform == "aws":
            section += self._generate_aws_section(tech_stack, project_requirements)
        elif platform == "gcp":
            section += self._generate_gcp_section(tech_stack, project_requirements)
        elif platform == "azure":
            section += self._generate_azure_section(tech_stack, project_requirements)
        elif platform == "heroku":
            section += self._generate_heroku_section(tech_stack)
        elif platform == "self_hosted":
            section += self._generate_self_hosted_section(tech_stack)

        return section

    def _generate_aws_section(
        self, tech_stack: Dict[str, Any], project_requirements: Optional[Dict[str, Any]]
    ) -> str:
        """Generate AWS-specific deployment instructions."""
        section = "### Key AWS Services\n\n"
        section += "- **EC2**: Virtual machines for running your application\n"
        section += "- **Lambda**: Serverless compute for event-driven workloads\n"
        section += "- **RDS**: Managed relational database service\n"
        section += "- **S3**: Object storage for static files and assets\n"
        section += "- **CloudFront**: CDN for distributed content delivery\n"
        section += "- **ElastiCache**: In-memory caching service\n\n"

        section += "### Deployment Options\n\n"

        section += "#### Option 1: EC2 Deployment\n\n"
        section += "```bash\n"
        section += "# 1. Create EC2 instance (Ubuntu 22.04 LTS recommended)\n"
        section += "# 2. SSH into the instance\n"
        section += "ssh -i your-key.pem ec2-user@your-instance-ip\n\n"
        section += "# 3. Install dependencies\n"
        section += "sudo apt-get update && sudo apt-get install -y docker.io\n"
        section += "sudo usermod -aG docker $USER\n\n"
        section += "# 4. Clone repository and deploy\n"
        section += "git clone <repository-url>\n"
        section += "cd <project-directory>\n"
        section += "docker build -t myapp .\n"
        section += "docker run -d -p 80:8000 myapp\n"
        section += "```\n\n"

        section += "#### Option 2: Lambda Deployment\n\n"
        section += "```bash\n"
        section += "# 1. Package your function\n"
        section += "zip -r function.zip .\n\n"
        section += "# 2. Create Lambda function via AWS CLI\n"
        section += "aws lambda create-function \\\n"
        section += "  --function-name myapp \\\n"
        section += "  --runtime python3.11 \\\n"
        section += "  --role arn:aws:iam::ACCOUNT:role/lambda-role \\\n"
        section += "  --handler index.handler \\\n"
        section += "  --zip-file fileb://function.zip\n\n"
        section += "# 3. Set environment variables\n"
        section += "aws lambda update-function-configuration \\\n"
        section += "  --function-name myapp \\\n"
        section += "  --environment Variables={KEY=value}\n"
        section += "```\n\n"

        section += "### Database Setup (RDS)\n\n"
        section += "```bash\n"
        section += "# Create RDS PostgreSQL instance\n"
        section += "aws rds create-db-instance \\\n"
        section += "  --db-instance-identifier myapp-db \\\n"
        section += "  --engine postgres \\\n"
        section += "  --db-instance-class db.t3.micro \\\n"
        section += "  --allocated-storage 20 \\\n"
        section += "  --master-username admin \\\n"
        section += "  --master-user-password <PASSWORD>\n"
        section += "```\n\n"

        return section

    def _generate_gcp_section(
        self, tech_stack: Dict[str, Any], project_requirements: Optional[Dict[str, Any]]
    ) -> str:
        """Generate GCP-specific deployment instructions."""
        section = "### Key GCP Services\n\n"
        section += "- **Compute Engine**: Virtual machines (VMs) for running applications\n"
        section += "- **Cloud Run**: Serverless container execution\n"
        section += "- **Firestore**: NoSQL database\n"
        section += "- **Cloud Storage**: Object storage service\n"
        section += "- **Cloud CDN**: Content delivery network\n"
        section += "- **Memorystore**: Redis caching service\n\n"

        section += "### Deployment Options\n\n"

        section += "#### Option 1: Compute Engine\n\n"
        section += "```bash\n"
        section += "# 1. Create a VM instance\n"
        section += "gcloud compute instances create myapp-vm \\\n"
        section += "  --image-family ubuntu-2204-lts \\\n"
        section += "  --image-project ubuntu-os-cloud \\\n"
        section += "  --machine-type e2-medium\n\n"
        section += "# 2. SSH into the instance\n"
        section += "gcloud compute ssh myapp-vm\n\n"
        section += "# 3. Deploy application\n"
        section += "git clone <repository-url>\n"
        section += "cd <project-directory>\n"
        section += "docker build -t gcr.io/PROJECT-ID/myapp .\n"
        section += "docker push gcr.io/PROJECT-ID/myapp\n"
        section += "```\n\n"

        section += "#### Option 2: Cloud Run\n\n"
        section += "```bash\n"
        section += "# 1. Build and push container image\n"
        section += "gcloud builds submit --tag gcr.io/PROJECT-ID/myapp\n\n"
        section += "# 2. Deploy to Cloud Run\n"
        section += "gcloud run deploy myapp \\\n"
        section += "  --image gcr.io/PROJECT-ID/myapp \\\n"
        section += "  --platform managed \\\n"
        section += "  --region us-central1 \\\n"
        section += "  --allow-unauthenticated\n\n"
        section += "# 3. View service URL\n"
        section += "gcloud run services describe myapp --region us-central1\n"
        section += "```\n\n"

        section += "### Database Setup (Firestore)\n\n"
        section += "```bash\n"
        section += "# Enable Firestore API\n"
        section += "gcloud services enable firestore.googleapis.com\n\n"
        section += "# Create Firestore database\n"
        section += "gcloud firestore databases create --region=us-central1\n"
        section += "```\n\n"

        return section

    def _generate_azure_section(
        self, tech_stack: Dict[str, Any], project_requirements: Optional[Dict[str, Any]]
    ) -> str:
        """Generate Azure-specific deployment instructions."""
        section = "### Key Azure Services\n\n"
        section += "- **App Service**: Managed web hosting platform\n"
        section += "- **Azure Functions**: Serverless compute service\n"
        section += "- **CosmosDB**: Globally distributed NoSQL database\n"
        section += "- **Blob Storage**: Cloud object storage\n"
        section += "- **Application Gateway**: Load balancer and WAF\n"
        section += "- **Cache for Redis**: Redis caching service\n\n"

        section += "### Deployment Options\n\n"

        section += "#### Option 1: App Service\n\n"
        section += "```bash\n"
        section += "# 1. Create resource group\n"
        section += "az group create --name myapp-rg --location eastus\n\n"
        section += "# 2. Create App Service plan\n"
        section += "az appservice plan create \\\n"
        section += "  --name myapp-plan \\\n"
        section += "  --resource-group myapp-rg \\\n"
        section += "  --sku B1\n\n"
        section += "# 3. Create web app\n"
        section += "az webapp create \\\n"
        section += "  --name myapp \\\n"
        section += "  --resource-group myapp-rg \\\n"
        section += "  --plan myapp-plan\n\n"
        section += "# 4. Deploy from GitHub\n"
        section += "az webapp deployment source config-zip \\\n"
        section += "  --resource-group myapp-rg \\\n"
        section += "  --name myapp \\\n"
        section += "  --src <zip-file>\n"
        section += "```\n\n"

        section += "#### Option 2: Azure Functions\n\n"
        section += "```bash\n"
        section += "# 1. Create storage account\n"
        section += "az storage account create \\\n"
        section += "  --name mystorageaccount \\\n"
        section += "  --resource-group myapp-rg\n\n"
        section += "# 2. Create Function App\n"
        section += "az functionapp create \\\n"
        section += "  --name myapp \\\n"
        section += "  --storage-account mystorageaccount \\\n"
        section += "  --resource-group myapp-rg \\\n"
        section += "  --runtime python \\\n"
        section += "  --functions-version 4\n\n"
        section += "# 3. Deploy function code\n"
        section += "func azure functionapp publish myapp\n"
        section += "```\n\n"

        section += "### Database Setup (CosmosDB)\n\n"
        section += "```bash\n"
        section += "# Create CosmosDB account\n"
        section += "az cosmosdb create \\\n"
        section += "  --name myapp-cosmos \\\n"
        section += "  --resource-group myapp-rg \\\n"
        section += "  --default-consistency-level Session\n"
        section += "```\n\n"

        return section

    def _generate_heroku_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate Heroku-specific deployment instructions."""
        section = "### Key Features\n\n"
        section += "- **Simple deployment**: Push code and it's deployed automatically\n"
        section += "- **Managed databases**: Built-in PostgreSQL and Redis\n"
        section += "- **CI/CD**: Automatic deployments from Git\n"
        section += "- **Scaling**: Easy horizontal scaling with dynos\n\n"

        section += "### Deployment Steps\n\n"
        section += "```bash\n"
        section += "# 1. Install Heroku CLI\n"
        section += "curl https://cli-assets.heroku.com/install.sh | sh\n\n"
        section += "# 2. Login to Heroku\n"
        section += "heroku login\n\n"
        section += "# 3. Create a new Heroku app\n"
        section += "heroku create myapp\n\n"
        section += "# 4. Add environment variables\n"
        section += "heroku config:set KEY=value\n\n"
        section += "# 5. Add PostgreSQL addon\n"
        section += "heroku addons:create heroku-postgresql:hobby-dev\n\n"
        section += "# 6. Deploy by pushing to Heroku git\n"
        section += "git push heroku main\n\n"
        section += "# 7. View logs\n"
        section += "heroku logs --tail\n"
        section += "```\n\n"

        section += "### Database Connections\n\n"
        section += "Heroku automatically sets `DATABASE_URL` environment variable when you add a database addon.\n\n"

        return section

    def _generate_self_hosted_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate self-hosted deployment instructions."""
        section = "### Deployment Options\n\n"

        section += "#### Option 1: Docker Containerization\n\n"
        section += "```dockerfile\n"
        section += "FROM python:3.11-slim\n\n"
        section += "WORKDIR /app\n"
        section += "COPY requirements.txt .\n"
        section += "RUN pip install -r requirements.txt\n"
        section += "COPY . .\n"
        section += "EXPOSE 8000\n"
        section += 'CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"]\n'
        section += "```\n\n"

        section += "#### Option 2: Docker Compose\n\n"
        section += "```yaml\n"
        section += "version: '3.8'\n"
        section += "services:\n"
        section += "  app:\n"
        section += "    build: .\n"
        section += "    ports:\n"
        section += "      - '80:8000'\n"
        section += "    environment:\n"
        section += "      - DATABASE_URL=postgresql://user:pass@db:5432/myapp\n"
        section += "    depends_on:\n"
        section += "      - db\n"
        section += "  db:\n"
        section += "    image: postgres:15\n"
        section += "    environment:\n"
        section += "      - POSTGRES_DB=myapp\n"
        section += "      - POSTGRES_USER=user\n"
        section += "      - POSTGRES_PASSWORD=pass\n"
        section += "    volumes:\n"
        section += "      - postgres_data:/var/lib/postgresql/data\n"
        section += "volumes:\n"
        section += "  postgres_data:\n"
        section += "```\n\n"

        section += "#### Option 3: Kubernetes\n\n"
        section += "```yaml\n"
        section += "apiVersion: apps/v1\n"
        section += "kind: Deployment\n"
        section += "metadata:\n"
        section += "  name: myapp\n"
        section += "spec:\n"
        section += "  replicas: 3\n"
        section += "  selector:\n"
        section += "    matchLabels:\n"
        section += "      app: myapp\n"
        section += "  template:\n"
        section += "    metadata:\n"
        section += "      labels:\n"
        section += "        app: myapp\n"
        section += "    spec:\n"
        section += "      containers:\n"
        section += "      - name: app\n"
        section += "        image: myapp:latest\n"
        section += "        ports:\n"
        section += "        - containerPort: 8000\n"
        section += "        env:\n"
        section += "        - name: DATABASE_URL\n"
        section += "          valueFrom:\n"
        section += "            secretKeyRef:\n"
        section += "              name: app-secrets\n"
        section += "              key: database-url\n"
        section += "```\n\n"

        section += "#### Option 4: Bare Metal / VPS\n\n"
        section += "```bash\n"
        section += "# 1. SSH into your server\n"
        section += "ssh user@your-server-ip\n\n"
        section += "# 2. Update system\n"
        section += "sudo apt-get update && sudo apt-get upgrade -y\n\n"
        section += "# 3. Install required software\n"
        section += "sudo apt-get install -y python3 python3-pip postgresql nginx\n\n"
        section += "# 4. Clone repository\n"
        section += "git clone <repository-url>\n"
        section += "cd <project-directory>\n\n"
        section += "# 5. Install dependencies\n"
        section += "pip install -r requirements.txt\n\n"
        section += "# 6. Configure systemd service\n"
        section += "sudo nano /etc/systemd/system/myapp.service\n\n"
        section += "# 7. Start application\n"
        section += "sudo systemctl start myapp\n"
        section += "sudo systemctl enable myapp\n"
        section += "```\n\n"

        return section

    def _generate_environment_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate environment configuration section."""
        section = "## Environment Configuration\n\n"
        section += "### Required Environment Variables\n\n"
        section += "Create a `.env` file with the following variables:\n\n"
        section += "```bash\n"
        section += "# Application\n"
        section += "APP_NAME=MyApplication\n"
        section += "APP_ENV=production\n"
        section += "DEBUG=false\n\n"
        section += "# Database\n"
        section += "DATABASE_URL=postgresql://user:password@localhost:5432/myapp\n"
        section += "DATABASE_POOL_SIZE=10\n\n"
        section += "# Cache\n"
        section += "REDIS_URL=redis://localhost:6379/0\n"
        section += "CACHE_TTL=3600\n\n"
        section += "# Security\n"
        section += "SECRET_KEY=your-secret-key-here\n"
        section += "ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com\n"
        section += "CORS_ALLOWED_ORIGINS=https://yourdomain.com\n\n"
        section += "# Third-party services\n"
        section += "STRIPE_SECRET_KEY=sk_live_...\n"
        section += "SENDGRID_API_KEY=SG....\n"
        section += "```\n\n"

        section += "### Platform-Specific Configuration\n\n"
        section += "#### AWS\n"
        section += "```bash\n"
        section += "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
        section += "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
        section += "AWS_REGION=us-east-1\n"
        section += "AWS_S3_BUCKET=my-app-bucket\n"
        section += "```\n\n"

        section += "#### GCP\n"
        section += "```bash\n"
        section += "GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json\n"
        section += "GCP_PROJECT_ID=my-project-id\n"
        section += "GCP_STORAGE_BUCKET=my-app-bucket\n"
        section += "```\n\n"

        section += "#### Azure\n"
        section += "```bash\n"
        section += "AZURE_SUBSCRIPTION_ID=subscription-id\n"
        section += "AZURE_RESOURCE_GROUP=my-app-rg\n"
        section += "AZURE_STORAGE_ACCOUNT=mystorageaccount\n"
        section += "```\n\n"

        return section

    def _generate_security_checklist(self) -> str:
        """Generate security checklist for deployment."""
        section = "## Security Checklist\n\n"
        section += "Before deploying to production, verify the following:\n\n"

        section += "### Application Security\n"
        section += "- [ ] Remove all debug and verbose logging in production code\n"
        section += "- [ ] Disable DEBUG mode in configuration\n"
        section += "- [ ] Implement proper input validation and sanitization\n"
        section += "- [ ] Use parameterized queries to prevent SQL injection\n"
        section += "- [ ] Implement CSRF protection\n"
        section += "- [ ] Set secure HTTP headers (CSP, X-Frame-Options, etc.)\n"
        section += "- [ ] Implement rate limiting and DDoS protection\n"
        section += "- [ ] Use HTTPS/TLS for all communications\n"
        section += "- [ ] Implement proper authentication and authorization\n"
        section += "- [ ] Use strong password hashing (bcrypt, scrypt, argon2)\n\n"

        section += "### Data Security\n"
        section += "- [ ] Encrypt sensitive data at rest\n"
        section += "- [ ] Use encrypted connections for database\n"
        section += "- [ ] Implement proper backup and recovery procedures\n"
        section += "- [ ] Set up database access logging\n"
        section += "- [ ] Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)\n"
        section += "- [ ] Never commit secrets to version control\n"
        section += "- [ ] Rotate database credentials regularly\n"
        section += "- [ ] Implement data retention and deletion policies\n\n"

        section += "### Infrastructure Security\n"
        section += "- [ ] Configure firewall rules and network policies\n"
        section += "- [ ] Use VPC/virtual networks for isolation\n"
        section += "- [ ] Enable VPN for administrative access\n"
        section += "- [ ] Configure auto-scaling with proper limits\n"
        section += "- [ ] Enable security monitoring and alerts\n"
        section += "- [ ] Set up WAF (Web Application Firewall) rules\n"
        section += "- [ ] Implement DDoS protection\n"
        section += "- [ ] Use trusted container registries\n"
        section += "- [ ] Scan container images for vulnerabilities\n"
        section += "- [ ] Disable root access and use minimal base images\n\n"

        section += "### Access Control\n"
        section += "- [ ] Implement principle of least privilege\n"
        section += "- [ ] Use IAM roles and policies correctly\n"
        section += "- [ ] Enable MFA for administrative access\n"
        section += "- [ ] Limit SSH key access\n"
        section += "- [ ] Audit and restrict service account permissions\n"
        section += "- [ ] Regularly review access logs\n"
        section += "- [ ] Remove unused service accounts\n"
        section += "- [ ] Implement break-glass procedures for emergency access\n\n"

        section += "### Monitoring & Logging\n"
        section += "- [ ] Enable application error logging\n"
        section += "- [ ] Set up security event logging\n"
        section += "- [ ] Configure log rotation and retention\n"
        section += "- [ ] Monitor for suspicious activities\n"
        section += "- [ ] Set up alerting for security events\n"
        section += "- [ ] Implement centralized log management\n"
        section += "- [ ] Monitor system resources for anomalies\n\n"

        section += "### Compliance\n"
        section += "- [ ] Review applicable compliance requirements (GDPR, HIPAA, SOC 2, etc.)\n"
        section += "- [ ] Implement data privacy controls\n"
        section += "- [ ] Document security procedures\n"
        section += "- [ ] Conduct security audit/penetration testing\n"
        section += "- [ ] Maintain incident response plan\n"
        section += "- [ ] Keep software dependencies up to date\n"
        section += "- [ ] Document third-party integrations and security\n\n"

        return section

    def _generate_troubleshooting_section(self, platforms: List[str]) -> str:
        """Generate troubleshooting section."""
        section = "## Troubleshooting\n\n"

        section += "### Common Issues\n\n"
        section += "#### Application won't start\n"
        section += "1. Check environment variables are set correctly\n"
        section += "2. Verify database connection string and credentials\n"
        section += "3. Check application logs for error messages\n"
        section += "4. Ensure all dependencies are installed\n"
        section += "5. Verify file permissions for log directories\n\n"

        section += "#### Database connection failed\n"
        section += "1. Verify database is running and accessible\n"
        section += "2. Check DATABASE_URL is correctly formatted\n"
        section += "3. Verify database credentials\n"
        section += "4. Check firewall rules allow database access\n"
        section += "5. Ensure database port is not blocked\n"
        section += "6. Test connection with `psql` or `mysql` client\n\n"

        section += "#### High memory/CPU usage\n"
        section += "1. Check for memory leaks in application code\n"
        section += "2. Review database query performance\n"
        section += "3. Check for infinite loops or blocking operations\n"
        section += "4. Monitor third-party library performance\n"
        section += "5. Consider increasing instance resources\n\n"

        section += "#### Slow response times\n"
        section += "1. Enable and review application profiling\n"
        section += "2. Check database query performance\n"
        section += "3. Verify cache is working correctly\n"
        section += "4. Review API response times\n"
        section += "5. Check network latency\n"
        section += "6. Consider implementing pagination for large datasets\n\n"

        section += "### Getting Help\n\n"
        section += "1. Check application logs for error messages\n"
        section += "2. Enable verbose/debug logging temporarily\n"
        section += "3. Search platform documentation\n"
        section += "4. Check community forums and Stack Overflow\n"
        section += "5. Contact platform support with reproduction steps\n\n"

        return section

    def _generate_monitoring_section(self) -> str:
        """Generate monitoring and maintenance section."""
        section = "## Monitoring & Maintenance\n\n"

        section += "### Application Monitoring\n\n"
        section += "```bash\n"
        section += "# Application Performance Monitoring (APM)\n"
        section += "# Tools: New Relic, Datadog, Sentry, Splunk, ELK Stack\n"
        section += "```\n\n"

        section += "Key metrics to monitor:\n"
        section += "- **Response Time**: Average and P95/P99 latency\n"
        section += "- **Error Rate**: Percentage of failed requests\n"
        section += "- **Throughput**: Requests per second\n"
        section += "- **CPU Usage**: Average and peak CPU utilization\n"
        section += "- **Memory Usage**: Heap usage and garbage collection\n"
        section += "- **Database Performance**: Query execution time, connection pool status\n"
        section += "- **Cache Hit Rate**: Effectiveness of caching strategy\n\n"

        section += "### Alerting Rules\n\n"
        section += "Set up alerts for:\n"
        section += "- Error rate exceeds 1%\n"
        section += "- Response time exceeds 1000ms\n"
        section += "- CPU usage exceeds 80%\n"
        section += "- Memory usage exceeds 85%\n"
        section += "- Database connection pool exhaustion\n"
        section += "- Disk space below 10%\n"
        section += "- Health check failures\n\n"

        section += "### Maintenance Tasks\n\n"
        section += "**Daily:**\n"
        section += "- Review application errors and logs\n"
        section += "- Monitor performance metrics\n"
        section += "- Check system health\n\n"

        section += "**Weekly:**\n"
        section += "- Review security logs\n"
        section += "- Check backup status\n"
        section += "- Monitor database statistics\n"
        section += "- Review slow query logs\n\n"

        section += "**Monthly:**\n"
        section += "- Update dependencies and security patches\n"
        section += "- Review and rotate access credentials\n"
        section += "- Analyze performance trends\n"
        section += "- Test disaster recovery procedures\n"
        section += "- Review cost and resource utilization\n\n"

        section += "**Quarterly:**\n"
        section += "- Conduct security audit\n"
        section += "- Review and update documentation\n"
        section += "- Performance optimization review\n"
        section += "- Disaster recovery drill\n\n"

        return section

    @staticmethod
    def _get_install_command(tech_stack: Dict[str, Any]) -> str:
        """Get appropriate install command based on tech stack."""
        if "npm" in str(tech_stack).lower() or "node" in str(tech_stack).lower():
            return "npm install"
        elif "pip" in str(tech_stack).lower() or "python" in str(tech_stack).lower():
            return "pip install -r requirements.txt"
        elif "go" in str(tech_stack).lower():
            return "go mod download && go mod tidy"
        elif "maven" in str(tech_stack).lower():
            return "mvn install"
        elif "gradle" in str(tech_stack).lower():
            return "gradle build"
        else:
            return "# Install dependencies as per your build system"

    @staticmethod
    def _get_test_command(tech_stack: Dict[str, Any]) -> str:
        """Get appropriate test command based on tech stack."""
        if "npm" in str(tech_stack).lower() or "node" in str(tech_stack).lower():
            return "npm test"
        elif "pytest" in str(tech_stack).lower() or "python" in str(tech_stack).lower():
            return "pytest tests/ -v"
        elif "go" in str(tech_stack).lower():
            return "go test ./..."
        elif "java" in str(tech_stack).lower():
            return "mvn test"
        else:
            return "# Run tests as per your test framework"
