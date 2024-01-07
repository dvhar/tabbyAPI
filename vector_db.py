import chromadb
from chromadb.config import Settings
import itertools
from fastapi import FastAPI, UploadFile

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

def index(file: UploadFile):
    """Index a text file with chromadb"""
    global chroma_collection
    try:
        chroma_collection = chroma_client.create_collection(file.filename)
    except:
        chroma_collection = chroma_client.get_collection(file.filename)
        return {'message': 'Already indexed'}
    data = [sentence for sentence in file.file.read().decode('utf-8').split('.')]
    ids=[str(i) for i, _ in enumerate(data)]
    chroma_collection.upsert(documents=data, ids=ids)
    return {'message': 'Document indexed'}

def search(query: str):
    """Return relavant texts from chromadb"""
    query_texts=[q for q in query.split('.') if q]
    results = chroma_collection.query(query_texts=query_texts, n_results=100, include=[])
    morenums = []
    for ids in results.get('ids'):
        tuples = [(n-3,n-2,n-1,n,n+1,n+2,n+3) for n in (int(id) for id in ids)]
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

    uvicorn.run(
        app,
        host='0.0.0.0',
        port=6000,
        log_level="debug",
    )
