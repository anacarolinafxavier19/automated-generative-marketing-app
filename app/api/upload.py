import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import TokenTextSplitter

from app.dependencies import get_file_store, get_metadata_store, get_vector_store
from app.ingestion.pdf_parser import parse_pdf
from langchain_community.vectorstores.chroma import Chroma
from app.storage.file_store import FileStore
from app.storage.metadata_db import DocumentRecord, ImageAssetRecord, MetadataStore

router = APIRouter(prefix="/companies", tags=["ingestion"])

Role = Literal["sender", "receiver"]


@router.post("/{company_name}/documents")
async def upload_documents(
    company_name: str,
    role: Role,
    files: list[UploadFile],
    file_store: FileStore = Depends(get_file_store),
    metadata_store: MetadataStore = Depends(get_metadata_store),
    vector_store: Chroma = Depends(get_vector_store),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"'{upload.filename}' is not a PDF")

        content = await upload.read()
        pdf_path = file_store.save_pdf(company_name, role, str(uuid.uuid4()), upload.filename, content)

        # Use PyMuPDFLoader to load text content from the saved file
        loader = PyMuPDFLoader(pdf_path)
        documents = loader.load()

        # Use TokenTextSplitter for chunking
        text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_documents(documents)

        # Add metadata to each chunk for filtering during retrieval
        doc_id = str(uuid.uuid4())
        for chunk in chunks:
            chunk.metadata["company_name"] = company_name
            chunk.metadata["role"] = role
            chunk.metadata["document_id"] = doc_id

        vector_store.add_documents(chunks)

        # Your custom image/table parsing logic can remain to handle multi-modal data
        parsed = parse_pdf(content)

        image_count = 0
        for image in parsed.images:
            image_name = f"{image.index}_p{image.page_number}.{image.ext}"
            image_path = file_store.save_image(company_name, role, doc_id, image_name, image.content)
            metadata_store.add_image(
                ImageAssetRecord(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    company_name=company_name,
                    role=role,
                    file_path=image_path,
                    page_number=image.page_number,
                    is_logo=image.is_logo,
                )
            )
            image_count += 1

        metadata_store.add_document(
            DocumentRecord(
                id=doc_id,
                company_name=company_name,
                role=role,
                filename=upload.filename,
                file_path=pdf_path,
                chunk_count=len(chunks),
            )
        )

        results.append(
            {
                "document_id": doc_id,
                "filename": upload.filename,
                "chunk_count": len(chunks),
                "image_count": image_count,
            }
        )

    return {"company_name": company_name, "role": role, "documents": results}
