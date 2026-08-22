import os
import posixpath
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
import cloudinary
import cloudinary.uploader
import cloudinary.utils


@deconstructible
class CloudinaryMediaStorage(Storage):
    """
    Custom Django Storage backend that uploads media files directly to Cloudinary
    and returns secure Cloudinary CDN URLs.
    """

    def __init__(self, **kwargs):
        cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
        api_key = os.getenv('CLOUDINARY_API_KEY')
        api_secret = os.getenv('CLOUDINARY_API_SECRET')

        if cloud_name and api_key and api_secret:
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True
            )

    def _open(self, name, mode='rb'):
        raise NotImplementedError("CloudinaryMediaStorage does not support local file opening.")

    def _save(self, name, content):
        # Normalize name and split folder/filename
        name = name.replace('\\', '/')
        folder, filename = posixpath.split(name)
        base_name, _ = posixpath.splitext(filename)

        # Upload to Cloudinary
        content.seek(0)
        upload_params = {
            'resource_type': 'auto',
            'unique_filename': True,
            'overwrite': False,
        }
        if folder:
            upload_params['folder'] = folder
        if base_name:
            upload_params['public_id'] = base_name

        result = cloudinary.uploader.upload(content, **upload_params)
        # Return the secure HTTPS URL
        return result.get('secure_url', result.get('url', name))

    def url(self, name):
        if not name:
            return ''
        if name.startswith('http://') or name.startswith('https://'):
            return name
        # If stored as a relative public_id or path
        return cloudinary.utils.cloudinary_url(name, secure=True)[0]

    def exists(self, name):
        # Cloudinary handles uniqueness with unique_filename
        return False

    def get_available_name(self, name, max_length=None):
        return name

    def delete(self, name):
        if not name:
            return
        try:
            if 'res.cloudinary.com' in name:
                parts = name.split('/upload/')
                if len(parts) > 1:
                    path_after_upload = parts[1]
                    if path_after_upload.startswith('v') and '/' in path_after_upload:
                        path_after_upload = path_after_upload.split('/', 1)[1]
                    public_id, _ = posixpath.splitext(path_after_upload)
                    cloudinary.uploader.destroy(public_id)
            else:
                public_id, _ = posixpath.splitext(name)
                cloudinary.uploader.destroy(public_id)
        except Exception:
            pass

    def size(self, name):
        return 0
