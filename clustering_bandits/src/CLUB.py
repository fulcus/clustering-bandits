import numpy as np
import networkx as nx

from src.agents import Agent


class Cluster:
    def __init__(self, users, M, b, N):
        self.users = users  # a list/array of users
        self.M = M
        self.b = b
        self.N = N
        self.M_inv = np.linalg.inv(self.M)
        self.theta = np.matmul(self.M_inv, self.b)


class CLUB(Agent):
    # random_init: use random initialization or not
    def __init__(self, arms, context_set, horizon, edge_probability=1):
        super().__init__(arms, context_set)
        self.context_indexes = range(self.n_contexts)
        # Base
        self.horizon = horizon

        # INDLinUCB
        # one LinUCB per user i
        self.M = {i: np.eye(self.arm_dim) for i in range(self.n_contexts)}
        self.b = {i: np.zeros(self.arm_dim) for i in range(self.n_contexts)}
        self.M_inv = {i: np.eye(self.arm_dim) for i in range(self.n_contexts)}
        self.theta = {i: np.zeros(self.arm_dim) for i in range(self.n_contexts)}
        self.num_pulls = np.zeros(self.n_contexts)  # users array

        # CLUB
        self.nu = self.n_contexts
        # self.alpha = 4 * np.sqrt(d) # parameter for cut edge
        self.G = nx.gnp_random_graph(self.n_contexts, edge_probability)
        self.clusters = {0: Cluster(users=range(
            self.n_contexts), M=np.eye(self.arm_dim), b=np.zeros(self.arm_dim), N=0)}
        # index represents user, value is index of cluster he belongs to
        self.cluster_inds = np.zeros(self.n_contexts)
        # num_clusters over time (increasing)
        self.num_clusters = np.zeros(horizon)

    def pull_arm(self, context_i):
        """
        i: user index (context_i)
        items: (num_items, d) items to choose from (arms)
        """
        # get cluster of user i
        cluster_i = self.cluster_inds[context_i]
        cluster = self.clusters[cluster_i]
        self.last_pull_i = self._select_item_ucb(
            cluster.M_inv, cluster.theta, self.arms, cluster.N, self.t)
        self.a_hist.append(self.last_pull_i)
        return self.last_pull_i

    def _select_item_ucb(self, M_inv, theta, items, N, t):
        return np.argmax(np.dot(items, theta) + self._beta(N, t) * (np.matmul(items, M_inv) * items).sum(axis=1))

    def _beta(self, N, t):
        return np.sqrt(self.arm_dim * np.log(1 + N / self.arm_dim) + 4 * np.log(t) + np.log(2)) + 1

    def update(self, i, a, y):
        # INDLinUCB
        self.M[i] += np.outer(a, a)
        self.b[i] += y * a
        self.num_pulls[i] += 1
        self.M_inv[i], self.theta[i] = self._update_inverse(
            self.M[i], self.b[i], self.M_inv[i], a, self.num_pulls[i])

        # CLUB
        c = self.cluster_inds[i]
        self.clusters[c].M += np.outer(a, a)
        self.clusters[c].b += y * a
        self.clusters[c].N += 1

        self.clusters[c].M_inv, self.clusters[c].theta = self._update_inverse(
            self.clusters[c].M, self.clusters[c].b, self.clusters[c].M_inv, a, self.clusters[c].N)

    def _update_inverse(self, M, b, M_inv, x, t):
        M_inv = np.linalg.inv(M)
        theta = np.matmul(M_inv, b)
        return M_inv, theta

    def _if_split(self, theta, N1, N2):
        # alpha = 2 * np.sqrt(2 * self.d)
        alpha = 1

        def _factT(T):
            return np.sqrt((1 + np.log(1 + T)) / (1 + T))
        return np.linalg.norm(theta) > alpha * (_factT(N1) + _factT(N2))

    def update_cluster(self, t):
        update_clusters = False

        # delete edges
        for i in self.context_indexes:
            cluster_i = self.cluster_inds[i]
            A = [a for a in self.G.neighbors(i)]
            for j in A:
                if self.num_pulls[i] and self.num_pulls[j] and self._if_split(self.theta[i] - self.theta[j], self.num_pulls[i], self.num_pulls[j]):
                    self.G.remove_edge(i, j)
                    # print(f"remove_edge({i},{j})")
                    update_clusters = True

        if update_clusters:
            C = set() # contexts
            for i in self.context_indexes:  # suppose there is only one user per round
                C = nx.node_connected_component(self.G, i)
                cluster_i = self.cluster_inds[i]
                if len(C) < len(self.clusters[cluster_i].users):
                    remain_users = set(self.clusters[cluster_i].users)
                    self.clusters[cluster_i] = Cluster(list(C), M=sum([self.M[k]-np.eye(self.arm_dim) for k in C])+np.eye(
                        self.arm_dim), b=sum([self.b[k] for k in C]), N=sum([self.num_pulls[k] for k in C]))

                    remain_users = remain_users - set(C)
                    cluster_i = max(self.clusters) + 1
                    while len(remain_users) > 0:
                        j = np.random.choice(list(remain_users))
                        C = nx.node_connected_component(self.G, j)

                        self.clusters[cluster_i] = Cluster(list(C), M=sum([self.M[k]-np.eye(self.arm_dim) for k in C])+np.eye(
                            self.arm_dim), b=sum([self.b[k] for k in C]), N=sum([self.num_pulls[k] for k in C]))
                        for j in C:
                            self.cluster_inds[j] = cluster_i

                        cluster_i += 1
                        remain_users = remain_users - set(C)
            print(len(self.clusters))
        self.num_clusters[t] = len(self.clusters)

        # if t % 1000 == 0:
        #     print(self.cluster_inds)
        #     print([np.linalg.norm(self.theta[0]-self.theta[i]) for i in range(1,self.nu)])

    def update_arms(self, rewards):
        for arm_i, reward, c_i in zip(self.last_pulls_i, rewards, range(self.n_contexts)):
            # update weights
            self.update(i=c_i, a=self.arms[arm_i], y=reward)
        self.update_cluster(self.t)
        self.t += 1


"""
    def run(self, envir):
        for t in range(self.T):
            if t % 5000 == 0:
                print(t // 5000, end=' ')
            self.I = envir.generate_users()
            # main diff: recommend for each user i
            for i in self.I:
                # context_indexes = environment.get_contexts()
                items = envir.get_items()
                # actions = agent.pull_arms(context_indexes)
                # actually: only best action for current external ctx
                kk = self.pull_arm(context_i=i, items=items, t=t)
                x = items[kk]
                # rewards = environment.round_all(actions)
                y, r, br = envir.feedback(i=i, k=kk)
                # agent.update_arms(rewards)
                self.update_weights(i=i, x=x, y=y, t=t, r=r, br=br)

            self.update(t)
"""
