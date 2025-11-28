"""
Custom exceptions for FileOrganizer
"""


class FileOrganizerException(Exception):
    """Base exception for FileOrganizer"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class DocumentNotFoundException(FileOrganizerException):
    """Document not found"""
    def __init__(self, document_id: int):
        super().__init__(
            f"Document with ID {document_id} not found",
            status_code=404
        )


class PackNotFoundException(FileOrganizerException):
    """Pack not found"""
    def __init__(self, pack_id: int):
        super().__init__(
            f"Pack with ID {pack_id} not found",
            status_code=404
        )


class InvalidFileException(FileOrganizerException):
    """Invalid file upload"""
    def __init__(self, reason: str):
        super().__init__(
            f"Invalid file: {reason}",
            status_code=400
        )


class OCRException(FileOrganizerException):
    """OCR processing failed"""
    def __init__(self, reason: str):
        super().__init__(
            f"OCR failed: {reason}",
            status_code=500
        )


class ClassificationException(FileOrganizerException):
    """Classification failed"""
    def __init__(self, reason: str):
        super().__init__(
            f"Classification failed: {reason}",
            status_code=500
        )


class ExportException(FileOrganizerException):
    """Export failed"""
    def __init__(self, reason: str):
        super().__init__(
            f"Export failed: {reason}",
            status_code=500
        )
