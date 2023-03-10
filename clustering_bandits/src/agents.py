from abc import ABC, abstractmethod
import numpy as np
from src.utils import moving_average


class Agent(ABC):
    def __init__(self, arms, context_set):
        self.arms = arms
        self.context_set = context_set
        self.n_contexts = context_set.shape[0]
        self.n_arms = arms.shape[0]
        self.arm_dim = arms.shape[1]
        self.t = 0
        self.a_hist = []
        self.last_pulls = [[] for _ in range(self.n_contexts)]

    @abstractmethod
    def pull_arm(self, context_i):
        pass

    def pull_all(self, context_indexes):
        for c_i in context_indexes:
            self.last_pulls[c_i] = self.pull_arm(c_i)
        return self.last_pulls

    @abstractmethod
    def update(self, reward, *args, **kwargs):
        self.t += 1

    def update_all(self, rewards):
        for arm, reward, c_i in zip(self.last_pulls, rewards, range(self.n_contexts)):
            self.update(reward, arm=arm, context_i=c_i)


class Clairvoyant(Agent):
    """Always pulls the optimal arm"""

    def __init__(self, arms, context_set, theta, theta_p, k):
        super().__init__(arms, context_set)
        self.theta = theta
        self.theta_p = theta_p
        self.k = k

    def pull_arm(self, context_i):
        exp_rewards = np.zeros(self.n_arms)
        for i, arm in enumerate(self.arms):
            exp_rewards[i] = (self.theta @ arm[:self.k]
                              + self.theta_p[context_i] @ arm[self.k:])
        arm_i = np.argmax(exp_rewards)
        self.a_hist.append(arm_i)
        return self.arms[arm_i]

    def update(self, reward, arm, context_i=None):
        self.t += 1


class UCB1Agent(Agent):
    def __init__(self, arms, context_set, max_reward=1):
        super().__init__(arms, context_set)
        self.max_reward = max_reward
        self.avg_reward = np.ones(self.n_arms) * np.inf
        self.n_pulls = np.zeros(self.n_arms)
        self.arm_index = {tuple(arm): i for i, arm in enumerate(arms)}

    def pull_arm(self, *args, **kwargs):
        ucb1 = [self.avg_reward[a] + self.max_reward *
                np.sqrt(2 * np.log(self.t)
                / self.n_pulls[a]) for a in range(self.n_arms)]
        arm_i = np.argmax(ucb1)
        self.n_pulls[arm_i] += 1
        self.a_hist.append(arm_i)
        return self.arms[arm_i]

    def update(self, reward, arm, *args, **kwargs):
        arm_i = self.arm_index[tuple(arm)]

        if self.n_pulls[arm_i] == 1:
            self.avg_reward[arm_i] = reward
        else:
            self.avg_reward[arm_i] = ((
                self.avg_reward[arm_i]
                * self.n_pulls[arm_i] + reward)
                / (self.n_pulls[arm_i] + 1))
        self.t += 1


class LinUCBAgent(Agent):
    def __init__(self, arms, context_set, horizon, lmbd,
                 max_theta_norm, max_arm_norm, sigma=1):
        super().__init__(arms, context_set)
        assert lmbd > 0
        self.lmbd = lmbd
        self.horizon = horizon
        self.max_theta_norm = max_theta_norm
        self.max_arm_norm = max_arm_norm
        self.sigma = sigma

        self.V_t = self.lmbd * np.eye(self.arm_dim)
        self.V_t_inv = np.linalg.inv(self.V_t)
        self.b_vect = np.zeros((self.arm_dim, 1))
        self.theta_hat = np.zeros((self.arm_dim, 1))

        self.last_ucb = np.zeros(self.n_arms)
        self.reward_hist = []

    def pull_arm(self, *args, **kwargs):
        if len(self.a_hist) < self.arm_dim:
            arm_i = len(self.a_hist) % self.n_arms
        else:
            arm_i = self._estimate_linucb_arm()
        self.a_hist.append(arm_i)
        return self.arms[arm_i]

    def update(self, reward, arm, *args, **kwargs):
        arm = arm.reshape(-1, 1)
        # update params
        self.V_t += arm @ arm.T
        self.b_vect = self.b_vect + arm * reward
        self.V_t_inv = np.linalg.inv(self.V_t)
        self.theta_hat = self.V_t_inv @ self.b_vect
        # update hist
        self.reward_hist.append(reward)
        self.t += 1

    def _estimate_linucb_arm(self):
        bound = self._beta_t_fun_linucb()
        for i, arm in enumerate(self.arms):
            arm = arm.reshape(-1, 1)
            self.last_ucb[i] = (self.theta_hat.T @ arm + bound
                                * np.sqrt(arm.T @ self.V_t_inv @ arm))
        return np.argmax(self.last_ucb)

    def _beta_t_fun_linucb(self):
        return self.max_theta_norm * np.sqrt(self.lmbd) + \
            np.sqrt(2 * self.sigma**2 * np.log(self.t) +
                    np.log(np.linalg.det(self.V_t) / (self.lmbd ** self.arm_dim)))


class INDLinUCBAgent(Agent):
    """One independent LinUCBAgent instance per context - BASELINE"""

    def __init__(self, arms, context_set, horizon, lmbd,
                 max_theta_norm_sum, max_arm_norm, sigma=1):
        super().__init__(arms, context_set)
        self.lmbd = lmbd
        self.horizon = horizon
        self.max_theta_norm_sum = max_theta_norm_sum
        self.max_arm_norm = max_arm_norm
        self.sigma = sigma
        self.arm_index = {tuple(arm): i for i, arm in enumerate(arms)}
        self.context_agent = [
            LinUCBAgent(
                self.arms,
                self.context_set,
                self.horizon,
                self.lmbd,
                self.max_theta_norm_sum,
                self.max_arm_norm,
                self.sigma)
            for _ in range(self.n_contexts)
        ]

    def pull_arm(self, context_i):
        arm = self.context_agent[context_i].pull_arm()
        arm_i = self.arm_index[tuple(arm)]
        self.a_hist.append(arm_i)
        return arm

    def update(self, reward, arm, context_i):
        self.context_agent[context_i].update(
            reward, arm)
        self.t += 1


class PartitionedAgent(INDLinUCBAgent):
    """An independent linear bandit per context. 
    The first bandit that learns a good approximation of theta fixes 
    the first k components of theta for all."""

    def __init__(self, arms, context_set, horizon, lmbd,
                 max_theta_norm_sum, max_arm_norm, k=2, err_th=0.1, win=10, sigma=1):
        super().__init__(arms, context_set, horizon, lmbd,
                         max_theta_norm_sum, max_arm_norm, sigma)
        self.k = k
        self.err_th = err_th
        self.win = win

        self.is_split = False
        self.t_split = None
        self.reward_global = None
        self.subarm_global = None
        self.arms_global = np.delete(self.arms, np.s_[self.k:], axis=1)
        self.arms_local = np.delete(self.arms, np.s_[:self.k], axis=1)
        self.max_arm_norm_local = np.max(
            [np.linalg.norm(a) for a in self.arms_local])
        self.arm_index = {tuple(arm): i for i, arm in enumerate(arms)}
        self.agents_err_hist = [[] for _ in range(self.n_contexts)]

    def pull_arm(self, context_i):
        arm = self.context_agent[context_i].pull_arm()
        # if split has happened arm_i is index of second half
        if self.is_split:
            arm = np.concatenate([self.subarm_global, arm])
        arm_i = self.arm_index[tuple(arm)]
        self.a_hist.append(arm_i)
        return arm

    def update_all(self, rewards):
        arm_leader = None
        for arm, reward, c_i in zip(self.last_pulls, rewards, range(self.n_contexts)):
            if self.is_split:
                arm = arm[self.k:]
                # remove global arm contribution to reward for local arm update 
                pred_reward_local = self.context_agent[c_i].theta_hat.T @ arm
                error = (reward - (self.reward_global + pred_reward_local)) ** 2
                reward -= self.reward_global
                self.agents_err_hist[c_i].append(error)
            else:
                pred_reward = self.context_agent[c_i].theta_hat.T @ arm
                error = (reward - pred_reward) ** 2
                self.agents_err_hist[c_i].append(error)
                if moving_average(self.agents_err_hist[c_i], win=self.win) <= self.err_th:
                    arm_leader, c_i_leader = arm, c_i
                    print(f"error={error.squeeze()}\n" +
                          f"theta_hat={self.context_agent[c_i].theta_hat.squeeze()}\n" +
                          f"{c_i_leader=}")
            self.update(reward, arm, c_i)

        # recompute params at the end of round
        if arm_leader is not None:
            self._split_agents_params(arm_leader, c_i_leader)
            self.t_split = self.t
            self.is_split = True
            print(f"t_split={self.t_split}\n")

    def _split_agents_params(self, arm, context_i):
        subtheta_global = self.context_agent[context_i].theta_hat[:self.k]
        self.subarm_global = arm[:self.k]
        self.reward_global = subtheta_global.T @ self.subarm_global

        for agent in self.context_agent:
            # remove global components from all agents
            agent.arm_dim -= self.k
            agent.max_arm_norm = self.max_arm_norm_local
            agent.arms = self.arms_local
            # removing global components contributions
            y_loc = np.array(agent.reward_hist) - \
                subtheta_global.T @ self.arms_global[agent.a_hist].T
            A_loc = self.arms_local[agent.a_hist]
            # recompute bandit parameters
            agent.V_t = A_loc.T @ A_loc + \
                agent.lmbd * np.eye(agent.arm_dim)
            agent.b_vect = A_loc.T @ y_loc.T
            agent.V_t_inv = np.linalg.inv(agent.V_t)
            agent.theta_hat = agent.V_t_inv @ agent.b_vect
