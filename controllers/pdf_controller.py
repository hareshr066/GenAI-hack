import os
import fitz  # PyMuPDF for reading PDFs
from datetime import datetime
from controllers import summarizer
from controllers import db

UPLOAD_FOLDER = "uploaded_pdfs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extract_text_from_pdf(file_path: str) -> str:
    """Extracts all text from a PDF file."""
    text = ""
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text += page.get_text()
    return text.strip()

def save_pdf(file):
    """Save uploaded PDF and store extracted text in DB."""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)

        # Save file to disk
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        # Extract text from PDF
        text = extract_text_from_pdf(file_path)
        if not text:
            return {"error": "Could not extract text from PDF. Please check the file."}

        # Store in database
        db.files_collection.insert_one({
            "filename": file.filename,
            "filepath": file_path,
            "text": text,
            "uploaded_at": datetime.utcnow()
        })

        return {"message": f"PDF '{file.filename}' uploaded successfully.", "filename": file.filename}

    except Exception as e:
        return {"error": str(e)}

def get_files():
    """List uploaded files."""
    try:
        files = list(db.files_collection.find({}, {"_id": 0}))
        return {"files": files}
    except Exception as e:
        return {"error": str(e)}

def summarize_latest_pdf():
    """Summarize the most recently uploaded PDF."""
    try:
        latest_file = db.files_collection.find_one(sort=[("uploaded_at", -1)])
        if not latest_file:
            return {"error": "No PDF found. Please upload a PDF first."}

        summary = summarizer.summarize_text(latest_file["text"])
        return {"summary": summary, "filename": latest_file["filename"]}

    except Exception as e:
        return {"error": str(e)}

def reset_files():
    """Delete all stored PDFs and DB entries."""
    try:
        db.files_collection.delete_many({})
        for f in os.listdir(UPLOAD_FOLDER):
            os.remove(os.path.join(UPLOAD_FOLDER, f))
        return {"message": "All uploaded files and database entries have been reset."}
    except Exception as e:
        return {"error": str(e)}
