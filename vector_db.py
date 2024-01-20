import chromadb
from chromadb.config import Settings
import itertools, re
from fastapi import FastAPI, UploadFile
import PyPDF2
from epub2txt import epub2txt
from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract

chroma_client = chromadb.PersistentClient(
        settings=Settings(anonymized_telemetry=False),
        path='/tmp/chroma_data')
chroma_collection = chroma_client.get_or_create_collection("alldocs")

def group_consecutive(ids: list, docs: list):
    result = []
    sublist_texts = []
    sublist_ids = []
    for i, id in enumerate([int(id) for id in ids]):
        if not sublist_ids or id - sublist_ids[-1] == 1:
            sublist_texts.append(docs[i])
            sublist_ids.append(id)
        else:
            result.append('.'.join(sublist_texts))
            sublist_texts = [docs[i]]
            sublist_ids = [id]
    result.append('.'.join(sublist_texts))
    return result

def clean_name(name: str):
    pat = re.compile('[^a-zA-Z0-9_-]')
    name = re.sub(pat, '', name)
    if not name:
        raise Exception('bad name')
    if len(name) < 3:
        name += 'aaa'
    if re.match(r'^\d', name):
        name = 'a'+name
    if len(name) > 62:
        name = name[:62]
    if re.match(r'\d', name[-1]):
        name = name+'a'
    return name

def ocr(file):
    txt = ''
    file.seek(0)
    b = file.read()
    pages = convert_from_bytes(b)
    for page in pages:
        txt += str(pytesseract.image_to_string(page).encode("utf-8"))
    print('pdf len from OCR:',len(txt))
    return txt

def file_to_text(file: UploadFile) -> str:
    if '.pdf' in file.filename:
        txt = ''
        try:
            print('Trying text extraction wth PyPDF2')
            pdf = PyPDF2.PdfReader(file.file)
            for page in pdf.pages:
                txt += page.extract_text()
            if len(txt) < 1000:
                print(f'Not enough text found: {len(txt)} bytes. Trying OCR next')
                return ocr(file.file)
            return txt
        except Exception as e:
            print('Exception in PyPDF2, trying ocr next:',e)
            return ocr(file.file)
    if '.epub' in file.filename:
        print('Trying text extraction wth epub2txt')
        with open('/tmp/chroma_data/.tempepub','wb') as f:
            f.write(file.file.read())
        return epub2txt('/tmp/chroma_data/.tempepub')
    else:
        print('Trying to read text file')
        return file.file.read().decode('utf-8')

def deletedoc(name: str):
    """Delete indexed document"""
    global chroma_collection
    try:
        cname = clean_name(name)
        chroma_client.delete_collection(cname)
        chroma_collection = chroma_client.get_or_create_collection("alldocs")
        return {'message': f'Deleted index {cname}'}
    except Exception as e:
        print(e)
        return {'error': str(e)}

def listdocs():
    """List indexed documents"""
    lst = chroma_client.list_collections()
    return [doc.name for doc in lst]

def changedoc(name: str):
    """Select document for subsequent searches"""
    global chroma_collection
    try:
        cname = clean_name(name)
        chroma_collection = chroma_client.get_collection(cname)
        return {'message': f'Using index {cname}'}
    except Exception as e:
        print(e)
        return {'error': str(e)}

def index(file: UploadFile):
    """Index a text file with chromadb"""
    global chroma_collection
    cname = clean_name(file.filename)
    try:
        chroma_collection = chroma_client.create_collection(cname)
    except Exception as e:
        print(e)
        chroma_collection = chroma_client.get_collection(cname)
        return {'message': 'Already indexed'}
    try:
        txt = file_to_text(file)
        data = [sentence for sentence in txt.split('.') if len(sentence) > 8]
        ids=[str(i) for i, _ in enumerate(data)]
        chroma_collection.upsert(documents=data, ids=ids)
        return {'message': 'Document indexed'}
    except Exception as e:
        chroma_client.delete_collection(cname)
        return {'error':str(e)}

def search(query: str):
    """Return relavant texts from chromadb"""
    query_texts=[q for q in query.split('.') if q]
    results = chroma_collection.query(query_texts=query_texts, n_results=100, include=[])
    morenums = []
    for ids in results.get('ids'):
        tuples = [(n-1,n,n+1,n+2,n+3) for n in (int(id) for id in ids)]
        morenums += [i for i in itertools.chain(*tuples) if i >= 0]
    morenums = list(set(morenums))
    morenums.sort()
    morenums = [str(i) for i in morenums]
    moretext = chroma_collection.get(ids=morenums, include=['documents'])
    ids = moretext.get('ids')
    docs = moretext.get('documents')
    groups = group_consecutive(ids, docs)
    return {'result': groups}

# for testing vector database endpoints by themselves
if __name__ == '__main__':
    import uvicorn
    app = FastAPI()

    @app.post("/v1/chroma/index")
    async def index_(file: UploadFile):
        return index(file)

    @app.get("/v1/chroma/search")
    async def search_(query: str):
        return search(query)

    @app.get("/v1/chroma/list")
    async def listdocs_():
        return listdocs()

    @app.get("/v1/chroma/change")
    async def changedoc_(name: str):
        return changedoc(name)

    @app.get("/v1/chroma/delete")
    async def delete_(name: str):
        return deletedoc(name)


    uvicorn.run(
        app,
        host='0.0.0.0',
        port=6000,
        log_level="debug",
    )
