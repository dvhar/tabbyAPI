import chromadb
from chromadb.config import Settings
import itertools, re
from fastapi import FastAPI, UploadFile
import PyPDF2
from epub2txt import epub2txt

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

def file_to_text(file: UploadFile):
    if '.pdf' in file.filename:
        txt = ''
        pdf = PyPDF2.PdfReader(file.file)
        for page in pdf.pages:
            txt += page.extract_text()
        if len(txt) < 10:
            raise Exception('pdf not convertable to text, requires ocr')
        return txt
    if '.epub' in file.filename:
        with open('/tmp/chroma_data/.tempepub','wb') as f:
            f.write(file.file.read())
        return epub2txt('/tmp/chroma_data/.tempepub')
    else:
        return file.file.read().decode('utf-8')

def listdocs():
    """List indexed documents"""
    global chroma_collection
    lst = chroma_client.list_collections()
    return [doc.name for doc in lst]

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
        data = [sentence for sentence in txt.split('.')]
        ids=[str(i) for i, _ in enumerate(data)]
        chroma_collection.upsert(documents=data, ids=ids)
        return {'message': 'Document indexed'}
    except Exception as e:
        chroma_client.delete_collection(cname)
        return {'message': 'Error indexing', 'error':str(e)}

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


    uvicorn.run(
        app,
        host='0.0.0.0',
        port=6000,
        log_level="debug",
    )
