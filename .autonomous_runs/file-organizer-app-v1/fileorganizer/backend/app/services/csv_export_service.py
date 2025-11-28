"""
CSV Export Service - Generate organized document pack as CSV
"""
import csv
from pathlib import Path
from datetime import datetime
from app.models.document import Document
from app.models.category import Category
from typing import List


class CSVExportService:
    def export_pack(
        self,
        pack_name: str,
        documents: List[Document],
        categories: List[Category],
        output_path: Path
    ) -> Path:
        """
        Export documents as CSV file
        """
        category_map = {cat.id: cat.name for cat in categories}

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Header
            writer.writerow(['File Name', 'Category', 'Confidence (%)', 'Status', 'File Size (KB)', 'File Type'])

            # Data rows
            for doc in documents:
                category_name = category_map.get(doc.assigned_category_id, 'Uncategorized')
                confidence = f"{doc.classification_confidence:.0f}" if doc.classification_confidence else 'N/A'
                status = 'Approved' if doc.classification_confidence == 100 else 'Pending'
                file_size_kb = f"{doc.file_size / 1024:.2f}"

                writer.writerow([
                    doc.filename,
                    category_name,
                    confidence,
                    status,
                    file_size_kb,
                    doc.file_type
                ])

        return output_path
