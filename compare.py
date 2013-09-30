"""Usage:

python compare.py <path to text file with annotated data>
"""

import sys
import os
import codecs
import csv
import logging
from collections import Counter

from alchemy import Alchemy
from bitext import Bitext
from chatterbox import Chatterbox
from datumbox import Datumbox
from repustate import Repustate
from semantria_api import Semantria
from skyttle import Skyttle
from viralheat import Viralheat
from thr import Thr


ANALYZERS_TO_USE = [
                    'skyttle',
                    'chatterbox',
                    'datumbox',
                    'repustate',
                    'bitext',
                    'alchemy',
                    'semantria',
                    'viralheat'
                ]
ANALYZERS = []
LOGGER = None


def setup_logging():
    """Log debug or higher to a file, errors to stderr
    """
    global LOGGER
    fname = 'compare.log'
    if os.path.exists(fname):
         os.unlink(fname)

    format = '%(levelname)s:%(name)s:%(message)s'

    logging.basicConfig(filename=fname, level=logging.DEBUG, format=format)
    LOGGER = logging.getLogger('APICompare')

    streamhandler = logging.StreamHandler()
    streamhandler.setLevel(logging.ERROR)
    streamhandler.setFormatter(logging.Formatter(format))

    LOGGER.addHandler(streamhandler)


def read_evaluation_data(fname):
    """Read the file with test documents, possibly provided with the key in the
    second column (+, -, or 0)
    :return doc_id2doc: document id to the text of the document
    :return doc_id2key: document id to the manually assigned sentiment label
    """
    doc_id2key = {}
    doc_id2doc = {}
    doc_id = 0
    for line in codecs.open(fname, 'r', 'utf8'):
        if not line.strip():
            continue
        try:
            document, key = line.split('\t')
            key = key.strip()
            doc_id2key[doc_id] = key
        except ValueError:
            document = line
        document = document.strip()
        doc_id2doc[doc_id] = document
        doc_id += 1
    return doc_id2doc, doc_id2key


def read_config():
    """Read API keys
    """
    config = {}
    fname = 'config.txt'
    for line in codecs.open(fname, 'r', 'utf8'):
        line = line.strip()
        key, val = line.split('\t')
        config[key] = val
    return config


def initialize_analysers(config):
    """Initialise analysers
    """
    if 'skyttle' in ANALYZERS_TO_USE:
        skyttle = Skyttle(mashape_auth=config['mashape_auth'],
                          language=config['language'])
        ANALYZERS.append(skyttle)

    if 'chatterbox' in ANALYZERS_TO_USE:
        chatterbox = Chatterbox(mashape_auth=config['mashape_auth'],
                          language=config['language'])
        ANALYZERS.append(chatterbox)

    if 'datumbox' in ANALYZERS_TO_USE:
        datumbox = Datumbox(api_key=config['datumbox_key'])
        ANALYZERS.append(datumbox)

    if 'repustate' in ANALYZERS_TO_USE:
        repustate = Repustate(api_key=config['repustate_key'])
        ANALYZERS.append(repustate)

    if 'bitext' in ANALYZERS_TO_USE:
        bitext = Bitext(user=config['bitext_user'],
                        password=config['bitext_pwd'],
                        language=config['language'])
        ANALYZERS.append(bitext)

    if 'alchemy' in ANALYZERS_TO_USE:
        alchemy = Alchemy(api_key=config['alchemy_key'])
        ANALYZERS.append(alchemy)

    if 'semantria' in ANALYZERS_TO_USE:
        semantria = Semantria(consumer_key=config['semantria_consumer_key'],
                              consumer_secret=config['semantria_consumer_secret'])
        ANALYZERS.append(semantria)

    if 'viralheat' in ANALYZERS_TO_USE:
        viralheat = Viralheat(api_key=config['viralheat_key'])
        ANALYZERS.append(viralheat)


def process_one_doc(text, key):
    """Process one document in all analyzers
    :return result_list: a list of outputs for all analyzers
    :return hits: a Counter with hits for all analyzers
    :return errors: a Counter with errors for all analyzers
    """
    global ANALYZERS

    hits = Counter()
    errors = Counter()
    results = {}
    Thr.outputs = {}
    Thr.inputs = {}

    threads = []
    for analyser in ANALYZERS:
        thr = Thr(analyser, [text])
        threads.append(thr)
        thr.start()
    for thr in threads:
        thr.join()

    for name, output in Thr.outputs.items():
        if isinstance(output, tuple) and not output[0]:
            output = 'Error'
        if output == key:
            hits[name] += 1
        elif output != 'Error':
            if key == '0' or output == '0':
                errors[name] += 1
            else:
                errors[name] += 2
        results[name] = output

    result_list = [results[x.name] for x in ANALYZERS]

    return result_list, hits, errors


def get_max_weighted_errors(doc_id2key):
    """Determine the maximum possible sum of weighted errors
    """
    max_errors = 0
    for gs_key in doc_id2key.values():
        if gs_key == '0':
            max_errors += 1
        else:
            max_errors += 2
    return float(max_errors)


def evaluate(doc_id2text, doc_id2key):
    """Send evaluation documents to each API, output all results into a table,
    and if doc_id2key are available, output accuracy and error rate.
    """
    total_hits = Counter()
    total_errors = Counter()
    accuracy = Counter()
    error_rate = Counter()

    cvswriter = csv.writer(open('results.csv', 'wb'), delimiter='\t')
    col_names = ['doc_id', 'text', 'gold standard'] + [x.name for x in ANALYZERS]
    cvswriter.writerow(col_names)

    for doc_id, text in sorted(doc_id2text.items()):
        key = doc_id2key.get(doc_id)
        results, doc_hits, doc_errors = process_one_doc(text, key)
        if doc_hits:
            total_hits += doc_hits
        if doc_errors:
            total_errors += doc_errors
        cvswriter.writerow([doc_id, text, key] + results)

    num_docs = float(len(doc_id2text))
    max_errors = get_max_weighted_errors(doc_id2key)

    for analyzer in ANALYZERS:
        name = analyzer.name
        accuracy[name] = total_hits.get(name, 0.0)/num_docs
        error_rate[name] = total_errors.get(name, 0.0)/max_errors

    return accuracy, error_rate


def main(test_data_fname):
    """Main function
    """

    setup_logging()

    # read test data
    doc_id2text, doc_id2key = read_evaluation_data(test_data_fname)

    # read config
    config = read_config()

    # initialise relevant analysers
    initialize_analysers(config)

    # evaluate
    accuracy, error_rate = evaluate(doc_id2text, doc_id2key)

    print "%-15s%s" % ('Analyzer', 'Accuracy')
    for name, score in accuracy.most_common():
        print "%-15s%.3f" % (name, score)
    print
    print "%-15s%s" % ('Analyzer', 'Error rate')
    for name, score in reversed(error_rate.most_common()):
        print "%-15s%.3f" % (name, score)


if __name__ == "__main__":

    main(sys.argv[1])
