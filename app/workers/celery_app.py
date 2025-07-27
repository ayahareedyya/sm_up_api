"""
Celery Application Configuration

Celery setup for background image processing tasks.
"""

from celery import Celery
import os
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    "sm_image_processor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.image_worker"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=["json"],
    result_expires=3600,  # Results expire after 1 hour
    timezone="UTC",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "app.workers.image_worker.process_images_task": {"queue": "image_processing"},
        "app.workers.image_worker.cleanup_job_task": {"queue": "cleanup"},
    },
    
    # Worker configuration
    worker_prefetch_multiplier=1,  # Process one task at a time
    task_acks_late=True,  # Acknowledge task after completion
    worker_disable_rate_limits=False,
    
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,       # 10 minutes hard limit
    
    # Retry configuration
    task_default_retry_delay=60,  # 1 minute retry delay
    task_max_retries=3,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Task annotations for specific configurations
celery_app.conf.task_annotations = {
    "app.workers.image_worker.process_images_task": {
        "rate_limit": "10/m",  # 10 tasks per minute
        "time_limit": 600,     # 10 minutes
        "soft_time_limit": 300, # 5 minutes
    },
    "app.workers.image_worker.cleanup_job_task": {
        "rate_limit": "100/m",  # 100 cleanup tasks per minute
        "time_limit": 60,       # 1 minute
    },
}

# Logging configuration
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks."""
    # Cleanup old job files every hour
    sender.add_periodic_task(
        3600.0,  # Every hour
        cleanup_old_jobs.s(),
        name="cleanup_old_jobs"
    )

@celery_app.task
def cleanup_old_jobs():
    """Periodic task to cleanup old job files."""
    try:
        from app.workers.image_worker import cleanup_old_job_files
        cleanup_old_job_files()
        logger.info("Periodic cleanup completed")
    except Exception as e:
        logger.error(f"Periodic cleanup failed: {str(e)}")

if __name__ == "__main__":
    celery_app.start()
