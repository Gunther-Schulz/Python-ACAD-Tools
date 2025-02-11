import cv2
from PIL import Image

def patched_compute_ratio_and_resize(img, width, height, model_height):
    ratio = model_height / height
    target_width = int(width * ratio)
    processed = cv2.resize(img, (target_width, model_height), interpolation=cv2.INTER_AREA)
    return processed, ratio

# Monkey patch the EasyOCR function
import easyocr.utils
easyocr.utils.compute_ratio_and_resize = patched_compute_ratio_and_resize