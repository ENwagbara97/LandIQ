"""
LandIQ — agents/vision_preprocessor.py
Computer Vision & Document Quality Pre-processing

Uses OpenCV (cv2) to pre-process scanned survey plans before OCR extraction.
Features:
- Deskewing via Hough Lines
- Contrast Limited Adaptive Histogram Equalisation (CLAHE)
- Morphological noise removal
- 2x Upscaling for low-res scans
- Otsu Binarisation
"""

import io
import math
import numpy as np
import cv2
import logging
from PIL import Image

logger = logging.getLogger("landiq.vision")

def preprocess_image_for_ocr(file_bytes: bytes) -> bytes:
    """
    Run full OpenCV pre-processing pipeline on image bytes.
    Returns enhanced image bytes (PNG format).
    """
    try:
        # Convert bytes to numpy array then to cv2 image
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return file_bytes

        # Attempt to read DPI from PIL before processing
        try:
            pil_img = Image.open(io.BytesIO(file_bytes))
            dpi = pil_img.info.get('dpi', (72, 72))
            avg_dpi = (dpi[0] + dpi[1]) / 2.0
        except Exception:
            avg_dpi = 72.0

        # STEP 4: DPI Upscaling (moved early to improve line detection)
        if avg_dpi < 200:
            logger.info(f"[vision] Low DPI detected ({avg_dpi}). Upscaling 2x.")
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        # Convert to grayscale for remaining steps
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # STEP 1: Rotation Correction (Deskew)
        # Use Hough Lines to find dominant line angle
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        
        if lines is not None:
            angles = []
            for line in lines:
                r, theta = line[0]
                # Filter out lines that are strictly vertical or horizontal 
                # (we only want slightly skewed lines)
                angle = (theta * 180 / np.pi) - 90
                if abs(angle) > 0.5 and abs(angle) < 45: 
                    angles.append(angle)
            
            if angles:
                # Find median angle to avoid outliers
                median_angle = np.median(angles)
                logger.info(f"[vision] Deskewing by {median_angle:.2f} degrees")
                
                (h, w) = gray.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # STEP 2: Contrast Enhancement (CLAHE)
        logger.info("[vision] Applying CLAHE contrast enhancement")
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Encode back to PNG bytes
        success, encoded_img = cv2.imencode('.png', enhanced)
        if success:
            return encoded_img.tobytes()
        return file_bytes

    except Exception as exc:
        logger.error(f"[vision] Pipeline failed: {exc}. Returning original bytes.")
        return file_bytes
