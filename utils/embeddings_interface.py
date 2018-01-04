"""
    Script does all the magic with word embeddings including lazy loading them in the RAM and all that.

    @TODO: Check how well is this performing
"""

import os
import json
import gensim
import cPickle as pickle
import bottle
import warnings
import numpy as np
from bottle import post, get, put, delete, request, response

word2vec_embeddings = None
word2vec_vocab = None
glove_embeddings = None
glove_vocab = None

DEFAULT_EMBEDDING = 'word2vec'
DEBUG = True
glove_location = \
    {
        'dir': "./resources",
        'raw': "glove.42B.300d.txt",
        'parsed': "glove_parsed.npy",
        'vocab': "glove_vocab.pickle"
    }


# Better warning formatting. Ignore.
def better_warning(message, category, filename, lineno, file=None, line=None):
    return ' %s:%s: %s:%s\n' % (filename, lineno, category.__name__, message)


def __check_prepared__(_embedding):
    if not _embedding in ['word2vec', 'glove']:
        _embedding = DEFAULT_EMBEDDING

    if _embedding == 'word2vec':
        # Check if word2vec is loaded in RAM
        if word2vec_embeddings is None:
            __prepare__(_word2vec=True, _glove=False)

    if _embedding == 'glove':
        if glove_embeddings is None:
            __prepare__(_word2vec=False, _glove=True)


def __prepare__(_word2vec=True, _glove=False):
    """
        **Call this function prior to doing absolutely anything else.**

        :param None
        :return: None
    """
    global word2vec_embeddings, glove_embeddings, glove_vocab

    if DEBUG: print("embeddings_interface: Loading Word Vector to Memory.")

    if _word2vec:
        word2vec_embeddings = gensim.models.KeyedVectors.load_word2vec_format('resources/GoogleNews-vectors-negative300.bin', binary=True)

    if _glove:
        try:
            glove_embeddings = np.load(os.path.join(glove_location['dir'], glove_location['parsed']))
            glove_vocab = pickle.load(open(os.path.join(glove_location['dir'], glove_location['vocab'])))
        except(IOError, EOFError):
            # Glove is not parsed and stored. Do it.
            if DEBUG: warnings.warn(" GloVe is not parsed and stored. This will take some time.")

            glove_embeddings = []
            glove_vocab = {}

            # Set some initial values
            glove_vocab['UNK'] = 0
            glove_embeddings.append(np.zeros(300, dtype=np.float32))

            glove_vocab['+'] = 1
            glove_embeddings.append(np.repeat(1, 300))

            glove_vocab['-'] = 2
            glove_embeddings.append(np.repeat(-1, 300))

            glove_vocab['/'] = 3
            glove_embeddings.append(np.repeat(0.5, 300))

            f = open(os.path.join(glove_location['dir'], glove_location['raw']))
            iterable = f
            counter = 4
            for line in iterable:
                values = line.split()
                word = values[0]
                if word in ['UNK', '+', '-', '/']:
                    continue
                coefs = np.asarray(values[1:], dtype='float32')
                glove_vocab[word] = counter
                glove_embeddings.append(coefs)
                counter += 1
            f.close()

            # Convert embeddings to numpy object
            glove_embeddings = np.asarray(glove_embeddings)

            # Now store them to disk
            np.save(os.path.join(glove_location['dir'], glove_location['parsed']), glove_embeddings)
            pickle.dump(glove_vocab, open(os.path.join(glove_location['dir'], glove_location['vocab']), 'w+'))

            if DEBUG: print("GloVe successfully parsed and stored. This won't happen again.")


def __congregate__(_vector_set, ignore=[]):
    if len(ignore) == 0:
        return np.mean(_vector_set, axis=0)
    else:
        return np.dot(np.transpose(_vector_set), ignore) / sum(ignore)


def phrase_similarity(_phrase_1, _phrase_2, embedding='glove'):
    __check_prepared__(embedding)

    phrase_1 = _phrase_1.split(" ")
    phrase_2 = _phrase_2.split(" ")
    vw_phrase_1 = []
    vw_phrase_2 = []
    for phrase in phrase_1:
        try:
            # print phrase
            vw_phrase_1.append(word2vec_embeddings.word_vec(phrase.lower()) if embedding == 'word2vec'
                else glove_embeddings[phrase.lower()])
        except:
            # print traceback.print_exc()
            continue
    for phrase in phrase_2:
        try:
            vw_phrase_2.append(word2vec_embeddings.word_vec(phrase.lower()) if embedding == 'word2vec'
                else glove_embeddings[phrase.lower()])
        except:
            continue
    if len(vw_phrase_1) == 0 or len(vw_phrase_2) == 0:
        return 0
    v_phrase_1 = __congregate__(vw_phrase_1)
    v_phrase_2 = __congregate__(vw_phrase_2)
    cosine_similarity = np.dot(v_phrase_1, v_phrase_2) / (np.linalg.norm(v_phrase_1) * np.linalg.norm(v_phrase_2))
    return float(cosine_similarity)


def vectorize(_tokens, _report_unks=False, _embedding='glove'):
    """
        Function to embed a sentence and return it as a list of vectors.
        WARNING: Give it already split strings. I ain't splitting it for ye.

        :param _tokens: The sentence you want embedded. (Assumed pre-tokenized input)
        :param _report_unks: Whether or not return the out of vocab words
        :return: Numpy tensor of n * 300d, [OPTIONAL] List(str) of tokens out of vocabulary.
    """

    __check_prepared__(_embedding)

    op = []
    unks = []
    for token in _tokens:

        # Small cap everything
        token = token.lower()

        try:
            if _embedding == "glove":
                token_embedding = glove_embeddings[glove_vocab[token]]
            elif _embedding == 'word2vec':
                token_embedding = word2vec_embeddings.word_vec(token)

        except KeyError:
            if _report_unks: unks.append(token)
            token_embedding = np.zeros(300, dtype=np.float32)

        finally:

            op += [token_embedding]

    return (np.asarray(op), unks) if _report_unks else np.asarray(op)


def vocabularize(_tokens, _report_unks=False, _embedding='glove'):
    """
            Function to embed a sentence and return it as a list of "IDS".
            WARNING: Give it already split. I ain't splitting it for ye.

            :param _tokens: The sentence you want embedded. (Assumed pre-tokenized input)
            :param _report_unks: Whether or not return the out of vocab words
            :return: Numpy tensor of n * 300d, [OPTIONAL] List(str) of tokens out of vocabulary.
        """

    __check_prepared__(_embedding)

    op = []
    unks = []
    for token in _tokens:

        # Small cap everything
        token = token.lower()

        try:

            if _embedding == "glove":
                token_id = glove_vocab[token]
            else:
                token_id = glove_vocab[token]

        except KeyError:

            if _report_unks: unks.append(token)
            token_id = 0

        finally:

            op += [token_id]

    return (np.asarray(op), unks) if _report_unks else np.asarray(op)
