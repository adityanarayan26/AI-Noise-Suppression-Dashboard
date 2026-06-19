import os
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

load_dotenv()

# Initialize Cloudinary if credentials are provided
if os.getenv("CLOUDINARY_CLOUD_NAME"):
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )

class CloudinaryService:
    @staticmethod
    def upload_audio(file_bytes: bytes, folder: str = "beforeNoiseSuppression", filename: str = None) -> str:
        """Uploads audio to Cloudinary in the specified folder."""
        try:
            response = cloudinary.uploader.upload(
                file_bytes, 
                resource_type="video", # Audio is uploaded as video in Cloudinary
                folder=folder,
                public_id=filename,
                overwrite=True
            )
            return response.get("secure_url")
        except Exception as e:
            print(f"Cloudinary upload error: {e}")
            raise Exception("Failed to upload audio to Cloudinary")

    @staticmethod
    def get_audio_files(folder: str) -> list:
        """Gets a list of audio files from a specific folder."""
        try:
            # We use api.resources with prefix to find files in folder
            # Note: in a real production scenario with many files, use search API
            response = cloudinary.api.resources(
                type="upload",
                resource_type="video", 
                prefix=f"{folder}/",
                max_results=50
            )
            
            files = []
            for item in response.get("resources", []):
                files.append({
                    "id": item.get("public_id"),
                    "url": item.get("secure_url"),
                    "created_at": item.get("created_at"),
                    "format": item.get("format")
                })
            return files
        except Exception as e:
            print(f"Cloudinary fetch error: {e}")
            return []
