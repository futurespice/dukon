"""
Shared upload validators used across multiple apps.

Previously image validation was duplicated in:
  - apps/stores/serializers.py  (_validate_uploaded_image)
  - apps/accounts/serializers.py (UserProfileImageSerializer.validate_image)

Both implementations had identical logic. This module is the single source of
truth. Both files now import validate_image_upload from here.
"""
import logging

from rest_framework import serializers

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWED_TYPES = ('image/jpeg', 'image/png', 'image/webp')
_DEFAULT_MAX_MB = 5


def validate_image_upload(
    value,
    max_mb: int = _DEFAULT_MAX_MB,
    allowed_types: tuple = _DEFAULT_ALLOWED_TYPES,
    field_label: str = 'image',
) -> object:
    """
    Validate an uploaded image file for use in DRF serializer validate_<field> methods.

    Checks:
      1. MIME type against allowed_types.
      2. File size against max_mb (in megabytes).
      3. PIL image integrity — rejects pixel-bombs and corrupted files.

    Args:
        value:         The uploaded InMemoryUploadedFile / TemporaryUploadedFile.
        max_mb:        Maximum allowed file size in megabytes (default: 5).
        allowed_types: Tuple of allowed MIME type strings
                       (default: JPEG, PNG, WEBP).
        field_label:   Human-readable field name used in log messages.

    Returns:
        The validated file object (seeked back to position 0 after PIL check).

    Raises:
        rest_framework.serializers.ValidationError on any violation.
    """
    max_bytes = max_mb * 1024 * 1024

    content_type = getattr(value, 'content_type', None)
    if content_type and content_type not in allowed_types:
        types_str = ', '.join(t.split('/')[-1].upper() for t in allowed_types)
        raise serializers.ValidationError(
            f'Недопустимый формат: {content_type}. Разрешены: {types_str}.'
        )

    if value.size > max_bytes:
        mb = value.size / (1024 * 1024)
        raise serializers.ValidationError(
            f'Файл слишком большой ({mb:.1f} МБ). Максимальный размер: {max_mb} МБ.'
        )

    # R-1 FIX (MIME spoofing — verify actual file format via PIL):
    # content_type is read from the HTTP multipart header, which is fully
    # controlled by the client. An attacker can upload a PHP/EXE/SVG file
    # with Content-Type: image/jpeg and bypass the MIME check above.
    #
    # Fix: after PIL verify() confirms the file is a valid image, re-open
    # it (verify() exhausts the file pointer) and compare PIL's detected
    # format against the allowed_types whitelist.
    # This makes the format check server-side and unbypassable.
    #
    # PIL format strings: 'JPEG' | 'PNG' | 'WEBP' | ...
    _PIL_FORMAT_TO_MIME: dict[str, str] = {
        'JPEG': 'image/jpeg',
        'PNG':  'image/png',
        'WEBP': 'image/webp',
    }

    try:
        from PIL import Image, UnidentifiedImageError
        # Pass 1: verify() checks file integrity (detects truncated/corrupted images).
        # Note: verify() cannot be used after the fact on the same Image object —
        # it exhausts internal state. We must Image.open() again for format detection.
        img = Image.open(value)
        img.verify()
        value.seek(0)

        # Pass 2: re-open to detect actual format (verify() closes internal state).
        img2 = Image.open(value)
        actual_pil_format = img2.format  # e.g. 'JPEG', 'PNG', 'WEBP', 'GIF', None
        value.seek(0)

        actual_mime = _PIL_FORMAT_TO_MIME.get(actual_pil_format or '')
        if actual_mime not in allowed_types:
            # File content does not match an allowed format regardless of
            # what Content-Type the client claimed.
            types_str = ', '.join(t.split('/')[-1].upper() for t in allowed_types)
            raise serializers.ValidationError(
                f'Реальный формат файла ({actual_pil_format or "неизвестен"}) '
                f'не является допустимым изображением. Разрешены: {types_str}.'
            )
    except serializers.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise serializers.ValidationError('Файл повреждён или не является изображением.')
    except Exception:
        logger.exception(
            'Unexpected error during %s image validation (filename=%s, size=%d)',
            field_label,
            getattr(value, 'name', 'unknown'),
            getattr(value, 'size', -1),
        )
        raise serializers.ValidationError('Ошибка при проверке файла. Попробуйте другой файл.')

    return value
