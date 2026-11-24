
import hashlib
from pathlib import Path
from uuid import uuid4

import pymupdf
from fastapi import UploadFile

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCUMENT_STORAGE = PROJECT_ROOT / "storage" / "documents"

MAX_FILE_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

async def save_pdf(upload: UploadFile) -> dict:
    original_filename = Path(upload.filename or "").name

    if not original_filename:
        raise ValueError("A filename is required.")

    if Path(original_filename).suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are allowed.")

    DOCUMENT_STORAGE.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4().hex}.pdf"
    final_path = DOCUMENT_STORAGE / stored_filename
    temporary_path = DOCUMENT_STORAGE / f"{uuid4().hex}.upload"

    file_hash = hashlib.sha256()
    file_size = 0
    first_chunk = True

    try:
        with temporary_path.open("wb") as destination:
            while True:
                chunk = await upload.read(CHUNK_SIZE)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise ValueError("PDF exceeds the 20 MB upload limit.")

                if first_chunk:
                    if not chunk.startswith(b"%PDF-"):
                        raise ValueError("The uploaded file is not a valid PDF.")
                    first_chunk = False

                file_hash.update(chunk)
                destination.write(chunk)

        if file_size == 0:
            raise ValueError("The uploaded PDF is empty.")

        with pymupdf.open(temporary_path) as pdf:
            if pdf.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")

            page_count = pdf.page_count

            if page_count == 0:
                raise ValueError("The PDF contains no pages.")

        temporary_path.replace(final_path)

        return {
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "storage_path": str(final_path),
            "sha256": file_hash.hexdigest(),
            "file_size": file_size,
            "page_count": page_count,
        }

    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise

    finally:
        await upload.close()