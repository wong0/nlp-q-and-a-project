#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, division
import argparse
import json
import os
import struct
import sys
from base64 import urlsafe_b64decode as b64decode, \
    urlsafe_b64encode as b64encode
from collections import defaultdict
from functools import partial, reduce
# from itertools import imap

import numpy as np

from mctest_pb2 import StoryAsEmbeddings, QuestionAsEmbeddings
from parse import parse_proto_stream


ANSWER_LETTER = ['A', 'B', 'C', 'D']


def load_target_answers(stream):
    answers = stream.readlines()
    answers = map(lambda x: x.rstrip().split('\t'), answers)
    return reduce(lambda x, y: x + y, answers)


def l2_normalize(v):
    return v / np.sqrt(np.dot(v, v))


class SlidingWindowEmbeddings(object):
    def __init__(self, window_size=None):
        self._window_size = window_size

    def score_target(self, passage, target, verbose=True):
        target_size = len(target)
        window_size = self._window_size or target_size
        mean_target = l2_normalize(np.mean(target, 0))
        max_score = -np.inf
        tokens_at_max = []
        for i in xrange(len(passage) - window_size):
            try:
                mean_passage = l2_normalize(
                    np.mean(passage[i:i + window_size], 0))
                score = -np.dot(mean_passage-mean_target, mean_passage-mean_target)
                if score > max_score:
                    max_score = score
                    tokens_at_max = i, i + window_size
            except IndexError:
                pass
        if verbose:
            print('[score=%.2f] passage: %s ' %
                  (max_score, tokens_at_max), file=sys.stderr)
        return max_score

    def predict(self, passage, question, answers, verbose=True):
        scores = []
        for answer in answers:
            scores.append(self.score_target(
                passage, question + answer, verbose))
        return scores


def tokens_to_embeddings(model, tokens):
    embeds = []
    for token in tokens:
        try:
            token = token.lower()
            embeds.append(model[token])
        except KeyError as e:
            print('WARNING: "%s" missing from vocabulary.' % token,
                  file=sys.stderr)
    return embeds


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Baseline models from the MCTest paper (sliding '
        'window and distance based)')
    _arg = parser.add_argument
    _arg('--train', type=str, action='store', metavar='FILE', required=True,
         help='File with stories and questions (JSON format).')
    _arg('--truth', type=str, action='store', metavar='FILE',
         help='File with correct answers to the questions.')
    _arg('--window-size', type=int, action='store', metavar='SIZE',
         default=None, help='Fixed window size for the sliding window ' \
         'algorithm. By default it has the same length as the question.')
    args = parser.parse_args()

    stories = list(parse_proto_stream(open(args.train, 'r'), StoryAsEmbeddings))
    print('[model]\nwindow_size = %s\n' % (args.window_size))

    sw = SlidingWindowEmbeddings(window_size=args.window_size)
    predicted, q_types = [], []
    to_array_list = lambda tokens: map(lambda s: np.array(s.value), tokens)

    print('len(stories)', len(stories))
    
    for story in stories[:]:
        passage_vec = to_array_list(story.passage)
        for question in story.questions:
            q_types.append(question.type)
            question_vec = to_array_list(question.tokens)
            answers_vec = [to_array_list(answer.tokens)
                           for answer in question.answers]
            
            print('story > scores', scores)

            scores = sw.predict(passage_vec, question_vec, answers_vec, False)

            # print(ANSWER_LETTER[scores.index(max(scores))])
            predicted.append(ANSWER_LETTER[scores.index(max(scores))])

    if args.truth:
        answers_in = open(args.truth, 'r')
        answers = np.array(load_target_answers(answers_in))
        predicted = np.array(predicted)

        print('len(answers) =', len(answers), 'len(predicted) =', len(predicted));

        assert len(answers) == len(predicted)

        single = np.array(q_types) == QuestionAsEmbeddings.ONE
        n_single = float(np.sum(single))
        n_multiple = float(np.sum(~single))
        assert n_single + n_multiple == len(answers)

        print('All accuracy [%d]: %.4f' %
              (n_single + n_multiple,
               np.sum(answers == predicted) / float(len(predicted))))
        print('Single accuracy [%d]: %.4f' %
              (n_single,
               np.sum(answers[single] == predicted[single]) / n_single))
        print('Multiple accuracy [%d]: %.4f\n' %
              (n_multiple,
               np.sum(answers[~single] == predicted[~single]) / n_multiple))
    else:
        for p in predicted:
            print(p, file=sys.stdout)
