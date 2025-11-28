"""
Export API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.pdf_export_service import PDFExportService
from app.services.excel_export_service import ExcelExportService
from app.services.csv_export_service import CSVExportService
from app.services.pack_service import ScenarioPackService
from app.models.document import Document
from pathlib import Path
from datetime import datetime

router = APIRouter()


@router.get("/export/pdf/{pack_id}")
async def export_pdf(pack_id: int, db: Session = Depends(get_db)):
    """Export pack as PDF"""
    try:
        # Get pack
        pack_service = ScenarioPackService(db)
        pack = pack_service.get_pack(pack_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Pack not found")

        categories = pack_service.get_pack_categories(pack_id)

        # Get all documents
        documents = db.query(Document).filter(
            Document.assigned_category_id != None
        ).all()

        # Generate PDF
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{pack.name.replace(' ', '_')}_{timestamp}.pdf"
        output_path = exports_dir / output_filename

        pdf_service = PDFExportService()
        pdf_service.export_pack(pack.name, documents, categories, output_path)

        return FileResponse(
            path=str(output_path),
            filename=output_filename,
            media_type='application/pdf'
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/excel/{pack_id}")
async def export_excel(pack_id: int, db: Session = Depends(get_db)):
    """Export pack as Excel workbook"""
    try:
        # Get pack
        pack_service = ScenarioPackService(db)
        pack = pack_service.get_pack(pack_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Pack not found")

        categories = pack_service.get_pack_categories(pack_id)

        # Get all documents
        documents = db.query(Document).filter(
            Document.assigned_category_id != None
        ).all()

        # Generate Excel
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{pack.name.replace(' ', '_')}_{timestamp}.xlsx"
        output_path = exports_dir / output_filename

        excel_service = ExcelExportService()
        excel_service.export_pack(pack.name, documents, categories, output_path)

        return FileResponse(
            path=str(output_path),
            filename=output_filename,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/csv/{pack_id}")
async def export_csv(pack_id: int, db: Session = Depends(get_db)):
    """Export pack as CSV"""
    try:
        # Get pack
        pack_service = ScenarioPackService(db)
        pack = pack_service.get_pack(pack_id)
        if not pack:
            raise HTTPException(status_code=404, detail="Pack not found")

        categories = pack_service.get_pack_categories(pack_id)

        # Get all documents
        documents = db.query(Document).filter(
            Document.assigned_category_id != None
        ).all()

        # Generate CSV
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{pack.name.replace(' ', '_')}_{timestamp}.csv"
        output_path = exports_dir / output_filename

        csv_service = CSVExportService()
        csv_service.export_pack(pack.name, documents, categories, output_path)

        return FileResponse(
            path=str(output_path),
            filename=output_filename,
            media_type='text/csv'
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
