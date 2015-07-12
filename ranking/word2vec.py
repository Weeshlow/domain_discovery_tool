from pickle import load
import numpy as np
from os import environ
from pprint import pprint

from elastic.get_mtermvectors import getTermFrequency

class word2vec:
    def __init__(self, opt_docs = None, es_index = 'memex', es_doc_type = 'page', es = None):
        self.documents = opt_docs
        self.word2vec = None

        f = open(environ['DDT_HOME']+'/ranking/D_cbow_pdw_8B.pkl', 'rb')
        self.word_vec = load(f)

        if opt_docs != None:
            self.process(opt_docs, es_index, es_doc_type, es)

    def get_word2vec(self):
        return [self.documents,self.word2vec]

    def get(self, word):
        return self.word_vec.get(word)
        
    def process(self, documents, es_index = 'memex', es_doc_type = 'page', es = None):

        [data_tf, corpus, urls] = getTermFrequency(documents, self.word_vec, es_index, es_doc_type, es)
        
        documents = urls

        word2vec_list_docs = []
        urls = []
        i = 0
        for doc in data_tf:
            word_vec_doc = [self.word_vec[term] for term in doc.keys() if doc[term] > 5 and not self.word_vec.get(term) is None]
            if word_vec_doc:
                m_word_vec = np.array(word_vec_doc).mean(axis=0) 
                word2vec_list_docs.append(m_word_vec.tolist())
                urls.append(documents[i])
                i = i + 1
        
        self.documents = urls
        
        self.word2vec = np.array(word2vec_list_docs)
        return [self.documents,self.word2vec]
        
