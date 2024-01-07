import chromadb
from chromadb.config import Settings
import itertools
from fastapi import UploadFile

chroma_client = chromadb.Client(Settings(anonymized_telemetry=False))
chroma_collection = chroma_client.get_or_create_collection("alldocs")

def group_consecutive(ids: list, docs: list):
    result = []
    sublist = []
    sublistids = []
    for i, id in enumerate([int(id) for id in ids]):
        if not sublistids or id - sublistids[-1] == 1:
            sublist.append(docs[i])
            sublistids.append(id)
        else:
            result.append('.'.join(sublist))
            sublist = [docs[i]]
            sublistids = [id]
    result.append('.'.join(sublist))
    return result

def index(file: UploadFile):
    """Index a text file with chromadb"""
    global chroma_collection
    chroma_collection = chroma_client.get_or_create_collection(file.filename)
    data = [sentence for sentence in file.file.read().decode('utf-8').split('.')]
    ids=[str(i) for i, _ in enumerate(data)]
    chroma_collection.upsert(documents=data, ids=ids)
    return {'message': 'Document indexed.'}

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
