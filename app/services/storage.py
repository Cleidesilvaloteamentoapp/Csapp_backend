from typing import Optional, List
from supabase import Client
from fastapi import UploadFile, HTTPException, status
import uuid


class StorageService:
    """Service for Supabase Storage operations"""
    
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    BUCKETS = {
        "clients": "client-documents",
        "lots": "lot-documents",
        "developments": "development-documents",
        "services": "service-documents"
    }
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    def _validate_file(self, file: UploadFile) -> None:
        """Validate file extension and size"""
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required"
            )
        
        extension = file.filename.rsplit(".", 1)[-1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension not allowed. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )
    
    async def upload_file(
        self,
        file: UploadFile,
        bucket_type: str,
        folder_id: str
    ) -> str:
        """
        Upload file to Supabase Storage
        Returns the file path
        """
        self._validate_file(file)
        
        bucket = self.BUCKETS.get(bucket_type)
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket type: {bucket_type}"
            )
        
        extension = file.filename.rsplit(".", 1)[-1].lower()
        file_name = f"{uuid.uuid4()}.{extension}"
        file_path = f"{folder_id}/{file_name}"
        
        content = await file.read()
        
        if len(content) > self.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed ({self.MAX_FILE_SIZE // 1024 // 1024}MB)"
            )
        
        self.supabase.storage.from_(bucket).upload(
            path=file_path,
            file=content,
            file_options={"content-type": file.content_type}
        )
        
        return file_path
    
    def get_public_url(self, bucket_type: str, file_path: str) -> str:
        """Get public URL for a file"""
        bucket = self.BUCKETS.get(bucket_type)
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket type: {bucket_type}"
            )
        
        result = self.supabase.storage.from_(bucket).get_public_url(file_path)
        return result
    
    def get_signed_url(
        self,
        bucket_type: str,
        file_path: str,
        expires_in: int = 3600
    ) -> str:
        """Get signed URL for private file access"""
        bucket = self.BUCKETS.get(bucket_type)
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket type: {bucket_type}"
            )
        
        result = self.supabase.storage.from_(bucket).create_signed_url(
            path=file_path,
            expires_in=expires_in
        )
        return result.get("signedURL", "")
    
    def delete_file(self, bucket_type: str, file_path: str) -> bool:
        """Delete a file from storage"""
        bucket = self.BUCKETS.get(bucket_type)
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket type: {bucket_type}"
            )
        
        self.supabase.storage.from_(bucket).remove([file_path])
        return True
    
    def list_files(self, bucket_type: str, folder_id: str) -> List[dict]:
        """List files in a folder"""
        bucket = self.BUCKETS.get(bucket_type)
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket type: {bucket_type}"
            )
        
        result = self.supabase.storage.from_(bucket).list(path=folder_id)
        return result
