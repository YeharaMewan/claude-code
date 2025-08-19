"""
Document ingestion system for PostgreSQL + pgvector
Handles PDF chunking, embedding generation, and storage
"""
import os
import uuid
import json
import logging
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
import PyPDF2
from langchain.text_splitter import RecursiveCharacterTextSplitter
import io
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

class DocumentIngester:
    """Handles document ingestion with embeddings"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://hruser:hrpass@localhost:5432/hrdb')
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
        self.chunk_size = int(os.getenv('CHUNK_SIZE', '1000'))
        self.chunk_overlap = int(os.getenv('CHUNK_OVERLAP', '100'))
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        )
    
    def get_connection(self):
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes"""
        try:
            pdf_file = io.BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return text.strip()
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        try:
            response = openai_client.embeddings.create(
                input=texts,
                model=self.embedding_model
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def chunk_document(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split document into chunks with metadata"""
        chunks = self.text_splitter.split_text(text)
        
        chunk_docs = []
        for i, chunk in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                'chunk_index': i,
                'total_chunks': len(chunks)
            }
            
            chunk_docs.append({
                'chunk_id': f"{metadata.get('document_id', str(uuid.uuid4()))}_{i}",
                'content': chunk,
                'metadata': chunk_metadata
            })
        
        return chunk_docs
    
    def store_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Store chunks and embeddings in database"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                for chunk, embedding in zip(chunks, embeddings):
                    cur.execute("""
                        INSERT INTO documents (chunk_id, content, metadata, embedding)
                        VALUES (%s, %s, %s, %s::vector)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding,
                            created_at = NOW(),
                            deleted_at = NULL
                    """, (
                        chunk['chunk_id'],
                        chunk['content'],
                        json.dumps(chunk['metadata']),
                        embedding
                    ))
                
                conn.commit()
                logger.info(f"Stored {len(chunks)} chunks successfully")
                
        except Exception as e:
            logger.error(f"Failed to store chunks: {e}")
            raise
    
    async def ingest_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest a single document"""
        try:
            doc_id = document.get('id', str(uuid.uuid4()))
            filename = document.get('filename', 'unknown')
            content_type = document.get('content_type', 'text/plain')
            
            # Extract text based on content type
            if content_type == 'application/pdf':
                if 'content' in document:
                    # If content is base64 encoded bytes
                    import base64
                    pdf_content = base64.b64decode(document['content'])
                    text = self.extract_text_from_pdf(pdf_content)
                elif 'file_path' in document:
                    # If file path is provided
                    with open(document['file_path'], 'rb') as f:
                        text = self.extract_text_from_pdf(f.read())
                else:
                    raise ValueError("PDF document must have 'content' or 'file_path'")
            else:
                # Plain text or other formats
                text = document.get('content', document.get('text', ''))
            
            if not text.strip():
                raise ValueError("Document contains no extractable text")
            
            # Create document metadata
            metadata = {
                'document_id': doc_id,
                'filename': filename,
                'content_type': content_type,
                'ingested_at': str(datetime.now()),
                **document.get('metadata', {})
            }
            
            # Chunk the document
            chunks = self.chunk_document(text, metadata)
            
            # Generate embeddings for all chunks
            chunk_texts = [chunk['content'] for chunk in chunks]
            embeddings = self.generate_embeddings(chunk_texts)
            
            # Store in database
            self.store_chunks(chunks, embeddings)
            
            return {
                'document_id': doc_id,
                'filename': filename,
                'chunks_created': len(chunks),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Document ingestion failed: {e}")
            return {
                'document_id': document.get('id', 'unknown'),
                'filename': document.get('filename', 'unknown'),
                'chunks_created': 0,
                'status': 'error',
                'error': str(e)
            }
    
    async def ingest_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingest multiple documents"""
        results = []
        total_chunks = 0
        success_count = 0
        
        for doc in documents:
            result = await self.ingest_document(doc)
            results.append(result)
            
            if result['status'] == 'success':
                success_count += 1
                total_chunks += result['chunks_created']
        
        return {
            'total_documents': len(documents),
            'successful': success_count,
            'failed': len(documents) - success_count,
            'total_chunks_created': total_chunks,
            'results': results
        }
    
    def search_documents(self, query: str, limit: int = 5, min_similarity: float = 0.7) -> List[Dict[str, Any]]:
        """Search documents using vector similarity"""
        try:
            # Generate embedding for query
            query_embeddings = self.generate_embeddings([query])
            query_embedding = query_embeddings[0]
            
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT 
                        content, 
                        metadata, 
                        (1 - (embedding <=> %s::vector)) as similarity
                    FROM documents 
                    WHERE deleted_at IS NULL
                        AND (1 - (embedding <=> %s::vector)) >= %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_embedding, query_embedding, min_similarity, query_embedding, limit))
                
                results = cur.fetchall()
                
                return [
                    {
                        'content': r['content'],
                        'metadata': r['metadata'],
                        'similarity': float(r['similarity'])
                    }
                    for r in results
                ]
                
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
    
    def delete_document(self, document_id: str) -> bool:
        """Soft delete all chunks of a document"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    UPDATE documents 
                    SET deleted_at = NOW() 
                    WHERE metadata->>'document_id' = %s AND deleted_at IS NULL
                """, (document_id,))
                
                affected = cur.rowcount
                conn.commit()
                
                logger.info(f"Soft deleted {affected} chunks for document {document_id}")
                return affected > 0
                
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    def restore_document(self, document_id: str) -> bool:
        """Restore a soft-deleted document"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    UPDATE documents 
                    SET deleted_at = NULL 
                    WHERE metadata->>'document_id' = %s AND deleted_at IS NOT NULL
                """, (document_id,))
                
                affected = cur.rowcount
                conn.commit()
                
                logger.info(f"Restored {affected} chunks for document {document_id}")
                return affected > 0
                
        except Exception as e:
            logger.error(f"Failed to restore document {document_id}: {e}")
            return False
    
    def get_document_stats(self) -> Dict[str, Any]:
        """Get statistics about stored documents"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                
                # Active documents
                cur.execute("""
                    SELECT COUNT(DISTINCT metadata->>'document_id') as document_count,
                           COUNT(*) as chunk_count
                    FROM documents 
                    WHERE deleted_at IS NULL
                """)
                active_stats = dict(cur.fetchone())
                
                # Deleted documents
                cur.execute("""
                    SELECT COUNT(DISTINCT metadata->>'document_id') as deleted_document_count,
                           COUNT(*) as deleted_chunk_count
                    FROM documents 
                    WHERE deleted_at IS NOT NULL
                """)
                deleted_stats = dict(cur.fetchone())
                
                return {
                    'active_documents': active_stats['document_count'],
                    'active_chunks': active_stats['chunk_count'],
                    'deleted_documents': deleted_stats['deleted_document_count'],
                    'deleted_chunks': deleted_stats['deleted_chunk_count']
                }
                
        except Exception as e:
            logger.error(f"Failed to get document stats: {e}")
            return {}

# Global ingester instance
ingester = DocumentIngester()

# Convenience functions for MCP server
async def ingest_documents(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ingest documents - wrapper for MCP server"""
    return await ingester.ingest_documents(documents)

async def search_documents(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search documents - wrapper for MCP server"""
    return ingester.search_documents(query, limit)

if __name__ == "__main__":
    # Test the ingestion system
    import asyncio
    from datetime import datetime
    
    async def test_ingestion():
        # Test with a sample document
        test_doc = {
            'id': 'test-doc-1',
            'filename': 'test-document.txt',
            'content_type': 'text/plain',
            'content': 'This is a test document for the HR system. It contains information about employee policies and procedures.',
            'metadata': {
                'department': 'HR',
                'category': 'policy'
            }
        }
        
        result = await ingester.ingest_document(test_doc)
        print(f"Ingestion result: {result}")
        
        # Test search
        search_results = ingester.search_documents("employee policies", limit=3)
        print(f"Search results: {search_results}")
    
    asyncio.run(test_ingestion())