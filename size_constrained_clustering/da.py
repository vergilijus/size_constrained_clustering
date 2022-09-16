#!usr/bin/python 3.6
# -*-coding:utf-8-*-

'''
@file: da.py, deterministic annealing algorithm
@Author: Jing Wang (jingw2@foxmail.com)
@Date: 11/28/2019
@Paper reference: Clustering with Capacity and Size Constraints: A Deterministic Approach
'''
import collections
import logging
import numpy as np
import os
import random
import sys
from scipy.spatial.distance import cdist
from tqdm import tqdm
from typing import Dict, Tuple

from size_constrained_clustering.base import Base

logger = logging.getLogger(__name__)


class DeterministicAnnealing(Base):

    def __init__(self, n_clusters, distribution,
                 max_iters=1000,
                 labels_unchanged_threshold=15,
                 distance_func=cdist, random_state=42,
                 T=(1000, 100, 10, 1, 0.1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8),
                 show_progress=True,
                 debug=False):
        '''
        Args:
            n_clusters (int): number of clusters
            distribution (list): a list of ratio distribution for each cluster
            T (list): inverse choice of beta coefficients
        '''
        super(DeterministicAnnealing, self).__init__(n_clusters, max_iters, distance_func)
        self.lamb = distribution
        assert np.sum(distribution).round(3) == 1
        assert len(distribution) == n_clusters
        assert isinstance(T, list) or isinstance(T, tuple) or T is None

        self.beta = None
        self.T = T
        self.t = None
        self.cluster_centers_ = None
        self.labels_ = None
        self._eta = None
        self._demands_prob = None
        self.debug = debug
        self.labels_unchanged = 0
        self.labels_unchanged_threshold = labels_unchanged_threshold
        self.prev_labels = None
        self.show_progress = show_progress
        random.seed(random_state)
        np.random.seed(random_state)
        logger.debug(f'Temperature: {self.T}')

    def fit(self, X, demands_prob=None, fixed_points=None):
        # setting T, loop
        solutions = []
        diff_list = []
        is_early_terminated = False

        n_samples, n_features = X.shape
        self.capacity = [n_samples * d for d in self.lamb]
        if demands_prob is None:
            demands_prob = np.ones((n_samples, 1))
        else:
            demands_prob = np.asarray(demands_prob).reshape((-1, 1))
            assert demands_prob.shape[0] == X.shape[0]
        demands_prob = demands_prob / sum(demands_prob)
        for t in self.T:
            logger.debug(f'Current T: {t}')
            self.t = t
            centers = self.initial_centers(X)

            if fixed_points:
                centers = self.set_centers_for_anchors(centers, X, fixed_points)

            eta = self.lamb
            labels = None

            for i in tqdm(range(self.max_iters), disable=not self.show_progress):
                self.beta = 1. / self.t
                distance_matrix = self.distance_func(X, centers)
                eta = self.update_eta(eta, demands_prob, distance_matrix)
                gibbs = self.update_gibbs(eta, distance_matrix)
                if fixed_points:
                    gibbs = self.set_gibbs_fixed_points(gibbs, fixed_points)
                centers = self.update_centers(demands_prob, gibbs, X)
                if fixed_points:
                    centers = self.set_centers_for_anchors(centers, X, fixed_points)
                self.t *= 0.999

                labels = np.argmax(gibbs, axis=1)

                self.on_iter_end(i, X, eta, gibbs, centers, labels)
                if self.break_condition(labels): break

                self.prev_labels = labels

            solutions.append([labels, centers])
            resultant_clusters = len(collections.Counter(labels))

            diff_list.append(abs(resultant_clusters - self.n_clusters))

            if resultant_clusters == self.n_clusters:
                is_early_terminated = True
                break

        # modification for non-strictly satisfaction, only works for one demand per location
        # labels = self.modify(labels, centers, distance_matrix)
        if not is_early_terminated:
            best_index = np.argmin(diff_list)
            labels, centers = solutions[best_index]

        self.cluster_centers_ = centers
        self.labels_ = labels
        self._eta = eta
        self._demands_prob = demands_prob

    def predict(self, X):
        distance_matrix = self.distance_func(X, self.cluster_centers_)
        eta = self.update_eta(self._eta, self._demands_prob, distance_matrix)
        gibbs = self.update_gibbs(eta, distance_matrix)
        labels = np.argmax(gibbs, axis=1)
        return labels

    def modify(self, labels, centers, distance_matrix):
        centers_distance = self.distance_func(centers, centers)
        adjacent_centers = {i: np.argsort(centers_distance, axis=1)[i, 1:3].tolist() for i in range(self.n_clusters)}
        while not self._is_satisfied(labels):
            count = collections.Counter(labels)
            cluster_id_list = list(count.keys())
            random.shuffle(cluster_id_list)
            for cluster_id in cluster_id_list:
                num_points = count[cluster_id]
                diff = num_points - self.capacity[cluster_id]
                if diff <= 0:
                    continue
                adjacent_cluster = None
                adjacent_cluster = random.choice(adjacent_centers[cluster_id])
                if adjacent_cluster is None:
                    continue
                cluster_point_id = np.where(labels == cluster_id)[0].tolist()
                diff_distance = distance_matrix[cluster_point_id, adjacent_cluster] \
                                - distance_matrix[cluster_point_id, cluster_id]
                remove_point_id = np.asarray(cluster_point_id)[np.argsort(diff_distance)[:diff]]
                labels[remove_point_id] = adjacent_cluster

        return labels

    def initial_centers(self, X):
        selective_centers = random.sample(range(X.shape[0]), self.n_clusters)
        centers = X[selective_centers]
        return centers

    def set_centers_for_anchors(self, centers, X, fixed_points: Dict[int, Tuple[int]]):
        for cluster_id, points_idxs in fixed_points.items():
            centers[cluster_id] = X[points_idxs].mean(axis=0)
        return centers

    def break_condition(self, labels):
        return self._is_satisfied(labels)

    def _is_satisfied(self, labels):
        count = collections.Counter(labels)
        for cluster_id in range(len(self.capacity)):
            if cluster_id not in count:
                return False
            num_points = count[cluster_id]
            if num_points > self.capacity[cluster_id]:
                return False
        return True

    def update_eta(self, eta, demands_prob, distance_matrix):
        n_points, n_centers = distance_matrix.shape
        eta_repmat = np.tile(np.asarray(eta).reshape(1, -1), (n_points, 1))
        exp_term = np.exp(- self.beta * distance_matrix)
        divider = exp_term / np.sum(np.multiply(exp_term,
                                                eta_repmat), axis=1).reshape((-1, 1))
        eta = np.divide(np.asarray(self.lamb),
                        np.sum(divider * demands_prob, axis=0))

        return eta

    def update_gibbs(self, eta, distance_matrix):
        n_points, n_centers = distance_matrix.shape
        eta_repmat = np.tile(np.asarray(eta).reshape(1, -1), (n_points, 1))
        exp_term = np.exp(- self.beta * distance_matrix)
        factor = np.multiply(exp_term, eta_repmat)
        gibbs = factor / np.sum(factor, axis=1).reshape((-1, 1))
        return gibbs

    def set_gibbs_fixed_points(self, gibbs, fixed_points):
        for cluster_id, points_id in fixed_points.items():
            gibbs[tuple([points_id])] = 0
            gibbs[[points_id], cluster_id] = 1
        return gibbs

    def update_centers(self, demands_prob, gibbs, X):
        n_points, n_features = X.shape
        divide_up = gibbs.T.dot(X * demands_prob)  # n_cluster, n_features
        p_y = np.sum(gibbs * demands_prob, axis=0)  # n_cluster,
        p_y_repmat = np.tile(p_y.reshape(-1, 1), (1, n_features))
        centers = np.divide(divide_up, p_y_repmat)
        return centers

    def on_iter_end(self, i, X, eta, gibbs, centers, labels):
        pass
