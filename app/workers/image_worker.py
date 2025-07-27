"""
Image Processing Worker

Celery worker for processing images using Flux Kontext and LoRA models.
"""

import os
import time
import logging
import traceback
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path

import torch
from PIL import Image
import base64
import io
import numpy as np

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.image_service import ImageService

logger = logging.getLogger(__name__)


class FluxImageProcessor:
    """Image processor using Flux Kontext and LoRA models."""

    def __init__(self):
        # Auto-detect device
        self.device = self._detect_device()
        self.flux_pipe = None
        self.lora_pipe = None
        self.model_loaded = False
        self.use_cpu_fallback = self.device == "cpu"

        logger.info(f"Initialized FluxImageProcessor with device: {self.device}")

    def _detect_device(self):
        """Auto-detect the best available device."""
        try:
            if torch.cuda.is_available():
                device = "cuda"
                logger.info(f"CUDA available: {torch.cuda.get_device_name()}")
                logger.info(f"CUDA memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            else:
                device = "cpu"
                logger.warning("CUDA not available, using CPU")

            # Override with settings if specified
            if hasattr(settings, 'torch_device') and settings.torch_device:
                if settings.torch_device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA requested but not available, falling back to CPU")
                    device = "cpu"
                else:
                    device = settings.torch_device

            return device
        except Exception as e:
            logger.error(f"Error detecting device: {e}")
            return "cpu"
        
    def load_models(self):
        """Load Flux and LoRA models with CPU/GPU auto-detection."""
        try:
            if self.model_loaded:
                return

            logger.info(f"Loading Flux Kontext model on {self.device}...")

            # Check if model path exists
            if not os.path.exists(settings.flux_model_path):
                raise FileNotFoundError(f"Flux model not found at: {settings.flux_model_path}")

            # Import diffusers components
            from diffusers import FluxPipeline, DiffusionPipeline

            # Configure model loading based on device
            if self.device == "cpu":
                logger.info("Loading model for CPU inference...")
                self.flux_pipe = FluxPipeline.from_pretrained(
                    settings.flux_model_path,
                    torch_dtype=torch.float32,  # Use float32 for CPU
                    device_map=None,
                    low_cpu_mem_usage=True
                )
                self.flux_pipe.to("cpu")
            else:
                logger.info("Loading model for GPU inference...")
                # Determine appropriate dtype based on GPU memory
                torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

                self.flux_pipe = FluxPipeline.from_pretrained(
                    settings.flux_model_path,
                    torch_dtype=torch_dtype,
                    device_map="auto" if torch.cuda.is_available() else None
                )
                self.flux_pipe.to(self.device)

            # Load LoRA model for upscaling if available
            if os.path.exists(settings.lora_model_path):
                logger.info("Loading LoRA upscaling model...")
                try:
                    self.flux_pipe.load_lora_weights(settings.lora_model_path)
                except Exception as e:
                    logger.warning(f"Failed to load LoRA weights: {e}")

            # Apply optimizations based on device
            self._apply_optimizations()

            self.model_loaded = True
            logger.info(f"Models loaded successfully on {self.device}")

        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")
            # Try CPU fallback if GPU loading failed
            if self.device != "cpu":
                logger.info("Attempting CPU fallback...")
                self.device = "cpu"
                self.use_cpu_fallback = True
                self.load_models()
            else:
                raise

    def _apply_optimizations(self):
        """Apply device-specific optimizations."""
        try:
            if self.device == "cpu":
                # CPU optimizations
                logger.info("Applying CPU optimizations...")
                if hasattr(self.flux_pipe, 'enable_attention_slicing'):
                    self.flux_pipe.enable_attention_slicing()

            else:
                # GPU optimizations
                logger.info("Applying GPU optimizations...")
                if hasattr(self.flux_pipe, 'enable_model_cpu_offload'):
                    self.flux_pipe.enable_model_cpu_offload()

                if hasattr(self.flux_pipe, 'enable_attention_slicing'):
                    self.flux_pipe.enable_attention_slicing()

                if hasattr(self.flux_pipe, 'enable_xformers_memory_efficient_attention'):
                    try:
                        self.flux_pipe.enable_xformers_memory_efficient_attention()
                        logger.info("Enabled xformers memory efficient attention")
                    except Exception as e:
                        logger.warning(f"Could not enable xformers: {e}")

        except Exception as e:
            logger.warning(f"Error applying optimizations: {e}")
    
    def enhance_image(self, image: Image.Image, parameters: Dict[str, Any]) -> Image.Image:
        """
        Enhance image quality using Flux.
        
        Args:
            image: Input PIL Image
            parameters: Processing parameters
            
        Returns:
            Image.Image: Enhanced image
        """
        try:
            # Prepare parameters
            sampler = parameters.get("sampler", "euler")
            steps = parameters.get("steps", 20)
            guidance_scale = parameters.get("guidance_scale", 7.5)
            strength = parameters.get("strength", 0.8)
            seed = parameters.get("seed")
            
            # Set random seed if provided
            if seed is not None:
                torch.manual_seed(seed)
                np.random.seed(seed)
            
            # Process image
            with torch.autocast(self.device):
                result = self.flux_pipe(
                    image=image,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    strength=strength,
                    generator=torch.Generator(device=self.device).manual_seed(seed) if seed else None
                )
            
            return result.images[0]
            
        except Exception as e:
            logger.error(f"Error enhancing image: {str(e)}")
            raise
    
    def upscale_image(self, image: Image.Image, parameters: Dict[str, Any]) -> Image.Image:
        """
        Upscale image using LoRA model.
        
        Args:
            image: Input PIL Image
            parameters: Processing parameters
            
        Returns:
            Image.Image: Upscaled image
        """
        try:
            upscale_factor = parameters.get("upscale_factor", 2)
            steps = parameters.get("steps", 20)
            guidance_scale = parameters.get("guidance_scale", 7.5)
            seed = parameters.get("seed")
            
            # Set random seed if provided
            if seed is not None:
                torch.manual_seed(seed)
                np.random.seed(seed)
            
            # Calculate target size
            original_size = image.size
            target_size = (
                original_size[0] * upscale_factor,
                original_size[1] * upscale_factor
            )
            
            # Process with LoRA
            with torch.autocast(self.device):
                result = self.flux_pipe(
                    image=image,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    height=target_size[1],
                    width=target_size[0],
                    generator=torch.Generator(device=self.device).manual_seed(seed) if seed else None
                )
            
            return result.images[0]
            
        except Exception as e:
            logger.error(f"Error upscaling image: {str(e)}")
            raise
    
    def process_image(self, image_data: str, operation: str, parameters: Dict[str, Any]) -> Image.Image:
        """
        Process a single image.
        
        Args:
            image_data: Base64 encoded image data
            operation: Processing operation (enhance/upscale)
            parameters: Processing parameters
            
        Returns:
            Image.Image: Processed image
        """
        try:
            # Decode image
            if image_data.startswith("data:image/"):
                image_data = image_data.split(",", 1)[1]
            
            img_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(img_bytes))
            
            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Process based on operation
            if operation == "enhance":
                return self.enhance_image(image, parameters)
            elif operation == "upscale":
                return self.upscale_image(image, parameters)
            else:
                raise ValueError(f"Unknown operation: {operation}")
                
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise


# Global processor instance
processor = FluxImageProcessor()


@celery_app.task(bind=True, name="process_images_task")
def process_images_task(self, job_id: str, request_data: Dict[str, Any]):
    """
    Main task for processing images.
    
    Args:
        job_id: Job identifier
        request_data: Processing request data
    """
    start_time = time.time()
    db = SessionLocal()
    
    try:
        logger.info(f"Starting image processing for job {job_id}")
        
        # Initialize services
        image_service = ImageService(db)
        
        # Load models if not already loaded
        processor.load_models()
        
        # Update job status to processing
        image_service.update_job_status(job_id, "processing", progress=0)
        
        # Extract request data
        images = request_data["images"]
        operation = request_data["operation"]
        parameters = request_data["parameters"]
        
        # Process each image
        processed_images = []
        total_images = len(images)
        
        for i, image_data in enumerate(images):
            try:
                logger.info(f"Processing image {i+1}/{total_images} for job {job_id}")
                
                # Process image
                result_image = processor.process_image(
                    image_data["data"],
                    operation,
                    parameters
                )
                
                processed_images.append(result_image)
                
                # Update progress
                progress = int((i + 1) / total_images * 90)  # 90% for processing, 10% for saving
                image_service.update_job_status(job_id, "processing", progress=progress)
                
                logger.info(f"Completed image {i+1}/{total_images} for job {job_id}")
                
            except Exception as e:
                logger.error(f"Error processing image {i+1} for job {job_id}: {str(e)}")
                raise
        
        # Save output images
        logger.info(f"Saving output images for job {job_id}")
        output_urls = image_service.save_output_images(job_id, processed_images)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Update job as completed
        image_service.update_job_status(
            job_id,
            "completed",
            progress=100,
            output_images=output_urls,
            processing_time=processing_time
        )
        
        logger.info(f"Job {job_id} completed successfully in {processing_time:.2f} seconds")
        
        # Send webhook notification if provided
        callback_url = request_data.get("callback_url")
        if callback_url:
            send_webhook_notification.delay(job_id, callback_url, "completed")
        
        # Schedule cleanup
        cleanup_job_task.apply_async(args=[job_id], countdown=3600)  # Cleanup after 1 hour
        
    except Exception as e:
        error_message = f"Processing failed: {str(e)}"
        logger.error(f"Job {job_id} failed: {error_message}")
        logger.error(traceback.format_exc())
        
        # Update job as failed
        image_service.update_job_status(
            job_id,
            "failed",
            error_message=error_message
        )
        
        # Send webhook notification if provided
        callback_url = request_data.get("callback_url")
        if callback_url:
            send_webhook_notification.delay(job_id, callback_url, "failed")
        
        # Re-raise for Celery retry mechanism
        raise self.retry(exc=e, countdown=60, max_retries=3)
        
    finally:
        db.close()


@celery_app.task(name="cleanup_job_task")
def cleanup_job_task(job_id: str):
    """
    Clean up job files to save storage space.
    
    Args:
        job_id: Job identifier
    """
    try:
        db = SessionLocal()
        image_service = ImageService(db)
        
        # Clean up input files but keep outputs for download
        image_service.cleanup_job_files(job_id, keep_outputs=True)
        
        logger.info(f"Cleaned up files for job {job_id}")
        
    except Exception as e:
        logger.error(f"Error cleaning up job {job_id}: {str(e)}")
    finally:
        db.close()


@celery_app.task(name="send_webhook_notification")
def send_webhook_notification(job_id: str, callback_url: str, status: str):
    """
    Send webhook notification for job completion.
    
    Args:
        job_id: Job identifier
        callback_url: Webhook URL
        status: Job status
    """
    try:
        import httpx
        
        payload = {
            "job_id": job_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with httpx.Client(timeout=30) as client:
            response = client.post(callback_url, json=payload)
            response.raise_for_status()
        
        logger.info(f"Webhook notification sent for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to send webhook for job {job_id}: {str(e)}")


def cleanup_old_job_files():
    """Clean up old job files (called by periodic task)."""
    try:
        storage_path = Path(settings.storage_path) / "jobs"
        cutoff_date = datetime.now() - timedelta(days=7)  # Keep files for 7 days
        
        for job_dir in storage_path.iterdir():
            if job_dir.is_dir():
                # Check directory modification time
                dir_mtime = datetime.fromtimestamp(job_dir.stat().st_mtime)
                if dir_mtime < cutoff_date:
                    import shutil
                    shutil.rmtree(job_dir)
                    logger.info(f"Cleaned up old job directory: {job_dir.name}")
        
    except Exception as e:
        logger.error(f"Error cleaning up old job files: {str(e)}")
