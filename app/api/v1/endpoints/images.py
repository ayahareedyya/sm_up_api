"""
Image Processing Endpoints

Main endpoints for image enhancement and upscaling operations.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging
import uuid
from datetime import datetime

from app.core.database import get_db
from app.api.v1.dependencies import get_authenticated_user, rate_limit_check
from app.models.database import User, ProcessingJob
from app.models.schemas import (
    ImageProcessRequest, 
    JobResponse, 
    JobStatusResponse,
    JobStatus
)
from app.services.credit_service import CreditService
from app.services.image_service import ImageService
from app.core.exceptions import (
    InsufficientCreditsError,
    JobNotFoundError,
    ImageProcessingError
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["image-processing"])


@router.post("/process", response_model=JobResponse)
async def process_images(
    request: ImageProcessRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(rate_limit_check),
    db: Session = Depends(get_db)
):
    """
    Process images with enhancement or upscaling.
    
    Args:
        request: Image processing request
        background_tasks: FastAPI background tasks
        user: Authenticated user
        db: Database session
        
    Returns:
        JobResponse: Job creation response with job ID and status
    """
    try:
        # Initialize services
        credit_service = CreditService(db)
        image_service = ImageService(db)
        
        # Calculate processing cost
        cost = credit_service.calculate_cost(
            operation=request.operation.value,
            parameters=request.parameters.dict(),
            image_count=len(request.images)
        )
        
        logger.info(f"Processing request from user {user.id}: {len(request.images)} images, cost: {cost} credits")
        
        # Check and reserve credits
        if not credit_service.check_and_reserve_credits(str(user.id), cost):
            raise InsufficientCreditsError(
                required=cost,
                available=user.credits_balance
            )
        
        # Create processing job
        job = image_service.create_job(
            user_id=str(user.id),
            request=request,
            estimated_cost=cost
        )
        
        # Queue job for processing
        background_tasks.add_task(
            image_service.queue_processing_job,
            job.id,
            request.dict()
        )
        
        # Get updated user credits
        updated_user = db.query(User).filter(User.id == user.id).first()
        
        # Estimate processing time
        estimated_time = image_service.estimate_processing_time(
            len(request.images),
            request.operation.value,
            request.parameters.dict()
        )
        
        logger.info(f"Job {job.id} created successfully for user {user.id}")
        
        return JobResponse(
            job_id=str(job.id),
            status=JobStatus.QUEUED,
            estimated_time=estimated_time,
            credits_used=cost,
            credits_remaining=updated_user.credits_balance,
            message="Job queued successfully for processing"
        )
        
    except (InsufficientCreditsError, ImageProcessingError) as e:
        logger.warning(f"Processing request failed for user {user.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing request for user {user.id}: {str(e)}")
        raise ImageProcessingError("Failed to create processing job", details=str(e))


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Get processing job status.
    
    Args:
        job_id: Job identifier
        user: Authenticated user
        db: Database session
        
    Returns:
        JobStatusResponse: Current job status and details
    """
    try:
        # Find job
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == user.id
        ).first()
        
        if not job:
            raise JobNotFoundError(job_id)
        
        # Prepare response
        response_data = {
            "job_id": str(job.id),
            "status": JobStatus(job.status),
            "progress": job.progress,
            "operation": job.operation,
            "parameters": job.parameters,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        }
        
        # Add results if completed
        if job.status == "completed" and job.output_images:
            response_data["result_urls"] = job.output_images
            response_data["processing_time"] = job.processing_time_seconds
        
        # Add error message if failed
        if job.status == "failed" and job.error_message:
            response_data["error_message"] = job.error_message
        
        return JobStatusResponse(**response_data)
        
    except JobNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error getting job status {job_id} for user {user.id}: {str(e)}")
        raise ImageProcessingError("Failed to get job status", details=str(e))


@router.get("/jobs", response_model=List[JobStatusResponse])
async def get_user_jobs(
    limit: int = 10,
    offset: int = 0,
    status: str = None,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Get user's processing jobs with pagination.
    
    Args:
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        status: Filter by job status (optional)
        user: Authenticated user
        db: Database session
        
    Returns:
        List[JobStatusResponse]: List of user's jobs
    """
    try:
        # Build query
        query = db.query(ProcessingJob).filter(ProcessingJob.user_id == user.id)
        
        # Apply status filter if provided
        if status:
            query = query.filter(ProcessingJob.status == status)
        
        # Apply pagination and ordering
        jobs = query.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit).all()
        
        # Convert to response format
        job_responses = []
        for job in jobs:
            response_data = {
                "job_id": str(job.id),
                "status": JobStatus(job.status),
                "progress": job.progress,
                "operation": job.operation,
                "parameters": job.parameters,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at
            }
            
            if job.status == "completed" and job.output_images:
                response_data["result_urls"] = job.output_images
                response_data["processing_time"] = job.processing_time_seconds
            
            if job.status == "failed" and job.error_message:
                response_data["error_message"] = job.error_message
            
            job_responses.append(JobStatusResponse(**response_data))
        
        return job_responses
        
    except Exception as e:
        logger.error(f"Error getting jobs for user {user.id}: {str(e)}")
        raise ImageProcessingError("Failed to get user jobs", details=str(e))


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a processing job.
    
    Args:
        job_id: Job identifier
        user: Authenticated user
        db: Database session
        
    Returns:
        dict: Cancellation confirmation
    """
    try:
        # Find job
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == user.id
        ).first()
        
        if not job:
            raise JobNotFoundError(job_id)
        
        # Check if job can be cancelled
        if job.status in ["completed", "failed", "cancelled"]:
            raise ImageProcessingError(f"Cannot cancel job with status: {job.status}")
        
        # Cancel job
        job.status = "cancelled"
        job.updated_at = datetime.utcnow()
        
        # Refund credits if job was queued
        if job.status == "queued":
            credit_service = CreditService(db)
            credit_service.refund_credits(str(user.id), job.credits_used, f"Job {job_id} cancelled")
        
        db.commit()
        
        logger.info(f"Job {job_id} cancelled by user {user.id}")
        
        return {
            "message": "Job cancelled successfully",
            "job_id": job_id,
            "cancelled_at": datetime.utcnow().isoformat()
        }
        
    except (JobNotFoundError, ImageProcessingError):
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {job_id} for user {user.id}: {str(e)}")
        raise ImageProcessingError("Failed to cancel job", details=str(e))


@router.get("/download/{job_id}/{image_index}")
async def download_result(
    job_id: str,
    image_index: int,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Download processed image result.
    
    Args:
        job_id: Job identifier
        image_index: Index of the image to download
        user: Authenticated user
        db: Database session
        
    Returns:
        FileResponse: Processed image file
    """
    try:
        # Find job
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == user.id
        ).first()
        
        if not job:
            raise JobNotFoundError(job_id)
        
        if job.status != "completed":
            raise ImageProcessingError("Job is not completed yet")
        
        if not job.output_images or image_index >= len(job.output_images):
            raise ImageProcessingError("Image not found")
        
        # Get image service and download file
        image_service = ImageService(db)
        return await image_service.download_result_image(job_id, image_index)
        
    except (JobNotFoundError, ImageProcessingError):
        raise
    except Exception as e:
        logger.error(f"Error downloading result {job_id}/{image_index} for user {user.id}: {str(e)}")
        raise ImageProcessingError("Failed to download result", details=str(e))
