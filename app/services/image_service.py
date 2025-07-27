"""
Image Service

Service for managing image processing jobs and file operations.
"""

from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import UploadFile
from fastapi.responses import FileResponse
import uuid
import os
import json
import logging
from pathlib import Path

from app.models.database import ProcessingJob
from app.models.schemas import ImageProcessRequest
from app.core.config import settings
from app.core.exceptions import ImageProcessingError, StorageError
from app.workers.image_worker import process_images_task

logger = logging.getLogger(__name__)


class ImageService:
    """Service for managing image processing operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_path = Path(settings.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def create_job(self, user_id: str, request: ImageProcessRequest, estimated_cost: int) -> ProcessingJob:
        """
        Create a new processing job.
        
        Args:
            user_id: User identifier
            request: Image processing request
            estimated_cost: Estimated cost in credits
            
        Returns:
            ProcessingJob: Created job object
        """
        try:
            # Prepare input images metadata
            input_images = []
            for i, image_data in enumerate(request.images):
                input_images.append({
                    "index": i,
                    "filename": image_data.filename or f"image_{i}.jpg",
                    "size_bytes": len(image_data.data) * 3 // 4,  # Approximate size from base64
                })
            
            # Create job record
            job = ProcessingJob(
                id=uuid.uuid4(),
                user_id=user_id,
                operation=request.operation.value,
                status="queued",
                progress=0,
                parameters=request.parameters.dict(),
                input_images=input_images,
                credits_used=estimated_cost,
                estimated_cost=estimated_cost,
                callback_url=request.callback_url
            )
            
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            
            logger.info(f"Created job {job.id} for user {user_id}")
            return job
            
        except Exception as e:
            logger.error(f"Error creating job: {str(e)}")
            self.db.rollback()
            raise ImageProcessingError("Failed to create processing job", details=str(e))
    
    def queue_processing_job(self, job_id: str, request_data: Dict[str, Any]):
        """
        Queue job for background processing.
        
        Args:
            job_id: Job identifier
            request_data: Processing request data
        """
        try:
            # Send job to Celery worker
            process_images_task.delay(job_id, request_data)
            logger.info(f"Job {job_id} queued for processing")
            
        except Exception as e:
            logger.error(f"Error queuing job {job_id}: {str(e)}")
            # Update job status to failed
            self.update_job_status(job_id, "failed", error_message=f"Failed to queue job: {str(e)}")
    
    def update_job_status(
        self, 
        job_id: str, 
        status: str, 
        progress: int = None,
        error_message: str = None,
        output_images: List[str] = None,
        processing_time: float = None
    ):
        """
        Update job status and progress.
        
        Args:
            job_id: Job identifier
            status: New job status
            progress: Progress percentage (0-100)
            error_message: Error message if failed
            output_images: List of output image URLs
            processing_time: Processing time in seconds
        """
        try:
            job = self.db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if not job:
                logger.warning(f"Job not found for status update: {job_id}")
                return
            
            job.status = status
            job.updated_at = datetime.utcnow()
            
            if progress is not None:
                job.progress = progress
            
            if status == "processing" and not job.started_at:
                job.started_at = datetime.utcnow()
            
            if status in ["completed", "failed"]:
                job.completed_at = datetime.utcnow()
                job.progress = 100 if status == "completed" else job.progress
            
            if error_message:
                job.error_message = error_message
            
            if output_images:
                job.output_images = output_images
            
            if processing_time:
                job.processing_time_seconds = processing_time
            
            self.db.commit()
            logger.info(f"Updated job {job_id} status to {status}")
            
        except Exception as e:
            logger.error(f"Error updating job status: {str(e)}")
            self.db.rollback()
    
    def estimate_processing_time(self, image_count: int, operation: str, parameters: Dict[str, Any]) -> int:
        """
        Estimate processing time for a job.
        
        Args:
            image_count: Number of images
            operation: Processing operation
            parameters: Processing parameters
            
        Returns:
            int: Estimated time in seconds
        """
        try:
            # Base time per image
            base_time = 30  # 30 seconds per image
            
            # Adjust based on operation
            if operation == "upscale":
                upscale_factor = parameters.get("upscale_factor", 2)
                base_time *= upscale_factor
            
            # Adjust based on quality/steps
            steps = parameters.get("steps", 20)
            if steps > 50:
                base_time *= 1.5
            
            quality = parameters.get("quality", "medium")
            quality_multiplier = {"low": 0.7, "medium": 1.0, "high": 1.5, "ultra": 2.0}
            base_time *= quality_multiplier.get(quality, 1.0)
            
            total_time = int(base_time * image_count)
            
            # Add queue time estimate (5-30 seconds)
            total_time += min(30, max(5, image_count * 2))
            
            return total_time
            
        except Exception as e:
            logger.error(f"Error estimating processing time: {str(e)}")
            return 60 * image_count  # Fallback: 1 minute per image
    
    def save_input_images(self, job_id: str, images: List[Dict[str, Any]]) -> List[str]:
        """
        Save input images to storage.
        
        Args:
            job_id: Job identifier
            images: List of image data
            
        Returns:
            List[str]: List of saved image paths
        """
        try:
            job_dir = self.storage_path / "jobs" / str(job_id) / "input"
            job_dir.mkdir(parents=True, exist_ok=True)
            
            saved_paths = []
            for i, image_data in enumerate(images):
                filename = f"input_{i}.jpg"
                file_path = job_dir / filename
                
                # Decode and save image
                import base64
                from PIL import Image
                import io
                
                # Remove data URL prefix if present
                data = image_data["data"]
                if data.startswith("data:image/"):
                    data = data.split(",", 1)[1]
                
                img_bytes = base64.b64decode(data)
                img = Image.open(io.BytesIO(img_bytes))
                img.save(file_path, "JPEG", quality=95)
                
                saved_paths.append(str(file_path))
            
            logger.info(f"Saved {len(saved_paths)} input images for job {job_id}")
            return saved_paths
            
        except Exception as e:
            logger.error(f"Error saving input images: {str(e)}")
            raise StorageError("Failed to save input images", details=str(e))
    
    def save_output_images(self, job_id: str, output_images: List[Any]) -> List[str]:
        """
        Save output images to storage.
        
        Args:
            job_id: Job identifier
            output_images: List of processed images
            
        Returns:
            List[str]: List of output image URLs
        """
        try:
            job_dir = self.storage_path / "jobs" / str(job_id) / "output"
            job_dir.mkdir(parents=True, exist_ok=True)
            
            output_urls = []
            for i, img in enumerate(output_images):
                filename = f"output_{i}.jpg"
                file_path = job_dir / filename
                
                # Save PIL Image
                img.save(file_path, "JPEG", quality=95)
                
                # Generate URL
                url = f"{settings.storage_url_prefix}/jobs/{job_id}/output/{filename}"
                output_urls.append(url)
            
            logger.info(f"Saved {len(output_urls)} output images for job {job_id}")
            return output_urls
            
        except Exception as e:
            logger.error(f"Error saving output images: {str(e)}")
            raise StorageError("Failed to save output images", details=str(e))
    
    async def download_result_image(self, job_id: str, image_index: int) -> FileResponse:
        """
        Download a result image.
        
        Args:
            job_id: Job identifier
            image_index: Index of the image to download
            
        Returns:
            FileResponse: Image file response
        """
        try:
            file_path = self.storage_path / "jobs" / job_id / "output" / f"output_{image_index}.jpg"
            
            if not file_path.exists():
                raise StorageError("Image file not found")
            
            return FileResponse(
                path=str(file_path),
                media_type="image/jpeg",
                filename=f"processed_image_{image_index}.jpg"
            )
            
        except Exception as e:
            logger.error(f"Error downloading result image: {str(e)}")
            raise StorageError("Failed to download image", details=str(e))
    
    def cleanup_job_files(self, job_id: str, keep_outputs: bool = True):
        """
        Clean up job files to save storage space.
        
        Args:
            job_id: Job identifier
            keep_outputs: Whether to keep output images
        """
        try:
            job_dir = self.storage_path / "jobs" / str(job_id)
            
            if not keep_outputs and job_dir.exists():
                import shutil
                shutil.rmtree(job_dir)
                logger.info(f"Cleaned up all files for job {job_id}")
            else:
                # Only remove input files
                input_dir = job_dir / "input"
                if input_dir.exists():
                    import shutil
                    shutil.rmtree(input_dir)
                    logger.info(f"Cleaned up input files for job {job_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up job files: {str(e)}")
