"""
PDF Export Service - Generate organized document pack as PDF
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.category import Category
from typing import List


class PDFExportService:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1F2937'),
            spaceAfter=30,
        )
        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#374151'),
            spaceAfter=12,
        )

    def export_pack(
        self,
        pack_name: str,
        documents: List[Document],
        categories: List[Category],
        output_path: Path
    ) -> Path:
        """
        Export documents as organized PDF
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )

        # Build content
        story = []

        # Title page
        story.append(Paragraph(pack_name, self.title_style))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            self.styles['Normal']
        ))
        story.append(Spacer(1, 0.5*inch))

        # Summary statistics
        story.append(Paragraph("Summary", self.heading_style))
        summary_data = [
            ['Total Documents:', str(len(documents))],
            ['Categories:', str(len(categories))],
            ['Approved Documents:', str(len([d for d in documents if d.classification_confidence == 100]))],
        ]
        summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(summary_table)
        story.append(PageBreak())

        # Group documents by category
        category_docs = {}
        for cat in categories:
            category_docs[cat.id] = {
                'name': cat.name,
                'description': cat.description,
                'documents': []
            }

        for doc in documents:
            if doc.assigned_category_id and doc.assigned_category_id in category_docs:
                category_docs[doc.assigned_category_id]['documents'].append(doc)

        # Generate sections for each category
        for cat_id, cat_data in category_docs.items():
            if not cat_data['documents']:
                continue

            # Category heading
            story.append(Paragraph(cat_data['name'], self.heading_style))
            if cat_data['description']:
                story.append(Paragraph(cat_data['description'], self.styles['Normal']))
            story.append(Spacer(1, 0.2*inch))

            # Documents table
            table_data = [['File Name', 'Confidence', 'Status']]
            for doc in cat_data['documents']:
                confidence = f"{doc.classification_confidence:.0f}%" if doc.classification_confidence else 'N/A'
                status = '[x] Approved' if doc.classification_confidence == 100 else 'Pending'
                table_data.append([doc.filename, confidence, status])

            doc_table = Table(table_data, colWidths=[3.5*inch, 1*inch, 1.5*inch])
            doc_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(doc_table)
            story.append(Spacer(1, 0.3*inch))

        # Build PDF
        doc.build(story)
        return output_path
